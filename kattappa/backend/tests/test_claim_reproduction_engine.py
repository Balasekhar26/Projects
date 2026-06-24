"""Tests for Step 18: Claim Reproduction Engine."""

from __future__ import annotations

import uuid
import pytest
from unittest.mock import patch, MagicMock

from backend.core.claim_reproduction_engine import (
    ClaimReproductionEngine,
    ExperimentTemplate,
    ClaimReproductionResult,
    _COMPONENT_SUITE_MAP,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.claim_reproduction_engine as cre_module
    monkeypatch.setenv("KATTAPPA_DATA_DIR", str(tmp_path))
    cre_module._schema_ensured.clear()
    yield


@pytest.fixture
def sample_claim():
    return {
        "claim_id": f"clm_{uuid.uuid4().hex[:12]}",
        "paper_id": f"pap_{uuid.uuid4().hex[:12]}",
        "paper_title": "ActiveMem: Dynamic Memory Recall Enhancement",
        "component_target": "memory",
        "predicted_gain": 0.12,  # 12% claimed improvement
    }


# ── ExperimentTemplate building ───────────────────────────────────────────────

class TestBuildTemplate:

    def test_build_returns_template(self, sample_claim):
        template = ClaimReproductionEngine.build_template(**sample_claim)
        assert isinstance(template, ExperimentTemplate)
        assert template.claim_id == sample_claim["claim_id"]
        assert template.paper_id == sample_claim["paper_id"]

    def test_template_uses_correct_suite(self, sample_claim):
        template = ClaimReproductionEngine.build_template(**sample_claim)
        assert template.suite_id == "memory"
        assert template.metric_key == "recall_accuracy"

    def test_template_maps_conversation_component(self, sample_claim):
        sample_claim["component_target"] = "conversation"
        template = ClaimReproductionEngine.build_template(**sample_claim)
        assert template.suite_id == "conversation"
        assert template.metric_key == "context_retention"

    def test_template_maps_agent_component(self, sample_claim):
        sample_claim["component_target"] = "agent"
        template = ClaimReproductionEngine.build_template(**sample_claim)
        assert template.suite_id == "agent"
        assert template.metric_key == "planner_quality"

    def test_template_falls_back_to_default_for_unknown(self, sample_claim):
        sample_claim["component_target"] = "unknown_xyz"
        template = ClaimReproductionEngine.build_template(**sample_claim)
        assert template.suite_id == "agent"  # default

    def test_template_persisted_as_queued(self, sample_claim):
        template = ClaimReproductionEngine.build_template(**sample_claim)
        queued = ClaimReproductionEngine.list_queued()
        ids = [e["id"] for e in queued]
        assert template.experiment_id in ids

    def test_template_status_is_queued(self, sample_claim):
        template = ClaimReproductionEngine.build_template(**sample_claim)
        exp = ClaimReproductionEngine.get_experiment(template.experiment_id)
        assert exp is not None
        assert exp["status"] == "queued"

    def test_template_expected_delta_stored(self, sample_claim):
        template = ClaimReproductionEngine.build_template(**sample_claim)
        assert template.expected_delta == 0.12

    def test_two_templates_for_same_claim_are_distinct(self, sample_claim):
        t1 = ClaimReproductionEngine.build_template(**sample_claim)
        t2 = ClaimReproductionEngine.build_template(**sample_claim)
        assert t1.experiment_id != t2.experiment_id


# ── Component → suite mapping coverage ───────────────────────────────────────

class TestComponentMapping:

    def test_all_known_components_have_suite_configs(self):
        for component in ["memory", "conversation", "agent", "performance", "simulation"]:
            cfg = _COMPONENT_SUITE_MAP[component]
            assert "suite_id" in cfg
            assert "metric_key" in cfg
            assert cfg["suite_id"] != ""
            assert cfg["metric_key"] != ""


# ── ClaimReproductionResult ───────────────────────────────────────────────────

class TestClaimReproductionResult:

    def test_delta_ratio_zero_when_no_expected_delta(self):
        result = ClaimReproductionResult(
            experiment_id="e1",
            claim_id="c1",
            paper_id="p1",
            confirmed=False,
            baseline_score=90.0,
            challenger_score=90.0,
            actual_delta=0.0,
            expected_delta=0.0,
        )
        assert result.delta_ratio == 0.0

    def test_delta_ratio_one_when_exact_match(self):
        result = ClaimReproductionResult(
            experiment_id="e2",
            claim_id="c2",
            paper_id="p2",
            confirmed=True,
            baseline_score=80.0,
            challenger_score=89.6,
            actual_delta=0.12,
            expected_delta=0.12,
        )
        assert abs(result.delta_ratio - 1.0) < 0.001

    def test_delta_ratio_partial(self):
        result = ClaimReproductionResult(
            experiment_id="e3",
            claim_id="c3",
            paper_id="p3",
            confirmed=False,
            baseline_score=80.0,
            challenger_score=84.0,
            actual_delta=0.05,
            expected_delta=0.12,
        )
        assert abs(result.delta_ratio - (0.05 / 0.12)) < 0.001


# ── Execution (mocked suite calls) ───────────────────────────────────────────

class TestRunExecution:

    def _build(self, sample_claim):
        return ClaimReproductionEngine.build_template(**sample_claim)

    def test_run_marks_done_on_success(self, sample_claim):
        template = self._build(sample_claim)

        with patch.object(
            ClaimReproductionEngine, "_run_baseline", return_value=80.0
        ), patch.object(
            ClaimReproductionEngine, "_run_challenger", return_value=90.0
        ), patch.object(
            ClaimReproductionEngine, "_report_to_research_loop"
        ), patch.object(
            ClaimReproductionEngine, "_record_strategic_decision"
        ), patch.object(
            ClaimReproductionEngine, "_submit_to_governance"
        ):
            result = ClaimReproductionEngine.run(template.experiment_id)

        exp = ClaimReproductionEngine.get_experiment(template.experiment_id)
        assert exp["status"] == "done"
        assert result.baseline_score == 80.0
        assert result.challenger_score == 90.0

    def test_run_confirms_when_delta_meets_threshold(self, sample_claim):
        """12% claimed, 10% measured → 10/12 = 83% > 70% threshold → confirmed."""
        sample_claim["predicted_gain"] = 0.12
        template = self._build(sample_claim)

        with patch.object(
            ClaimReproductionEngine, "_run_baseline", return_value=100.0
        ), patch.object(
            ClaimReproductionEngine, "_run_challenger", return_value=110.0
        ), patch.object(ClaimReproductionEngine, "_report_to_research_loop"), \
           patch.object(ClaimReproductionEngine, "_record_strategic_decision"), \
           patch.object(ClaimReproductionEngine, "_submit_to_governance"):
            result = ClaimReproductionEngine.run(template.experiment_id)

        assert result.confirmed is True
        assert result.actual_delta == pytest.approx(0.10, abs=0.001)

    def test_run_rejects_when_delta_too_small(self, sample_claim):
        """12% claimed, 2% measured → 2/12 = 16% < 70% threshold → not confirmed."""
        sample_claim["predicted_gain"] = 0.12
        template = self._build(sample_claim)

        with patch.object(
            ClaimReproductionEngine, "_run_baseline", return_value=100.0
        ), patch.object(
            ClaimReproductionEngine, "_run_challenger", return_value=102.0
        ), patch.object(ClaimReproductionEngine, "_report_to_research_loop"), \
           patch.object(ClaimReproductionEngine, "_record_strategic_decision"), \
           patch.object(ClaimReproductionEngine, "_submit_to_governance"):
            result = ClaimReproductionEngine.run(template.experiment_id)

        assert result.confirmed is False

    def test_run_does_not_submit_to_governance_when_not_confirmed(self, sample_claim):
        """Unconfirmed claims must never reach governance."""
        template = self._build(sample_claim)

        with patch.object(
            ClaimReproductionEngine, "_run_baseline", return_value=100.0
        ), patch.object(
            ClaimReproductionEngine, "_run_challenger", return_value=101.0
        ), patch.object(ClaimReproductionEngine, "_report_to_research_loop"), \
           patch.object(ClaimReproductionEngine, "_record_strategic_decision"), \
           patch.object(ClaimReproductionEngine, "_submit_to_governance") as mock_gov:
            ClaimReproductionEngine.run(template.experiment_id)

        mock_gov.assert_not_called()

    def test_run_submits_to_governance_when_confirmed(self, sample_claim):
        sample_claim["predicted_gain"] = 0.10
        template = self._build(sample_claim)

        with patch.object(
            ClaimReproductionEngine, "_run_baseline", return_value=100.0
        ), patch.object(
            ClaimReproductionEngine, "_run_challenger", return_value=111.0
        ), patch.object(ClaimReproductionEngine, "_report_to_research_loop"), \
           patch.object(ClaimReproductionEngine, "_record_strategic_decision"), \
           patch.object(ClaimReproductionEngine, "_submit_to_governance") as mock_gov:
            ClaimReproductionEngine.run(template.experiment_id)

        mock_gov.assert_called_once()

    def test_run_raises_for_unknown_experiment(self):
        with pytest.raises(ValueError, match="No experiment found"):
            ClaimReproductionEngine.run("nonexistent_id")

    def test_list_queued_returns_only_queued(self, sample_claim):
        t1 = self._build(sample_claim)
        sample_claim2 = {**sample_claim, "claim_id": f"clm_{uuid.uuid4().hex[:8]}"}
        t2 = self._build(sample_claim2)

        with patch.object(ClaimReproductionEngine, "_run_baseline", return_value=80.0), \
             patch.object(ClaimReproductionEngine, "_run_challenger", return_value=80.0), \
             patch.object(ClaimReproductionEngine, "_report_to_research_loop"), \
             patch.object(ClaimReproductionEngine, "_record_strategic_decision"), \
             patch.object(ClaimReproductionEngine, "_submit_to_governance"):
            ClaimReproductionEngine.run(t1.experiment_id)

        queued = ClaimReproductionEngine.list_queued()
        queued_ids = [e["id"] for e in queued]
        assert t2.experiment_id in queued_ids
        assert t1.experiment_id not in queued_ids
