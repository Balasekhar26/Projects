"""
Step 7.3 — Learning Dashboard Test Suite

Categories:
  1. Read-only guarantee: no write methods exist
  2. Executive summary: three panels in correct order
  3. EROI: production-anchored, formula, CI, insufficient-data handling
  4. Confidence bands: t-CI computation correctness
  5. Metric trust map: correct classification for all keys
  6. Proposals panel: structure and counts
  7. Experiments panel: structure and orphan count
  8. Benchmarks panel: floors and categories
  9. Research panel: trust levels and scores
  10. Protected Core registration
  11. API endpoints: all 7 GET routes return 200 with correct structure
  12. Alert thresholds: _alert_level() returns correct levels
"""
from __future__ import annotations

import inspect
import json
import math
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.learning_dashboard import (
    LearningDashboard,
    METRIC_TRUST,
    ALERT_THRESHOLDS,
    _ci,
    _alert_level,
    _t_critical,
)
from backend.core.proposal_governance import ProtectedCoreRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_store(tmp_path: Path, filename: str):
    """Patch a data store to point to an empty list file in tmp_path."""
    store = tmp_path / filename
    store.write_text("[]", encoding="utf-8")
    return store


def _patch_data(tmp_path: Path):
    """Context manager that patches all data stores to empty tmp files."""
    stores = [
        "proposals.json",
        "experiments_store.json",
        "benchmark_history.json",
        "research_results.json",
        "improvement_registry.json",
        "track_records.json",
        "canary_status.json",
        "approval_workflow.json",
        "capabilities.json",
    ]
    for s in stores:
        _empty_store(tmp_path, s)

    def _fake_data(filename: str):
        p = tmp_path / filename
        if not p.exists():
            return []
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []

    return patch("backend.core.learning_dashboard._data", side_effect=_fake_data)


# ---------------------------------------------------------------------------
# 1. Read-Only Guarantee
# ---------------------------------------------------------------------------

class TestReadOnlyGuarantee:
    def test_no_write_methods_on_learning_dashboard(self):
        """LearningDashboard must contain NO write methods."""
        # Use full-word token matching to avoid false positives like _compute_fnr containing 'put'
        WRITE_TOKENS = {"write", "save", "create", "update", "delete", "insert", "patch", "post"}
        for name, method in inspect.getmembers(LearningDashboard, predicate=inspect.ismethod):
            tokens = set(name.strip("_").lower().split("_"))
            bad = tokens & WRITE_TOKENS
            assert not bad, f"LearningDashboard.{name}() looks like a write method (tokens: {bad})"

    def test_no_private_write_methods(self):
        """Private methods should also not write."""
        for name, _ in inspect.getmembers(LearningDashboard, predicate=inspect.isfunction):
            assert not any(
                keyword in name.lower()
                for keyword in ("_write", "_save", "_create", "_delete", "_insert")
            ), f"LearningDashboard.{name}() looks like a write helper"

    def test_module_has_no_file_write_calls(self):
        """The learning_dashboard source should not contain .write_text or open(..., 'w')."""
        import backend.core.learning_dashboard as mod
        src = inspect.getsource(mod)
        assert "write_text" not in src, "learning_dashboard.py contains write_text()"
        assert "open(" not in src or "'w'" not in src, "learning_dashboard.py opens files for writing"

    def test_no_dashboard_post_endpoints_in_main(self):
        """No POST/PUT/DELETE endpoints exist under /dashboard/ in main.py."""
        client = TestClient(app)
        # These should all return 405 Method Not Allowed (no POST registered)
        for path in [
            "/dashboard/executive",
            "/dashboard/proposals",
            "/dashboard/experiments",
            "/dashboard/benchmarks",
            "/dashboard/research",
            "/dashboard/eroi",
            "/dashboard/metric-trust",
        ]:
            resp = client.post(path, json={})
            assert resp.status_code == 405, (
                f"POST {path} returned {resp.status_code}, expected 405"
            )


# ---------------------------------------------------------------------------
# 2. Executive Summary Structure
# ---------------------------------------------------------------------------

