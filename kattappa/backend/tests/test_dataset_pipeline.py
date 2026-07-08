"""Unit tests for Program 26.0: Dataset Generation Pipeline.

Verifies trace extraction, quality filtering, curriculum ordering, augmentation,
dataset building, versioning, and metric computations.
"""
from __future__ import annotations

import pytest
from backend.core.learning.trajectory_builder import Trajectory
from backend.core.dataset.trace_extractor import TraceExtractor
from backend.core.dataset.quality_filter import QualityFilter
from backend.core.dataset.curriculum_generator import CurriculumGenerator
from backend.core.dataset.synthetic_augmentation import SyntheticAugmentation
from backend.core.dataset.dataset_builder import DatasetBuilder
from backend.core.dataset.dataset_versioning import DatasetVersioning
from backend.core.dataset.dataset_metrics import DatasetMetrics


@pytest.fixture(autouse=True)
def clean_versions():
    DatasetVersioning.reset()
    yield
    DatasetVersioning.reset()


def _make_traj(
    goal_id: str = "deploy_docker_sandbox",
    success: bool = True,
    score: float = 0.85,
    nodes: list[str] | None = None,
    failures: int = 0,
    recoveries: int = 0,
    duration: float = 12.0,
    cost: float = 0.02,
) -> Trajectory:
    return Trajectory(
        goal_id=goal_id,
        plan_id="plan-01",
        planner_version="HTN-v2",
        success=success,
        predicted_duration=10.0,
        actual_duration=duration,
        predicted_cost=0.015,
        actual_cost=cost,
        failures_count=failures,
        recoveries_count=recoveries,
        combined_score=score,
    nodes_executed=nodes if nodes is not None else ["create_sandbox_manager", "create_resource_limiter", "run_tests"],
    )


# ── 1. Trace Extractor ────────────────────────────────────────────────────────

class TestTraceExtractor:
    def test_successful_extraction(self):
        t = _make_traj()
        rec = TraceExtractor.extract(t)
        assert rec["instruction"] == "deploy_docker_sandbox"
        assert rec["result"] == "success"
        assert rec["actions"] == ["create_sandbox_manager", "create_resource_limiter", "run_tests"]
        assert rec["metrics"]["cost"] == 0.02
        assert "create_sandbox_manager" in rec["reasoning_trace"]

    def test_recovered_result_label(self):
        t = _make_traj(success=True, recoveries=1)
        rec = TraceExtractor.extract(t)
        assert rec["result"] == "recovered"

    def test_failure_result_label(self):
        t = _make_traj(success=False, score=0.1)
        rec = TraceExtractor.extract(t)
        assert rec["result"] == "failure"

    def test_batch_extraction(self):
        trajs = [_make_traj("g1"), _make_traj("g2"), _make_traj("g3")]
        records = TraceExtractor.extract_all(trajs)
        assert len(records) == 3


# ── 2. Quality Filter ─────────────────────────────────────────────────────────

class TestQualityFilter:
    def _records(self):
        return [
            TraceExtractor.extract(_make_traj("high_quality", success=True, score=0.9)),
            TraceExtractor.extract(_make_traj("low_quality", success=True, score=0.3)),
            TraceExtractor.extract(_make_traj("failed_task", success=False, score=0.6, nodes=["step_a"])),
            TraceExtractor.extract(_make_traj("no_actions", success=True, score=0.8, nodes=[])),
        ]

    def test_default_filter_removes_low_score_and_failures(self):
        passed = QualityFilter.filter(self._records())
        instructions = [r["instruction"] for r in passed]
        assert "high_quality" in instructions
        assert "low_quality" not in instructions
        assert "failed_task" not in instructions
        assert "no_actions" not in instructions

    def test_allow_failed_flag(self):
        passed = QualityFilter.filter(self._records(), allow_failed=True)
        instructions = [r["instruction"] for r in passed]
        assert "failed_task" in instructions

    def test_require_actions_false(self):
        passed = QualityFilter.filter(self._records(), require_actions=False)
        instructions = [r["instruction"] for r in passed]
        assert "no_actions" in instructions


# ── 3. Curriculum Generator ───────────────────────────────────────────────────

