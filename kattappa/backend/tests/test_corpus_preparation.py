"""Unit tests for Program 27.0 / Phase 27A: Corpus Preparation Pipeline.

Verifies deduplication (exact + near-dup), stratified splitting, token
estimation, and the end-to-end corpus export manifest.
"""
from __future__ import annotations

import pytest
from backend.core.learning.trajectory_builder import Trajectory
from backend.core.learning.experience_store import ExperienceStore
from backend.core.dataset.trace_extractor import TraceExtractor
from backend.core.dataset.deduplicator import Deduplicator, _hamming_distance, _simhash
from backend.core.dataset.corpus_splitter import CorpusSplitter
from backend.core.dataset.token_estimator import TokenEstimator
from backend.core.dataset.corpus_exporter import CorpusExporter
from backend.core.dataset.dataset_versioning import DatasetVersioning


@pytest.fixture(autouse=True)
def clean_versions():
    DatasetVersioning.reset()
    yield
    DatasetVersioning.reset()


def _traj(
    goal_id: str,
    success: bool = True,
    score: float = 0.85,
    nodes: list[str] | None = None,
    recoveries: int = 0,
) -> Trajectory:
    return Trajectory(
        goal_id=goal_id,
        plan_id="plan-01",
        planner_version="HTN-v2",
        success=success,
        predicted_duration=10.0,
        actual_duration=12.0,
        predicted_cost=0.015,
        actual_cost=0.02,
        failures_count=0,
        recoveries_count=recoveries,
        combined_score=score,
        nodes_executed=nodes if nodes is not None else ["step_a", "step_b"],
    )


def _rec(
    instruction: str,
    actions: list[str] | None = None,
    result: str = "success",
    score: float = 0.85,
) -> dict:
    """Builds a minimal extraction record directly for lower-level tests."""
    return {
        "instruction": instruction,
        "context": {},
        "reasoning_trace": " -> ".join(actions or []),
        "actions": actions or ["step_a", "step_b"],
        "result": result,
        "metrics": {
            "combined_score": score,
            "duration": 12.0,
            "cost": 0.02,
            "failures": 0,
            "recoveries": 0,
        },
    }


# ── 1. SimHash & Hamming helpers ──────────────────────────────────────────────

class TestSimHash:
    def test_identical_text_same_fingerprint(self):
        fp1 = _simhash("deploy the docker sandbox now")
        fp2 = _simhash("deploy the docker sandbox now")
        assert fp1 == fp2

    def test_different_text_different_fingerprint(self):
        fp1 = _simhash("deploy the docker sandbox")
        fp2 = _simhash("train the neural network on gpu cluster")
        assert _hamming_distance(fp1, fp2) > 3

    def test_hamming_distance_identical(self):
        assert _hamming_distance(0b1010, 0b1010) == 0

    def test_hamming_distance_one_bit(self):
        assert _hamming_distance(0b1010, 0b1011) == 1

    def test_empty_text_produces_zero(self):
        assert _simhash("") == 0


# ── 2. Deduplicator ───────────────────────────────────────────────────────────

class TestDeduplicator:
    def test_exact_duplicates_removed(self):
        rec = _rec("deploy docker sandbox", actions=["a", "b"])
        duplicate = _rec("deploy docker sandbox", actions=["a", "b"])
        records = [rec, duplicate, _rec("train model", actions=["x"])]
        unique, stats = Deduplicator.deduplicate(records, hamming_threshold=3)
        assert stats["exact_removed"] == 1
        assert stats["total_output"] == 2

    def test_near_duplicates_removed(self):
        # Two very similar instructions — differ by one prefix word.
        # Threshold=8 is the calibrated default for 6–10 word sentences.
        base = _rec("Please deploy the docker sandbox now", actions=["a", "b"])
        near = _rec("deploy the docker sandbox now", actions=["c", "d"])
        distinct = _rec("train a neural network on the GPU cluster tonight", actions=["x"])
        unique, stats = Deduplicator.deduplicate([base, near, distinct], hamming_threshold=8)
        assert stats["near_removed"] == 1
        assert stats["total_output"] == 2

    def test_distinct_records_all_kept(self):
        records = [
            _rec("deploy docker sandbox", actions=["a"]),
            _rec("train the neural network on GPU", actions=["b"]),
            _rec("run automated integration tests for the api", actions=["c"]),
        ]
        unique, stats = Deduplicator.deduplicate(records)
        assert stats["exact_removed"] == 0
        assert stats["near_removed"] == 0
        assert stats["total_output"] == 3

    def test_empty_list(self):
        unique, stats = Deduplicator.deduplicate([])
        assert stats["total_output"] == 0
        assert stats["total_input"] == 0


# ── 3. Corpus Splitter ────────────────────────────────────────────────────────

