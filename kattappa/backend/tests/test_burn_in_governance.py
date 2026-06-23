"""
Step 8.0 — Operational Burn-In Telemetry & Freeze Rules Test Suite
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.burn_in_governance import (
    BurnInGovernance,
    ResearchDebtLedger,
    PredictionReliabilityTracker,
    _state_path,
    _history_path,
)
from backend.core.proposal_engine import ProposalEngine
from backend.core.experiment_sandbox import ExperimentManager
from backend.core.approval_workflow import ApprovalWorkflow
from backend.core.proposal_governance import ProtectedCoreRegistry, ProposalStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_burn_in_stores(tmp_path):
    """Fixture to patch state and history path to temp files for isolation."""
    temp_state = tmp_path / "burn_in_state.json"
    temp_history = tmp_path / "burn_in_history.json"

    with patch("backend.core.burn_in_governance._state_path", return_value=temp_state), \
         patch("backend.core.burn_in_governance._history_path", return_value=temp_history):
        # Initialize as NORMAL
        temp_state.write_text(json.dumps({"state": "NORMAL", "active_freezes": []}), encoding="utf-8")
        temp_history.write_text("[]", encoding="utf-8")
        yield


# ---------------------------------------------------------------------------
# 1. State Machine & Overrides
# ---------------------------------------------------------------------------

class TestBurnInStateMachine:
    def test_default_state_is_normal(self):
        assert BurnInGovernance.is_frozen() is False
        assert BurnInGovernance.get_state()["state"] == "NORMAL"

    def test_human_reset_successful(self):
        # Force AUDIT state
        BurnInGovernance._save_state("AUDIT", ["Mock freeze"])
        assert BurnInGovernance.is_frozen() is True

        # Human resets it
        BurnInGovernance.reset_audit_mode("Alice Smith")
        assert BurnInGovernance.is_frozen() is False
        assert BurnInGovernance.get_state()["state"] == "NORMAL"

    def test_system_reset_fails(self):
        # Force AUDIT state
        BurnInGovernance._save_state("AUDIT", ["Mock freeze"])

        # System reset should raise ValueError
        with pytest.raises(ValueError, match="System actors may never override a freeze"):
            BurnInGovernance.reset_audit_mode("system")
        with pytest.raises(ValueError):
            BurnInGovernance.reset_audit_mode("")

        assert BurnInGovernance.is_frozen() is True


# ---------------------------------------------------------------------------
# 2. Block Enforcement Points
# ---------------------------------------------------------------------------

class TestFreezeBlocks:
    def test_create_proposal_blocked_when_frozen(self):
        BurnInGovernance._save_state("AUDIT", ["Mock freeze"])
        
        # Call create_proposal
        res = ProposalEngine.create_proposal(
            title="Fix cache",
            problem="Latency issue",
            evidence="Profile logs",
            proposal="Add index",
            expected_gain=1.5,
            complexity=1,
            confidence=90,
        )
        assert res["status"] == "rejected"
        assert "disabled in Audit Mode" in res["reasons"][0]

    def test_execute_experiment_blocked_when_frozen(self):
        BurnInGovernance._save_state("AUDIT", ["Mock freeze"])

        with pytest.raises(PermissionError, match="disabled in Audit Mode"):
            ExperimentManager.execute_experiment("prop_1")

    def test_deploy_blocked_when_frozen(self):
        BurnInGovernance._save_state("AUDIT", ["Mock freeze"])

        with pytest.raises(PermissionError, match="disabled in Audit Mode"):
            ApprovalWorkflow.deploy("app_123", "Alice")


# ---------------------------------------------------------------------------
# 3. Research Debt & Reliability Ledger Math
# ---------------------------------------------------------------------------

class TestLedgersAndTrackers:
    def test_research_debt_calculations(self):
        mock_improvements = [
            {"proposal_id": "p-1", "final_outcome": "DEPLOYED_SUCCESSFUL", "production_gain": 150.0},
            {"proposal_id": "p-2", "final_outcome": "DEPLOYED_SUCCESSFUL", "production_gain": 50.0},
            {"proposal_id": "p-3", "final_outcome": "REJECTED", "production_gain": 500.0}, # non-deployed should be ignored
        ]
        mock_track_records = [
            {"proposal_id": "p-1", "research_cost": 50.0, "sandbox_cost": 20.0, "review_cost": 10.0}, # cost = 80
            {"proposal_id": "p-2", "research_cost": 40.0, "sandbox_cost": 20.0, "review_cost": 10.0}, # cost = 70
            {"proposal_id": "p-3", "research_cost": 100.0, "sandbox_cost": 50.0, "review_cost": 20.0}, # cost = 170
        ]
        # Total cost = 80 + 70 + 170 = 320
        # Total gains = 150 + 50 = 200
        # Debt = 320 - 200 = 120 (accumulating = True)

        with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=mock_improvements), \
             patch("backend.core.proposal_governance.TrackRecordStore.get_track_records", return_value=mock_track_records):
            report = ResearchDebtLedger.get_debt_report()
            assert report["total_costs"] == 320.0
            assert report["total_gains"] == 200.0
            assert report["research_debt"] == 120.0
            assert report["debt_accumulating"] is True

    def test_prediction_reliability_error(self):
        mock_improvements = [
            {"proposal_id": "p-1", "final_outcome": "DEPLOYED_SUCCESSFUL", "production_gain": 12.0, "predicted_gain": 15.0}, # error = 3
            {"proposal_id": "p-2", "final_outcome": "DEPLOYED_SUCCESSFUL", "production_gain": 20.0}, # error = 5 (cost map below has 25)
        ]
        mock_track_records = [
            {"proposal_id": "p-2", "predicted_gain": 25.0},
        ]

        with patch("backend.core.proposal_governance.ImprovementRegistry.get_improvements", return_value=mock_improvements), \
             patch("backend.core.proposal_governance.TrackRecordStore.get_track_records", return_value=mock_track_records):
            report = PredictionReliabilityTracker.get_reliability_report()
            # p-1 error: abs(15 - 12) = 3
            # p-2 error: abs(25 - 20) = 5
            # avg error = (3 + 5) / 2 = 4.0
            assert report["average_prediction_error"] == 4.0
            assert report["total_audited_predictions"] == 2


# ---------------------------------------------------------------------------
# 4. Weekly Trend checks & Freeze Triggers
# ---------------------------------------------------------------------------

class TestWeeklyFreezeTriggers:
    def test_economic_failure_eroi_less_than_one(self):
        # 4 weeks of EROI < 1.0
        history = [
            {"week_index": 1, "production_eroi": 0.8},
            {"week_index": 2, "production_eroi": 0.7},
            {"week_index": 3, "production_eroi": 0.9},
            {"week_index": 4, "production_eroi": 0.5},
        ]
        BurnInGovernance._save_snapshots(history)
        triggers = BurnInGovernance.evaluate_freeze_rules()
        assert len(triggers) == 1
        assert "Economic Failure" in triggers[0]

    def test_economic_failure_not_triggered_with_good_week(self):
        # 3 weeks bad, 1 week good
        history = [
            {"week_index": 1, "production_eroi": 0.8},
            {"week_index": 2, "production_eroi": 1.2},
            {"week_index": 3, "production_eroi": 0.7},
            {"week_index": 4, "production_eroi": 0.5},
        ]
        BurnInGovernance._save_snapshots(history)
        triggers = BurnInGovernance.evaluate_freeze_rules()
        assert not any("Economic Failure" in t for t in triggers)

    def test_safety_failure_rising_rollback_rate(self):
        # 5 weeks of snapshots showing 4 consecutive transitions of rising rollbacks
        history = [
            {"week_index": 1, "rollback_rate": 0.05},
            {"week_index": 2, "rollback_rate": 0.07}, # transition 1
            {"week_index": 3, "rollback_rate": 0.10}, # transition 2
            {"week_index": 4, "rollback_rate": 0.12}, # transition 3
            {"week_index": 5, "rollback_rate": 0.15}, # transition 4
        ]
        BurnInGovernance._save_snapshots(history)
        triggers = BurnInGovernance.evaluate_freeze_rules()
        assert len(triggers) == 1
        assert "Safety Failure" in triggers[0]

    def test_governance_failure_rising_approval_error_rate(self):
        # 5 weeks showing 4 consecutive rises in approval error rate
        history = [
            {"week_index": 1, "approval_error_rate": 0.01},
            {"week_index": 2, "approval_error_rate": 0.02},
            {"week_index": 3, "approval_error_rate": 0.03},
            {"week_index": 4, "approval_error_rate": 0.04},
            {"week_index": 5, "approval_error_rate": 0.06},
        ]
        BurnInGovernance._save_snapshots(history)
        triggers = BurnInGovernance.evaluate_freeze_rules()
        assert len(triggers) == 1
        assert "Governance Failure" in triggers[0]

    def test_research_failure_falling_transfer_rate(self):
        # 5 weeks showing 4 consecutive falls in transfer rate
        history = [
            {"week_index": 1, "transfer_rate": 0.90},
            {"week_index": 2, "transfer_rate": 0.85},
            {"week_index": 3, "transfer_rate": 0.80},
            {"week_index": 4, "transfer_rate": 0.75},
            {"week_index": 5, "transfer_rate": 0.60},
        ]
        BurnInGovernance._save_snapshots(history)
        triggers = BurnInGovernance.evaluate_freeze_rules()
        assert len(triggers) == 1
        assert "Research Failure" in triggers[0]

    def test_reliability_failure_rising_prediction_error(self):
        # 5 weeks showing 4 consecutive rises in prediction reliability error
        history = [
            {"week_index": 1, "prediction_reliability_error": 0.05},
            {"week_index": 2, "prediction_reliability_error": 0.08},
            {"week_index": 3, "prediction_reliability_error": 0.12},
            {"week_index": 4, "prediction_reliability_error": 0.15},
            {"week_index": 5, "prediction_reliability_error": 0.20},
        ]
        BurnInGovernance._save_snapshots(history)
        triggers = BurnInGovernance.evaluate_freeze_rules()
        assert len(triggers) == 1
        assert "Reliability Failure" in triggers[0]


# ---------------------------------------------------------------------------
# 5. Protected Core Modules list check
# ---------------------------------------------------------------------------

class TestProtectedCoreRegistration:
    def test_burn_in_governance_is_protected(self):
        assert "burn_in_governance" in ProtectedCoreRegistry.PROTECTED_MODULES


# ---------------------------------------------------------------------------
# 6. REST API Endpoint checks
# ---------------------------------------------------------------------------

class TestBurnInAPI:
    def test_get_status(self):
        client = TestClient(app)
        resp = client.get("/dashboard/burn-in/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "state" in data["data"]
        assert "active_freezes" in data["data"]

    def test_post_reset_by_human(self):
        BurnInGovernance._save_state("AUDIT", ["Mock freeze"])
        
        client = TestClient(app)
        resp = client.post("/dashboard/burn-in/reset?reviewer=Alice")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert BurnInGovernance.is_frozen() is False

    def test_post_reset_by_system_denied(self):
        BurnInGovernance._save_state("AUDIT", ["Mock freeze"])

        client = TestClient(app)
        resp = client.post("/dashboard/burn-in/reset?reviewer=system")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
        assert "System actors may never override" in resp.json()["message"]
        assert BurnInGovernance.is_frozen() is True