class TestExecutiveSummary:
    def test_three_panels_present(self, tmp_path):
        with _patch_data(tmp_path):
            with patch("backend.core.approval_workflow.ApprovalWorkflow.metrics", return_value={"AAR": None, "RAR": 0.0}):
                with patch("backend.core.approval_workflow.ApprovalWorkflow.list_all", return_value=[]):
                    with patch("backend.core.proposal_governance.ImprovementRegistry.get_stats", return_value={
                        "pipeline_rf": 0.0, "avg_gra": 0.0, "avg_iqs": 0.0,
                        "avg_pvs": 0.0, "pipeline_iy": 0.0, "pipeline_prr": 0.0,
                    }):
                        with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=[]):
                            result = LearningDashboard.executive_summary()

        assert "panels" in result
        assert len(result["panels"]) == 3

    def test_panels_in_correct_order(self, tmp_path):
        with _patch_data(tmp_path):
            with patch("backend.core.approval_workflow.ApprovalWorkflow.metrics", return_value={"AAR": None, "RAR": 0.0}):
                with patch("backend.core.approval_workflow.ApprovalWorkflow.list_all", return_value=[]):
                    with patch("backend.core.proposal_governance.ImprovementRegistry.get_stats", return_value={}):
                        with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=[]):
                            result = LearningDashboard.executive_summary()

        panels = result["panels"]
        assert panels[0]["id"] == "safety_governance", "Safety & Governance must be first"
        assert panels[1]["id"] == "learning_reality"
        assert panels[2]["id"] == "system_health"

    def test_panels_have_priority_field(self, tmp_path):
        with _patch_data(tmp_path):
            with patch("backend.core.approval_workflow.ApprovalWorkflow.metrics", return_value={"AAR": None, "RAR": 0.0}):
                with patch("backend.core.approval_workflow.ApprovalWorkflow.list_all", return_value=[]):
                    with patch("backend.core.proposal_governance.ImprovementRegistry.get_stats", return_value={}):
                        with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=[]):
                            result = LearningDashboard.executive_summary()

        priorities = [p["priority"] for p in result["panels"]]
        assert priorities == [1, 2, 3]

    def test_summary_contains_metric_trust(self, tmp_path):
        with _patch_data(tmp_path):
            with patch("backend.core.approval_workflow.ApprovalWorkflow.metrics", return_value={"AAR": None, "RAR": 0.0}):
                with patch("backend.core.approval_workflow.ApprovalWorkflow.list_all", return_value=[]):
                    with patch("backend.core.proposal_governance.ImprovementRegistry.get_stats", return_value={}):
                        with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=[]):
                            result = LearningDashboard.executive_summary()

        assert "metric_trust" in result
        assert result["metric_trust"] is METRIC_TRUST

    def test_safety_governance_has_required_metrics(self, tmp_path):
        with _patch_data(tmp_path):
            with patch("backend.core.approval_workflow.ApprovalWorkflow.metrics", return_value={"AAR": None, "RAR": 0.0}):
                with patch("backend.core.approval_workflow.ApprovalWorkflow.list_all", return_value=[]):
                    with patch("backend.core.proposal_governance.ImprovementRegistry.get_stats", return_value={"pipeline_rf": 0.05}):
                        with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=[]):
                            result = LearningDashboard.executive_summary()

        sg = result["panels"][0]
        metric_keys = {m["key"] for m in sg["metrics"]}
        assert "rollback_rate" in metric_keys
        assert "approval_error_rate" in metric_keys
        assert "protected_core_violations" in metric_keys
        assert "reviewer_backlog" in metric_keys

    def test_learning_reality_has_eroi(self, tmp_path):
        with _patch_data(tmp_path):
            with patch("backend.core.approval_workflow.ApprovalWorkflow.metrics", return_value={"AAR": None, "RAR": 0.0}):
                with patch("backend.core.approval_workflow.ApprovalWorkflow.list_all", return_value=[]):
                    with patch("backend.core.proposal_governance.ImprovementRegistry.get_stats", return_value={}):
                        with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=[]):
                            result = LearningDashboard.executive_summary()

        lr = result["panels"][1]
        metric_keys = {m["key"] for m in lr["metrics"]}
        assert "eroi" in metric_keys
        assert "sandbox_transfer_rate" in metric_keys
        assert "learning_velocity" in metric_keys
        assert "false_negative_rate" in metric_keys