class TestCorpusSplitter:
    def _build_records(self, n_success: int, n_failure: int, n_recovered: int):
        records = []
        for i in range(n_success):
            records.append(_rec(f"success_task_{i}", result="success"))
        for i in range(n_failure):
            records.append(_rec(f"failure_task_{i}", result="failure"))
        for i in range(n_recovered):
            records.append(_rec(f"recovered_task_{i}", result="recovered"))
        return records

    def test_split_sizes_sum_to_total(self):
        records = self._build_records(80, 10, 10)
        (train, val, test), info = CorpusSplitter.split(records, seed=42)
        assert info["train_count"] + info["val_count"] + info["test_count"] == len(records)

    def test_train_is_largest_split(self):
        records = self._build_records(60, 20, 20)
        (train, val, test), _ = CorpusSplitter.split(records, seed=42)
        assert len(train) > len(val)
        assert len(train) > len(test)

    def test_all_labels_appear_in_train(self):
        records = self._build_records(30, 10, 10)
        (train, val, test), _ = CorpusSplitter.split(records, seed=42)
        results_in_train = {r["result"] for r in train}
        assert "success" in results_in_train
        assert "failure" in results_in_train
        assert "recovered" in results_in_train

    def test_reproducible_with_same_seed(self):
        records = self._build_records(50, 20, 10)
        (train1, _, _), _ = CorpusSplitter.split(records, seed=99)
        (train2, _, _), _ = CorpusSplitter.split(records, seed=99)
        assert [r["instruction"] for r in train1] == [r["instruction"] for r in train2]

    def test_invalid_ratios_raise(self):
        with pytest.raises(ValueError):
            CorpusSplitter.split([_rec("x")], train_ratio=0.5, val_ratio=0.5, test_ratio=0.5)


# ── 4. Token Estimator ────────────────────────────────────────────────────────

class TestTokenEstimator:
    def test_basic_estimate(self):
        records = [_rec("deploy docker sandbox", actions=["step_a", "step_b"])] * 10
        report = TokenEstimator.estimate(records)
        assert report["total_records"] == 10
        assert report["total_tokens"] > 0
        assert 0.0 <= report["latin_token_share"] <= 1.0

    def test_flops_computed_when_params_given(self):
        records = [_rec("run tests", actions=["a"])] * 5
        report = TokenEstimator.estimate(records, model_params=135_000_000)
        assert report["training_flops"] is not None
        assert report["training_flops"] > 0

    def test_no_flops_without_params(self):
        records = [_rec("run tests", actions=["a"])]
        report = TokenEstimator.estimate(records)
        assert report["training_flops"] is None

    def test_recommended_scale_small_corpus(self):
        records = [_rec(f"task_{i}") for i in range(5)]
        report = TokenEstimator.estimate(records)
        assert "135M" in report["recommended_scale"]

    def test_empty_corpus(self):
        report = TokenEstimator.estimate([])
        assert report["total_tokens"] == 0
        assert report["avg_tokens_per_record"] == 0.0


# ── 5. Corpus Exporter (end-to-end) ──────────────────────────────────────────

class TestCorpusExporter:
    def _build_store(self) -> ExperienceStore:
        store = ExperienceStore()
        for i in range(20):
            store.add_trajectory(_traj(f"deploy_sandbox_{i}", success=True, score=0.85))
        for i in range(5):
            store.add_trajectory(_traj(f"failed_mission_{i}", success=False, score=0.3))
        return store

    def test_manifest_contains_all_keys(self):
        store = self._build_store()
        manifest = CorpusExporter.export(store, version_id="test_export_v1", fmt="instruction_tuning")
        for key in ("version_id", "pipeline", "counts", "dedup_stats", "split", "corpus_metrics", "token_report"):
            assert key in manifest, f"Missing manifest key: {key}"

    def test_pipeline_stages_reduce_record_count(self):
        store = self._build_store()
        manifest = CorpusExporter.export(store, version_id="test_export_v2", fmt="instruction_tuning")
        counts = manifest["counts"]
        # After quality filter, failed low-score trajectories are removed
        assert counts["after_quality_filter"] < counts["after_extraction"]

    def test_augmentation_expands_corpus(self):
        store = self._build_store()
        manifest = CorpusExporter.export(
            store,
            version_id="test_export_v3",
            fmt="instruction_tuning",
            augment_variants=2,
        )
        counts = manifest["counts"]
        # Augmentation should produce more records than dedup output
        assert counts["after_augmentation"] > counts["after_dedup"]

    def test_split_sizes_match_manifest(self):
        store = self._build_store()
        manifest = CorpusExporter.export(store, version_id="test_export_v4", fmt="planning")
        split = manifest["split"]
        total = split["train_count"] + split["val_count"] + split["test_count"]
        assert total == manifest["counts"]["after_augmentation"]

    def test_version_registered(self):
        store = self._build_store()
        CorpusExporter.export(store, version_id="test_export_v5", fmt="chain_of_thought")
        latest = DatasetVersioning.get_latest_version()
        assert latest is not None
        assert latest["version_id"] == "test_export_v5"
