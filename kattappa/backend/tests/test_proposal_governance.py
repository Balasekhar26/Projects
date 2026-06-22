from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.proposal_governance import (
    ProposalStatus,
    ProtectedCoreRegistry,
    ProposalIntegrityScorer,
    ProposalBudgetManager,
    ProposalExpirationManager,
    TrackRecordStore,
    SemanticNegativeKnowledgeMatcher,
)
from backend.core.proposal_engine import ProposalEngine


@pytest.fixture
def temp_gov_db(monkeypatch):
    """Sets a temporary folder for proposals, negative knowledge, and track records."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_gov_test_")
    monkeypatch.setattr("backend.core.proposal_engine.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.core.proposal_governance.runtime_data_root", lambda: Path(temp_dir))
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_immutable_protected_core_registry():
    # Verify protected modules
    assert ProtectedCoreRegistry.is_protected("validators") is True
    assert ProtectedCoreRegistry.is_protected("validators.py") is True
    assert ProtectedCoreRegistry.is_protected("consensus_engine") is True
    assert ProtectedCoreRegistry.is_protected("proposal_governance") is True
    assert ProtectedCoreRegistry.is_protected("random_module") is False

    # Check affected modules list
    assert ProtectedCoreRegistry.check_affected_modules(["validators", "random"]) is True
    assert ProtectedCoreRegistry.check_affected_modules(["random_module", "other"]) is False


def test_proposal_integrity_scorer():
    # Clean proposal
    assert ProposalIntegrityScorer.compute_pis(
        title="Add query logs",
        proposal="Inject logger in router",
        affected_modules=["router"]
    ) == 100.0

    # Tampering: Touching protected module
    assert ProposalIntegrityScorer.compute_pis(
        title="Speed up routing",
        proposal="Optimize lookup",
        affected_modules=["validators"]
    ) == 0.0

    # Tampering: keywords in description
    assert ProposalIntegrityScorer.compute_pis(
        title="Bypass consensus",
        proposal="disable consensus checking",
        affected_modules=["router"]
    ) == 0.0


def test_proposal_budget_manager(temp_gov_db):
    # Default limit should be 5
    assert ProposalBudgetManager.get_budget_limit() == 5

    # Log 3 successful sandbox runs and 1 failed run
    # Total = 4, success = 3. PQS = 3/4 = 0.75
    TrackRecordStore.record_run("p-1", "sandbox", success=True, research_cost=0.0)
    TrackRecordStore.record_run("p-2", "sandbox", success=True, research_cost=0.0)
    TrackRecordStore.record_run("p-3", "sandbox", success=True, research_cost=0.0)
    TrackRecordStore.record_run("p-4", "sandbox", success=False, research_cost=0.0)
    
    # PQS > 0.7 triggers +20% limit scaling: 5 * 1.20 = 6
    assert TrackRecordStore.get_pqs() == 0.75
    assert ProposalBudgetManager.get_budget_limit() == 6

    # Log 3 failures to drop PQS
    TrackRecordStore.record_run("p-5", "sandbox", success=False, research_cost=0.0)
    TrackRecordStore.record_run("p-6", "sandbox", success=False, research_cost=0.0)
    TrackRecordStore.record_run("p-7", "sandbox", success=False, research_cost=0.0)
    
    # Total total = 7, success = 3. PQS = 3/7 = 0.428 (Neutral band)
    assert ProposalBudgetManager.get_budget_limit() == 5

    # Drop PQS below 0.3
    TrackRecordStore.record_run("p-8", "sandbox", success=False, research_cost=0.0)
    TrackRecordStore.record_run("p-9", "sandbox", success=False, research_cost=0.0)
    TrackRecordStore.record_run("p-10", "sandbox", success=False, research_cost=0.0)
    # Total total = 10, success = 3. PQS = 0.30
    # Let's add one more failure to make it PQS < 0.30 (3/11 = 0.2727)
    TrackRecordStore.record_run("p-11", "sandbox", success=False, research_cost=0.0)
    assert TrackRecordStore.get_pqs() < 0.3
    # PQS < 0.3 triggers -50% limit scaling: 5 * 0.50 = 2
    assert ProposalBudgetManager.get_budget_limit() == 2

    # Verify manual override
    ProposalBudgetManager.set_budget_override(10)
    # Override gets applied (limit 10, no PQS scaling logic override since overrides override base)
    # Actually override base is scaled unless config bypass. Let's make sure it handles override correctly.
    # In get_budget_limit, if override file exists, it uses it as base_limit and then applies scaling.
    # PQS is still 0.2727 so 10 * 0.50 = 5
    assert ProposalBudgetManager.get_budget_limit() == 5


def test_pipeline_roi_throttling(temp_gov_db):
    # Initialize track records with high research costs and 0 production gain
    # This leads to a negative Pipeline ROI. If >= 5 runs, it throttles daily budget by 75%.
    for i in range(5):
        # stage production, success=True, metrics={gain=0.0}, research_cost=20.0
        TrackRecordStore.record_run(f"r-{i}", "production", success=True, metrics={"gain": 0.0}, research_cost=20.0)

    # ROI = 0 - 100 = -100
    assert TrackRecordStore.get_pipeline_roi() == -100.0
    
    # Base limit is 5, throttled by 75% = 1.25 -> int = 1
    assert ProposalBudgetManager.get_budget_limit() == 1


def test_proposal_expiration_manager():
    # Not expired yet
    created = time.time()
    assert ProposalExpirationManager.is_expired(created, lifespan_days=30) is False

    # Expired proposal
    stale_time = time.time() - (31 * 24 * 3600)
    assert ProposalExpirationManager.is_expired(stale_time, lifespan_days=30) is True

    proposals = [
        {"id": "p-1", "status": "pending", "created_at": stale_time},
        {"id": "p-2", "status": "pending", "created_at": time.time()},
        {"id": "p-3", "status": "draft", "created_at": stale_time},
    ]
    updated = ProposalExpirationManager.expire_stale_proposals(proposals)
    assert updated[0]["status"] == "expired"
    assert updated[1]["status"] == "pending"
    assert updated[2]["status"] == "expired"


def test_track_record_store_and_burden_score(temp_gov_db):
    # Log reviews
    TrackRecordStore.record_human_review("p-100", "gate_1", approved=True, review_time_seconds=60.0)
    TrackRecordStore.record_human_review("p-100", "gate_2", approved=True, review_time_seconds=120.0)
    TrackRecordStore.record_human_review("p-101", "gate_1", approved=False, review_time_seconds=30.0)

    burden = TrackRecordStore.get_human_burden_score()
    assert burden["reviewed_count"] == 3
    assert burden["rejected_count"] == 1
    assert burden["average_review_time_seconds"] == 70.0
    # burden score = (3 / 2) * (70 / 60) = 1.5 * 1.166 = 1.75
    assert burden["human_burden_score"] == 1.75


def test_semantic_confidence_bands(temp_gov_db):
    failures = [
        {"title": "tauri config cache", "reason": "locks up graphics layer"},
        {"title": "cuda scale memory error", "reason": "gpu crash on serialization"},
    ]

    # Band: Block (>= 0.90) - Uses semantic family 1 (tauri)
    band, score, reason = SemanticNegativeKnowledgeMatcher.check_semantic_duplicate("tauri graphics layout", failures)
    assert band == "block"
    assert math.isclose(score, 1.0)

    # Band: Warning (0.70-0.80) - Uses Jaccard fallback logic if not matching exact families
    # Let's test check_semantic_duplicate Jaccard fallback with partial word overlap:
    # "tauri config cache" words: {"tauri", "config", "cache"}
    # Candidate words: {"tauri", "helper"}
    # Intersection = {"tauri"}
    # Union = {"tauri", "config", "cache", "helper"} (size 4)
    # Jaccard = 1/4 = 0.25 -> maps to "warning" (0.25 - 0.35)
    band, score, reason = SemanticNegativeKnowledgeMatcher._jaccard_fallback("tauri helper", failures)
    assert band == "warning"


def test_occam_gate_skepticism(temp_gov_db):
    # Capping expected gain when there's no history (should default to capping at mean + 2 * std_dev = 5.0 + 2 * 2.0 = 9.0)
    res_no_hist = ProposalEngine.evaluate_occam_gate("some change", expected_gain=100.0, complexity=2)
    assert res_no_hist["skeptical_gain"] == 9.0
    assert res_no_hist["downgraded"] is True
    assert res_no_hist["novelty_risk_score"] > 0.0

    # With history: let's record 3 successful production runs
    # Gains: 10.0, 12.0, 8.0. Mean = 10.0, std = ~1.63. limit = 10.0 + 2 * 1.63 = 13.26
    TrackRecordStore.record_run("p-1", "production", success=True, metrics={"gain": 10.0})
    TrackRecordStore.record_run("p-2", "production", success=True, metrics={"gain": 12.0})
    TrackRecordStore.record_run("p-3", "production", success=True, metrics={"gain": 8.0})

    res_with_hist = ProposalEngine.evaluate_occam_gate("some change", expected_gain=50.0, complexity=2)
    # Capped at limit (~13.26)
    assert res_with_hist["skeptical_gain"] < 15.0  # limit is max(mean + 2*std, 15) which is 15.0
    assert res_with_hist["downgraded"] is True


def test_lineage_and_lifecycle_transitions(temp_gov_db):
    # 1. Create a draft proposal with a lineage parent
    prop = ProposalEngine.create_proposal(
        title="Optimize cargo builds",
        problem="Slow compilation",
        evidence="cargo builds take 4 minutes",
        proposal="Use sccache",
        expected_gain=12.0,
        complexity=1,
        confidence=90,
        parent_proposal_id="prop_parent_123",
        research_cost=15.0
    )
    assert prop["status"] == ProposalStatus.PENDING.value
    assert prop["parent_proposal_id"] == "prop_parent_123"
    assert prop["research_cost"] == 15.0

    # 2. Transition status according to rules
    prop_id = prop["id"]
    
    # Valid transition: pending -> approved_gate_1
    updated = ProposalEngine.transition_status(prop_id, ProposalStatus.APPROVED_GATE_1)
    assert updated["status"] == ProposalStatus.APPROVED_GATE_1.value

    # Invalid transition: approved_gate_1 cannot jump straight to deployed
    with pytest.raises(ValueError):
        ProposalEngine.transition_status(prop_id, ProposalStatus.DEPLOYED)


def test_api_v2_endpoints(temp_gov_db):
    client = TestClient(app)

    # 1. Get budget statistics
    response = client.get("/proposal/budget")
    assert response.status_code == 200
    data = response.json()
    assert "daily_limit" in data
    assert "pipeline_roi" in data

    # 2. Log human review
    # Let's create a pending proposal first
    prop = ProposalEngine.create_proposal(
        title="Sync directory updates",
        problem="Inconsistent sweeps",
        evidence="Observed delay",
        proposal="Sync sweeps synchronously",
        expected_gain=12.0,
        complexity=1,
        confidence=85
    )
    prop_id = prop["id"]

    review_payload = {
        "approved": True,
        "review_time_seconds": 45.0
    }
    response = client.post(f"/proposal/review/{prop_id}", params={"gate": "gate_1"}, json=review_payload)
    assert response.status_code == 200
    assert response.json()["proposal"]["status"] == ProposalStatus.APPROVED_GATE_1.value

    # Verify review metrics updated in burden score
    response = client.get("/proposal/budget")
    assert response.json()["human_burden"]["reviewed_count"] == 1
    assert response.json()["human_burden"]["average_review_time_seconds"] == 45.0

    # 3. Record stage execution
    run_payload = {
        "stage": "sandbox",
        "success": True,
        "metrics": {"sandbox_failures": 0},
        "research_cost": 15.0
    }
    response = client.post(f"/proposal/record-result/{prop_id}", json=run_payload)
    assert response.status_code == 200
    assert response.json()["proposal"]["status"] == ProposalStatus.LAB_TESTING.value

    # Verify track records query
    response = client.get("/proposal/track-records")
    assert response.status_code == 200
    assert len(response.json()["records"]) == 1  # Unified record per proposal_id