class TestCurriculumGenerator:
    def test_sorted_ascending_complexity(self):
        records = [
            TraceExtractor.extract(_make_traj("complex_mission", nodes=["a"] * 8, failures=2, recoveries=1, cost=0.5)),
            TraceExtractor.extract(_make_traj("simple_task", nodes=["a"], failures=0, recoveries=0, cost=0.0)),
            TraceExtractor.extract(_make_traj("medium_task", nodes=["a", "b", "c"], failures=0, cost=0.05)),
        ]
        sorted_recs = CurriculumGenerator.sort(records)
        assert sorted_recs[0]["instruction"] == "simple_task"
        assert sorted_recs[-1]["instruction"] == "complex_mission"

    def test_difficulty_labels(self):
        simple = TraceExtractor.extract(_make_traj("s", nodes=["a"], failures=0, cost=0.0))
        complex_ = TraceExtractor.extract(_make_traj("c", nodes=["a"] * 10, failures=3, cost=1.0))
        assert CurriculumGenerator.label_difficulty(simple) == "simple"
        assert CurriculumGenerator.label_difficulty(complex_) == "complex"


# ── 4. Synthetic Augmentation ─────────────────────────────────────────────────

class TestSyntheticAugmentation:
    def test_augment_doubles_records(self):
        records = [TraceExtractor.extract(_make_traj("deploy_service"))]
        augmented = SyntheticAugmentation.augment(records, variants_per_record=2)
        # 1 original + 2 variants = 3
        assert len(augmented) == 3

    def test_augmented_instructions_differ(self):
        records = [TraceExtractor.extract(_make_traj("create a Docker sandbox"))]
        augmented = SyntheticAugmentation.augment(records, variants_per_record=3)
        instructions = [r["instruction"] for r in augmented]
        # All 4 instructions should be distinct
        assert len(set(instructions)) == len(instructions)

    def test_augmented_flag_set(self):
        records = [TraceExtractor.extract(_make_traj("run tests"))]
        augmented = SyntheticAugmentation.augment(records, variants_per_record=1)
        originals = [r for r in augmented if not r.get("augmented")]
        variants = [r for r in augmented if r.get("augmented")]
        assert len(originals) == 1
        assert len(variants) == 1


# ── 5. Dataset Builder ────────────────────────────────────────────────────────

class TestDatasetBuilder:
    def test_instruction_tuning_format(self):
        records = [TraceExtractor.extract(_make_traj("build_api"))]
        samples = DatasetBuilder.build(records, fmt="instruction_tuning", version_id="test_v1")
        assert len(samples) == 1
        assert "instruction" in samples[0]
        assert "output" in samples[0]

    def test_planning_format(self):
        records = [TraceExtractor.extract(_make_traj("plan_deployment"))]
        samples = DatasetBuilder.build(records, fmt="planning", version_id="test_v2")
        assert "goal" in samples[0]
        assert "plan_steps" in samples[0]
        assert isinstance(samples[0]["plan_steps"], list)

    def test_tool_calling_format(self):
        records = [TraceExtractor.extract(_make_traj("run_automation"))]
        samples = DatasetBuilder.build(records, fmt="tool_calling", version_id="test_v3")
        assert "tool_calls" in samples[0]


# ── 6. Dataset Versioning ─────────────────────────────────────────────────────

class TestDatasetVersioning:
    def test_register_and_retrieve_version(self):
        entry = DatasetVersioning.register_version(
            version_id="v1.0.0",
            sample_count=500,
            fmt="instruction_tuning",
            source_trajectory_count=200,
            notes="Initial corpus build",
        )
        assert entry["version_id"] == "v1.0.0"
        assert entry["sample_count"] == 500

        latest = DatasetVersioning.get_latest_version()
        assert latest["version_id"] == "v1.0.0"


# ── 7. Dataset Metrics ────────────────────────────────────────────────────────

class TestDatasetMetrics:
    def test_compute_balanced_corpus(self):
        records = [
            TraceExtractor.extract(_make_traj("task_a", success=True, score=0.9)),
            TraceExtractor.extract(_make_traj("task_b", success=True, score=0.8)),
            TraceExtractor.extract(_make_traj("task_c", success=False, score=0.6)),
        ]
        metrics = DatasetMetrics.compute(records)
        assert metrics["total_samples"] == 3
        assert metrics["success_count"] == 2
        assert metrics["failure_count"] == 1
        assert 0.0 < metrics["vocabulary_diversity"] <= 1.0
        assert metrics["avg_action_count"] > 0

    def test_empty_records(self):
        metrics = DatasetMetrics.compute([])
        assert metrics["total_samples"] == 0
        assert metrics["balance_ratio"] == 0.0
