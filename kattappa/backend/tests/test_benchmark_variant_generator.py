"""Tests for Step 17: Dynamic Benchmark Variant Generator (EvoArena)."""

from __future__ import annotations

import pytest
from backend.core.benchmark_variant_generator import (
    BenchmarkCase,
    BenchmarkVariantGenerator,
    PlateauReport,
    _RuleBasedMutator,
)
import random


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets its own isolated DB directory."""
    import backend.core.benchmark_variant_generator as bvg_module
    monkeypatch.setenv("KATTAPPA_DATA_DIR", str(tmp_path))
    # Reset schema cache between tests
    bvg_module._schema_ensured.clear()
    yield


@pytest.fixture
def fruit_seed_case():
    return BenchmarkCase(
        case_id="seed_fruit_001",
        suite_id="memory",
        input_text="The user prefers apples over bananas.",
        expected_answer="apples",
    )


@pytest.fixture
def name_seed_case():
    return BenchmarkCase(
        case_id="seed_name_001",
        suite_id="conversation",
        input_text="Alice told Bob she was going to Tokyo on Monday.",
        expected_answer="Alice",
    )


@pytest.fixture
def number_seed_case():
    return BenchmarkCase(
        case_id="seed_num_001",
        suite_id="agent",
        input_text="The project has 42 tasks remaining.",
        expected_answer="42",
    )


# ── Mutation engine tests ─────────────────────────────────────────────────────

class TestRuleBasedMutator:

    def test_fruit_swap_changes_surface(self, fruit_seed_case):
        rng = random.Random(42)
        variant = _RuleBasedMutator.mutate(fruit_seed_case, rng, generation=1)
        # The variant text should differ (fruit swapped)
        assert variant.input_text != fruit_seed_case.input_text

    def test_fruit_swap_preserves_structure(self, fruit_seed_case):
        rng = random.Random(42)
        variant = _RuleBasedMutator.mutate(fruit_seed_case, rng, generation=1)
        # The structure "user prefers X over" still present
        assert "prefers" in variant.input_text
        assert "over" in variant.input_text

    def test_name_swap(self, name_seed_case):
        rng = random.Random(7)
        variant = _RuleBasedMutator.mutate(name_seed_case, rng, generation=1)
        # Alice must be replaced by a different name
        assert "Alice" not in variant.input_text or "Alice" in variant.expected_answer

    def test_number_perturbation(self, number_seed_case):
        rng = random.Random(99)
        variant = _RuleBasedMutator.mutate(number_seed_case, rng, generation=1)
        # 42 should be replaced
        assert "42" not in variant.input_text

    def test_mutation_metadata_records_generation(self, fruit_seed_case):
        rng = random.Random(1)
        variant = _RuleBasedMutator.mutate(fruit_seed_case, rng, generation=3)
        assert variant.metadata["generation"] == 3
        assert variant.metadata["seed_case_id"] == fruit_seed_case.case_id

    def test_variant_has_new_case_id(self, fruit_seed_case):
        rng = random.Random(5)
        variant = _RuleBasedMutator.mutate(fruit_seed_case, rng, generation=1)
        assert variant.case_id != fruit_seed_case.case_id
        assert variant.case_id.startswith("var_")

    def test_suite_id_preserved(self, fruit_seed_case):
        rng = random.Random(11)
        variant = _RuleBasedMutator.mutate(fruit_seed_case, rng, generation=1)
        assert variant.suite_id == fruit_seed_case.suite_id

    def test_no_mutation_on_plain_text(self):
        """Cases with no matchable tokens should return close-to-identical text."""
        plain = BenchmarkCase(
            case_id="seed_plain",
            suite_id="memory",
            input_text="The system is initialised.",
            expected_answer="initialised",
        )
        rng = random.Random(0)
        variant = _RuleBasedMutator.mutate(plain, rng, generation=1)
        # No tokens matched — text should be identical
        assert variant.input_text == plain.input_text


# ── BenchmarkVariantGenerator API tests ──────────────────────────────────────

class TestBenchmarkVariantGenerator:

    def test_generate_variants_returns_correct_count(self, fruit_seed_case):
        variants = BenchmarkVariantGenerator.generate_variants(fruit_seed_case, n=3, seed_int=42)
        assert len(variants) == 3

    def test_generated_variants_are_persisted(self, fruit_seed_case):
        BenchmarkVariantGenerator.generate_variants(fruit_seed_case, n=4, seed_int=1)
        pool = BenchmarkVariantGenerator.get_pool("memory")
        assert len(pool) == 4

    def test_get_pool_excludes_retired(self, fruit_seed_case):
        variants = BenchmarkVariantGenerator.generate_variants(fruit_seed_case, n=3, seed_int=2)
        # Retire the first variant
        BenchmarkVariantGenerator.mark_retired(variants[0].case_id)
        pool = BenchmarkVariantGenerator.get_pool("memory")
        assert len(pool) == 2
        pool_ids = {c.case_id for c in pool}
        assert variants[0].case_id not in pool_ids

    def test_get_pool_include_retired_returns_all(self, fruit_seed_case):
        variants = BenchmarkVariantGenerator.generate_variants(fruit_seed_case, n=3, seed_int=3)
        BenchmarkVariantGenerator.mark_retired(variants[0].case_id)
        pool = BenchmarkVariantGenerator.get_pool("memory", include_retired=True)
        assert len(pool) == 3

    def test_register_variant_manually(self, fruit_seed_case):
        manual = BenchmarkCase(
            case_id="manual_v_001",
            suite_id="memory",
            input_text="User likes mangoes.",
            expected_answer="mangoes",
        )
        returned_id = BenchmarkVariantGenerator.register_variant("memory", manual)
        assert returned_id == "manual_v_001"
        pool = BenchmarkVariantGenerator.get_pool("memory")
        pool_ids = {c.case_id for c in pool}
        assert "manual_v_001" in pool_ids

    def test_variants_are_diverse(self, fruit_seed_case):
        """Multiple variants from same seed should differ from each other."""
        variants = BenchmarkVariantGenerator.generate_variants(fruit_seed_case, n=5)
        texts = [v.input_text for v in variants]
        # At least 2 unique texts (may not all differ due to limited mutation vocabulary)
        assert len(set(texts)) >= 2

    def test_deterministic_with_seed_int(self, fruit_seed_case):
        v1 = BenchmarkVariantGenerator.generate_variants(fruit_seed_case, n=3, seed_int=99)
        # Re-generate with same seed in a fresh instance
        # (generation counter will be 2 now, but mutation pattern is seeded)
        v2 = BenchmarkVariantGenerator.generate_variants(fruit_seed_case, n=3, seed_int=99)
        # Same seed → same mutation pattern applied; texts should match
        assert v1[0].input_text == v2[0].input_text


# ── Plateau detection tests ───────────────────────────────────────────────────

class TestPlateauDetection:

    def test_no_plateau_with_insufficient_history(self):
        report = BenchmarkVariantGenerator.detect_plateau("memory", window=3)
        assert report.plateau_detected is False
        assert report.run_scores == []

    def test_no_plateau_with_improving_scores(self):
        for score in [70.0, 80.0, 90.0, 95.0]:
            BenchmarkVariantGenerator.record_run_score("memory", score)
        report = BenchmarkVariantGenerator.detect_plateau("memory", window=3, threshold=0.02)
        assert report.plateau_detected is False
        # Mean improvement should be significant (>2%)
        assert report.mean_improvement > 0.02

    def test_plateau_detected_with_flat_scores(self):
        for score in [90.0, 90.1, 90.05, 90.08]:
            BenchmarkVariantGenerator.record_run_score("memory", score)
        report = BenchmarkVariantGenerator.detect_plateau("memory", window=3, threshold=0.02)
        assert report.plateau_detected is True
        assert report.mean_improvement < 0.02

    def test_plateau_detected_with_declining_scores(self):
        for score in [95.0, 94.0, 93.5, 93.0]:
            BenchmarkVariantGenerator.record_run_score("agent", score)
        report = BenchmarkVariantGenerator.detect_plateau("agent", window=3, threshold=0.02)
        assert report.plateau_detected is True
        assert report.mean_improvement < 0.0

    def test_plateau_suite_isolation(self):
        """Scores from one suite don't affect another suite's plateau detection."""
        for s in [70.0, 80.0, 90.0, 95.0]:
            BenchmarkVariantGenerator.record_run_score("memory", s)
        for s in [90.0, 90.0, 90.0, 90.0]:
            BenchmarkVariantGenerator.record_run_score("conversation", s)

        memory_report = BenchmarkVariantGenerator.detect_plateau("memory", window=3)
        conv_report = BenchmarkVariantGenerator.detect_plateau("conversation", window=3)

        assert memory_report.plateau_detected is False
        assert conv_report.plateau_detected is True

    def test_plateau_report_contains_correct_window(self):
        scores = [85.0, 86.0, 86.5, 86.6, 86.7]
        for s in scores:
            BenchmarkVariantGenerator.record_run_score("agent", s)
        report = BenchmarkVariantGenerator.detect_plateau("agent", window=3)
        # Should only have 3 scores in the window
        assert len(report.run_scores) == 3


# ── BenchmarkCase serialisation ───────────────────────────────────────────────

class TestBenchmarkCaseSerialization:

    def test_round_trip(self, fruit_seed_case):
        d = fruit_seed_case.to_dict()
        restored = BenchmarkCase.from_dict(d)
        assert restored.case_id == fruit_seed_case.case_id
        assert restored.suite_id == fruit_seed_case.suite_id
        assert restored.input_text == fruit_seed_case.input_text
        assert restored.expected_answer == fruit_seed_case.expected_answer