# ---------------------------------------------------------------------------
# 3. Production-Anchored EROI
# ---------------------------------------------------------------------------

class TestERROI:
    def test_eroi_insufficient_with_no_data(self, tmp_path):
        with _patch_data(tmp_path):
            with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=[]):
                with patch("backend.core.proposal_governance.TrackRecordStore.get_track_records", return_value=[]):
                    result = LearningDashboard.eroi()

        assert result["insufficient"] is True
        assert result["eroi"] is None
        assert result["ci"]["n"] == 0

    def test_eroi_insufficient_with_one_datapoint(self, tmp_path):
        improvements = [{
            "final_outcome": "DEPLOYED_SUCCESSFUL",
            "production_gain": 10.0,
            "proposal_id": "p-1",
        }]
        with _patch_data(tmp_path):
            with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=improvements):
                with patch("backend.core.proposal_governance.TrackRecordStore.get_track_records", return_value=[]):
                    result = LearningDashboard.eroi()

        assert result["insufficient"] is True
        assert result["ci"]["n"] == 1
        # mean is computed even with n=1, but CI is not
        assert result["eroi"] is not None

    def test_eroi_computed_with_two_datapoints(self, tmp_path):
        improvements = [
            {"final_outcome": "DEPLOYED_SUCCESSFUL", "production_gain": 20.0, "proposal_id": "p-1"},
            {"final_outcome": "DEPLOYED_SUCCESSFUL", "production_gain": 10.0, "proposal_id": "p-2"},
        ]
        records = [
            {"proposal_id": "p-1", "research_cost": 5.0, "sandbox_cost": 2.0, "review_cost": 1.0},
            {"proposal_id": "p-2", "research_cost": 5.0, "sandbox_cost": 2.0, "review_cost": 1.0},
        ]
        with _patch_data(tmp_path):
            with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=improvements):
                with patch("backend.core.proposal_governance.TrackRecordStore.get_track_records", return_value=records):
                    result = LearningDashboard.eroi()

        assert result["insufficient"] is False
        assert result["eroi"] is not None
        assert result["ci"]["margin"] is not None
        # EROI for p-1: 20 / 8 = 2.5; p-2: 10 / 8 = 1.25; mean ≈ 1.875
        assert abs(result["eroi"] - 1.875) < 0.01

    def test_eroi_excludes_non_deployed(self, tmp_path):
        """EROI only counts DEPLOYED_SUCCESSFUL outcomes."""
        improvements = [
            {"final_outcome": "REJECTED", "production_gain": 99.0, "proposal_id": "p-rej"},
            {"final_outcome": "SANDBOX_FAILED", "production_gain": 50.0, "proposal_id": "p-sf"},
            {"final_outcome": "DEPLOYED_SUCCESSFUL", "production_gain": 10.0, "proposal_id": "p-ok"},
        ]
        records = [{"proposal_id": "p-ok", "research_cost": 10.0, "sandbox_cost": 0.0, "review_cost": 0.0}]
        with _patch_data(tmp_path):
            with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=improvements):
                with patch("backend.core.proposal_governance.TrackRecordStore.get_track_records", return_value=records):
                    result = LearningDashboard.eroi()

        # Only one valid datapoint — should be insufficient
        assert result["ci"]["n"] == 1

    def test_eroi_formula_in_response(self, tmp_path):
        """EROI response includes the protected formula string."""
        with _patch_data(tmp_path):
            with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=[]):
                with patch("backend.core.proposal_governance.TrackRecordStore.get_track_records", return_value=[]):
                    result = LearningDashboard.eroi()

        assert "formula" in result
        assert "production_gain" in result["formula"]
        assert "research_cost" in result["formula"]

    def test_eroi_excludes_sandbox_only_gain(self, tmp_path):
        """sandbox_gain without production_gain must not contribute to EROI."""
        improvements = [
            {"final_outcome": "DEPLOYED_SUCCESSFUL", "sandbox_gain": 100.0, "production_gain": None, "proposal_id": "p-sb"},
            {"final_outcome": "DEPLOYED_SUCCESSFUL", "production_gain": 5.0, "proposal_id": "p-ok"},
        ]
        with _patch_data(tmp_path):
            with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=improvements):
                with patch("backend.core.proposal_governance.TrackRecordStore.get_track_records", return_value=[]):
                    result = LearningDashboard.eroi()

        # Only p-ok qualifies; n=1 → insufficient
        assert result["ci"]["n"] == 1


# ---------------------------------------------------------------------------
# 4. Confidence Bands
# ---------------------------------------------------------------------------

class TestConfidenceBands:
    def test_ci_empty_list(self):
        result = _ci([])
        assert result["mean"] is None
        assert result["n"] == 0
        assert result["insufficient"] is True

    def test_ci_single_value(self):
        result = _ci([3.14])
        assert result["mean"] == 3.14
        assert result["n"] == 1
        assert result["margin"] is None
        assert result["insufficient"] is True

    def test_ci_two_values(self):
        result = _ci([1.0, 3.0])
        assert result["n"] == 2
        assert result["mean"] == 2.0
        assert result["margin"] is not None
        assert result["insufficient"] is False
        # df=1, t=12.706, std=1.414, se=1.0, margin=12.706
        assert abs(result["margin"] - 12.706) < 0.01

    def test_ci_five_values(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _ci(values)
        assert result["n"] == 5
        assert result["mean"] == 3.0
        assert result["margin"] is not None
        assert result["low"] == round(result["mean"] - result["margin"], 4)
        assert result["high"] == round(result["mean"] + result["margin"], 4)

    def test_ci_uses_t_distribution_not_z(self):
        """Small samples should use t-distribution (wider bands than z)."""
        values = [1.0, 2.0, 3.0, 4.0]   # df=3
        result = _ci(values)
        # z=1.96 would give narrower CI; t(df=3)=3.182 gives wider
        std = math.sqrt(sum((x - 2.5) ** 2 for x in values) / 3)
        se = std / math.sqrt(4)
        z_margin = 1.96 * se
        assert result["margin"] > z_margin, "t-CI should be wider than z-CI for n=4"

    def test_t_critical_known_values(self):
        """t-critical values should match statistical tables."""
        assert abs(_t_critical(1) - 12.706) < 0.001
        assert abs(_t_critical(4) - 2.776) < 0.001
        assert abs(_t_critical(30) - 2.042) < 0.001

    def test_t_critical_large_df_approaches_z(self):
        """For large df, t-critical should approach 1.96."""
        assert abs(_t_critical(100) - 1.96) < 0.1


# ---------------------------------------------------------------------------
# 5. Metric Trust Map
# ---------------------------------------------------------------------------

class TestMetricTrustMap:
    def test_trust_map_has_all_three_levels(self):
        result = LearningDashboard.metric_trust_map()
        by_trust = result["by_trust"]
        assert "MEASURED" in by_trust
        assert "DERIVED" in by_trust
        assert "PREDICTED" in by_trust

    def test_rollback_rate_is_measured(self):
        assert METRIC_TRUST["rollback_rate"] == "MEASURED"

    def test_human_approvals_is_measured(self):
        assert METRIC_TRUST["human_approvals"] == "MEASURED"

    def test_eroi_is_derived(self):
        assert METRIC_TRUST["eroi"] == "DERIVED"

    def test_gra_mean_is_derived(self):
        assert METRIC_TRUST["gra_mean"] == "DERIVED"

    def test_predicted_gain_is_predicted(self):
        assert METRIC_TRUST["predicted_gain"] == "PREDICTED"

    def test_sandbox_gain_is_predicted(self):
        assert METRIC_TRUST["sandbox_gain"] == "PREDICTED"

    def test_metric_trust_is_immutable_dict(self):
        """The trust map returned is the same hardcoded object."""
        result = LearningDashboard.metric_trust_map()
        assert result["classification"] is METRIC_TRUST

    def test_trust_map_note_mentions_protected_core(self):
        result = LearningDashboard.metric_trust_map()
        assert "Protected Core" in result["note"]

    def test_all_metric_keys_have_valid_trust_level(self):
        valid = {"MEASURED", "DERIVED", "PREDICTED"}
        for key, trust in METRIC_TRUST.items():
            assert trust in valid, f"Metric {key!r} has invalid trust level {trust!r}"


# ---------------------------------------------------------------------------
# 6. Proposals Panel
# ---------------------------------------------------------------------------

class TestProposalsPanel:
    def test_empty_store(self, tmp_path):
        with _patch_data(tmp_path):
            with patch("backend.core.approval_workflow.ApprovalWorkflow.list_all", return_value=[]):
                result = LearningDashboard.proposals_panel()

        assert result["total"] == 0
        assert result["proposals"] == []

    def test_counts_by_status(self, tmp_path):
        proposals = [
            {"id": "p-1", "title": "A", "status": "pending", "created_at": 1.0},
            {"id": "p-2", "title": "B", "status": "deployed", "created_at": 2.0},
            {"id": "p-3", "title": "C", "status": "rejected", "created_at": 3.0},
        ]

        def _fake(filename):
            if filename == "proposals.json":
                return proposals
            return []

        with patch("backend.core.learning_dashboard._data", side_effect=_fake):
            with patch("backend.core.approval_workflow.ApprovalWorkflow.list_all", return_value=[]):
                result = LearningDashboard.proposals_panel()

        assert result["total"] == 3
        assert result["by_status"]["pending"] == 1
        assert result["by_status"]["deployed"] == 1
        assert result["by_status"]["rejected"] == 1

    def test_backlog_counts_reviewing_records(self, tmp_path):
        approval_records = [
            {"state": "REVIEWING", "approval_id": "a-1"},
            {"state": "ELEVATED_REVIEW", "approval_id": "a-2"},
            {"state": "DEPLOYED", "approval_id": "a-3"},
        ]
        with _patch_data(tmp_path):
            with patch("backend.core.approval_workflow.ApprovalWorkflow.list_all", return_value=approval_records):
                result = LearningDashboard.proposals_panel()

        assert result["awaiting_review"] == 2
        assert result["elevated_review"] == 1

    def test_proposals_limited_to_20(self, tmp_path):
        proposals = [
            {"id": f"p-{i}", "status": "pending", "created_at": float(i)}
            for i in range(30)
        ]

        def _fake(filename):
            if filename == "proposals.json":
                return proposals
            return []

        with patch("backend.core.learning_dashboard._data", side_effect=_fake):
            with patch("backend.core.approval_workflow.ApprovalWorkflow.list_all", return_value=[]):
                result = LearningDashboard.proposals_panel()

        assert len(result["proposals"]) <= 20


# ---------------------------------------------------------------------------
# 7. Experiments Panel
# ---------------------------------------------------------------------------

class TestExperimentsPanel:
    def test_empty_experiments(self, tmp_path):
        with _patch_data(tmp_path):
            result = LearningDashboard.experiments_panel()

        assert result["total"] == 0
        assert result["orphan"] == 0
        assert result["sandbox_pass_rate"] is None

    def test_orphan_count(self, tmp_path):
        experiments = [
            {"id": "e-1", "status": "orphan", "created_at": 1.0},
            {"id": "e-2", "status": "orphan", "created_at": 2.0},
            {"id": "e-3", "status": "completed", "created_at": 3.0, "results": {"passed": True}},
        ]

        def _fake(filename):
            if filename == "experiments_store.json":
                return experiments
            return []

        with patch("backend.core.learning_dashboard._data", side_effect=_fake):
            result = LearningDashboard.experiments_panel()

        assert result["orphan"] == 2
        assert result["completed"] == 1

    def test_pass_rate_computed(self, tmp_path):
        experiments = [
            {"id": "e-1", "status": "completed", "results": {"passed": True}, "created_at": 1.0},
            {"id": "e-2", "status": "completed", "results": {"passed": False}, "created_at": 2.0},
        ]

        def _fake(filename):
            if filename == "experiments_store.json":
                return experiments
            return []

        with patch("backend.core.learning_dashboard._data", side_effect=_fake):
            result = LearningDashboard.experiments_panel()

        assert result["sandbox_pass_rate"] == 0.5


# ---------------------------------------------------------------------------
# 8. Benchmarks Panel
# ---------------------------------------------------------------------------

class TestBenchmarksPanel:
    def test_empty_history(self, tmp_path):
        with _patch_data(tmp_path):
            result = LearningDashboard.benchmarks_panel()

        assert result["categories"] == []
        assert result["total_runs"] == 0

    def test_floors_are_protected_core(self, tmp_path):
        with _patch_data(tmp_path):
            result = LearningDashboard.benchmarks_panel()

        floors = result["floors"]
        # These floors must match what's in CATEGORY_FLOORS of deployment_advisor
        assert floors["security"] == 0.95
        assert floors["planning"] == 0.85
        assert floors["memory"] == 0.80
        assert floors["coding"] == 0.80

    def test_below_floor_shows_critical(self, tmp_path):
        history = [
            {"category": "security", "score": 0.80, "timestamp": 1.0},
        ]

        def _fake(filename):
            if filename == "benchmark_history.json":
                return history
            return []

        with patch("backend.core.learning_dashboard._data", side_effect=_fake):
            result = LearningDashboard.benchmarks_panel()

        security_cat = next(c for c in result["categories"] if c["category"] == "security")
        assert security_cat["status"] == "critical"

    def test_above_floor_shows_ok(self, tmp_path):
        history = [
            {"category": "security", "score": 0.97, "timestamp": 1.0},
        ]

        def _fake(filename):
            if filename == "benchmark_history.json":
                return history
            return []

        with patch("backend.core.learning_dashboard._data", side_effect=_fake):
            result = LearningDashboard.benchmarks_panel()

        security_cat = next(c for c in result["categories"] if c["category"] == "security")
        assert security_cat["status"] == "ok"


# ---------------------------------------------------------------------------
# 9. Research Panel
# ---------------------------------------------------------------------------

class TestResearchPanel:
    def test_empty_research(self, tmp_path):
        with _patch_data(tmp_path):
            result = LearningDashboard.research_panel()

        assert result["total"] == 0
        assert result["avg_usefulness"] is None

    def test_trust_level_counts(self, tmp_path):
        results = [
            {"id": "r-1", "trust_level": "High", "usefulness_score": 80, "comparison": {}},
            {"id": "r-2", "trust_level": "Medium", "usefulness_score": 60, "comparison": {}},
            {"id": "r-3", "trust_level": "High", "usefulness_score": 90, "comparison": {}},
        ]

        def _fake(filename):
            if filename == "research_results.json":
                return results
            return []

        with patch("backend.core.learning_dashboard._data", side_effect=_fake):
            result = LearningDashboard.research_panel()

        assert result["by_trust"]["High"] == 2
        assert result["by_trust"]["Medium"] == 1
        assert result["avg_usefulness"] == pytest.approx((80 + 60 + 90) / 3, abs=0.1)

    def test_protected_core_touches_counted(self, tmp_path):
        results = [
            {"id": "r-1", "trust_level": "Low", "comparison": {"touches_protected_core": True}},
            {"id": "r-2", "trust_level": "Low", "comparison": {"touches_protected_core": False}},
        ]

        def _fake(filename):
            if filename == "research_results.json":
                return results
            return []

        with patch("backend.core.learning_dashboard._data", side_effect=_fake):
            result = LearningDashboard.research_panel()

        assert result["protected_core_touches"] == 1


# ---------------------------------------------------------------------------
# 10. Protected Core Registration
# ---------------------------------------------------------------------------

class TestProtectedCoreRegistration:
    def test_learning_dashboard_in_protected_modules(self):
        assert "learning_dashboard" in ProtectedCoreRegistry.PROTECTED_MODULES

    def test_approval_workflow_still_in_protected_modules(self):
        """Regression: approval_workflow must still be protected."""
        assert "approval_workflow" in ProtectedCoreRegistry.PROTECTED_MODULES

    def test_proposal_governance_still_in_protected_modules(self):
        assert "proposal_governance" in ProtectedCoreRegistry.PROTECTED_MODULES

    def test_is_transitively_protected_for_learning_dashboard(self):
        assert ProtectedCoreRegistry.is_transitively_protected("learning_dashboard") is True


# ---------------------------------------------------------------------------
# 11. Alert Levels
# ---------------------------------------------------------------------------

class TestAlertLevels:
    def test_rollback_rate_ok(self):
        assert _alert_level("rollback_rate", 0.05) == "ok"

    def test_rollback_rate_warn(self):
        assert _alert_level("rollback_rate", 0.15) == "warn"

    def test_rollback_rate_critical(self):
        assert _alert_level("rollback_rate", 0.30) == "critical"

    def test_eroi_ok(self):
        assert _alert_level("eroi", 1.5) == "ok"

    def test_eroi_warn(self):
        assert _alert_level("eroi", 0.70) == "warn"

    def test_eroi_critical(self):
        assert _alert_level("eroi", 0.30) == "critical"

    def test_unknown_metric_returns_ok(self):
        assert _alert_level("some_unknown_metric", 999.0) == "ok"

    def test_none_value_returns_unknown(self):
        assert _alert_level("rollback_rate", None) == "unknown"


# ---------------------------------------------------------------------------
# 12. API Endpoints
# ---------------------------------------------------------------------------

class TestDashboardAPI:
    def test_executive_endpoint(self, tmp_path):
        with _patch_data(tmp_path):
            with patch("backend.core.approval_workflow.ApprovalWorkflow.metrics", return_value={"AAR": None, "RAR": 0.0}):
                with patch("backend.core.approval_workflow.ApprovalWorkflow.list_all", return_value=[]):
                    with patch("backend.core.proposal_governance.ImprovementRegistry.get_stats", return_value={}):
                        with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=[]):
                            client = TestClient(app)
                            resp = client.get("/dashboard/executive")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "panels" in data["data"]
        assert len(data["data"]["panels"]) == 3

    def test_proposals_endpoint(self, tmp_path):
        with _patch_data(tmp_path):
            with patch("backend.core.approval_workflow.ApprovalWorkflow.list_all", return_value=[]):
                client = TestClient(app)
                resp = client.get("/dashboard/proposals")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "total" in data["data"]

    def test_experiments_endpoint(self, tmp_path):
        with _patch_data(tmp_path):
            client = TestClient(app)
            resp = client.get("/dashboard/experiments")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "total" in data["data"]

    def test_benchmarks_endpoint(self, tmp_path):
        with _patch_data(tmp_path):
            client = TestClient(app)
            resp = client.get("/dashboard/benchmarks")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "floors" in data["data"]

    def test_research_endpoint(self, tmp_path):
        with _patch_data(tmp_path):
            client = TestClient(app)
            resp = client.get("/dashboard/research")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "total" in data["data"]

    def test_eroi_endpoint(self, tmp_path):
        with _patch_data(tmp_path):
            with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=[]):
                with patch("backend.core.proposal_governance.TrackRecordStore.get_track_records", return_value=[]):
                    client = TestClient(app)
                    resp = client.get("/dashboard/eroi")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "formula" in data["data"]
        assert data["data"]["insufficient"] is True

    def test_metric_trust_endpoint(self):
        client = TestClient(app)
        resp = client.get("/dashboard/metric-trust")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        trust_data = data["data"]
        assert "classification" in trust_data
        assert "by_trust" in trust_data
        assert "MEASURED" in trust_data["by_trust"]
        assert "DERIVED" in trust_data["by_trust"]
        assert "PREDICTED" in trust_data["by_trust"]

    def test_all_dashboard_endpoints_get_only(self):
        """All dashboard routes must reject POST/PUT/DELETE."""
        client = TestClient(app)
        routes = [
            "/dashboard/executive",
            "/dashboard/proposals",
            "/dashboard/experiments",
            "/dashboard/benchmarks",
            "/dashboard/research",
            "/dashboard/eroi",
            "/dashboard/metric-trust",
        ]
        for route in routes:
            assert client.post(route, json={}).status_code == 405
            assert client.put(route, json={}).status_code in {405, 422}
            assert client.delete(route).status_code == 405
