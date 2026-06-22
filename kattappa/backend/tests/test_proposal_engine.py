from __future__ import annotations

import os
import json
import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.proposal_engine import ProposalEngine, ProposalStatus


@pytest.fixture
def temp_proposal_db(monkeypatch):
    """Sets a temporary folder for proposal and negative knowledge data root."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_proposal_test_")
    monkeypatch.setattr("backend.core.proposal_engine.runtime_data_root", lambda: Path(temp_dir))
    yield Path(temp_dir)
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_observe_and_reflect():
    obs = ProposalEngine.observe_issue("Router latency spike", "high", {"p95_ms": 350.0})
    assert obs["issue"] == "Router latency spike"
    assert obs["severity"] == "high"
    assert obs["metrics"] == {"p95_ms": 350.0}

    hyps = ProposalEngine.reflect_on_observation(obs)
    assert len(hyps) > 0
    assert any("latency" in h["hypothesis"].lower() or "database" in h["hypothesis"].lower() for h in hyps)


def test_protected_core_checks():
    # Violation checks
    assert ProposalEngine.is_protected_core_violation("modify validators.py to bypass check") is True
    assert ProposalEngine.is_protected_core_violation("restructure consensus_engine module") is True
    assert ProposalEngine.is_protected_core_violation("rewrite execution_policy.py") is True
    assert ProposalEngine.is_protected_core_violation("optimize database query") is False


def test_negative_knowledge(temp_proposal_db):
    title = "Add global memory cache"
    assert ProposalEngine.negative_knowledge_exists(title) is False

    ProposalEngine.register_negative_knowledge(title, "Caused memory leaks in previous tests")
    assert ProposalEngine.negative_knowledge_exists(title) is True
    assert ProposalEngine.negative_knowledge_exists("different title") is False


def test_occam_gate():
    # Beats simple fix
    # Candidate ROI = 10 / 2 = 5.0
    # Simple fix ROI = 7.0 / 2 = 3.5
    res = ProposalEngine.evaluate_occam_gate("new design", expected_gain=10.0, complexity=2)
    assert res["beats_simple_fix"] is True

    # Fails to beat simple fix
    # Candidate ROI = 5 / 10 = 0.5
    # Simple fix ROI = 3.5 / 2 = 1.75
    res = ProposalEngine.evaluate_occam_gate("complex overhaul", expected_gain=5.0, complexity=10)
    assert res["beats_simple_fix"] is False


def test_create_and_manage_proposal(temp_proposal_db):
    # 1. Successful proposal creation (beats Occam gate, not core violation, not negative knowledge)
    prop = ProposalEngine.create_proposal(
        title="Index database keys",
        problem="Slow query lookups",
        evidence="p95 query latency is 400ms",
        proposal="Create B-tree indexes on keys",
        expected_gain=15.0,
        complexity=2, # ROI = 15/2 = 7.5 (beats simple 10.5/2 = 5.25)
        confidence=90
    )
    assert prop["status"] == ProposalStatus.PENDING.value
    assert "id" in prop

    # Verify persistent list
    proposals = ProposalEngine.list_proposals()
    assert len(proposals) == 1
    assert proposals[0]["title"] == "Index database keys"

    # 2. Rejection: Protected core violation
    prop_sec = ProposalEngine.create_proposal(
        title="Rewrite policy_engine rules",
        problem="Policy blocks too many queries",
        evidence="High block rate",
        proposal="Modify policy_engine rules dynamically",
        expected_gain=20.0,
        complexity=1,
        confidence=95
    )
    assert prop_sec["status"] == ProposalStatus.REJECTED.value
    assert "reasons" in prop_sec
    assert any("protected" in r.lower() for r in prop_sec["reasons"])

    # 3. Rejection: Matches negative knowledge
    ProposalEngine.register_negative_knowledge("Add global cache", "Fails due to memory leakage")
    prop_neg = ProposalEngine.create_proposal(
        title="Add global cache",
        problem="performance",
        evidence="slow speed",
        proposal="cache everything",
        expected_gain=20.0,
        complexity=1,
        confidence=95
    )
    assert prop_neg["status"] == ProposalStatus.REJECTED.value
    assert any("negative-knowledge" in r.lower() for r in prop_neg["reasons"])

    # 4. Rejection: Fails Occam Gate
    prop_occam = ProposalEngine.create_proposal(
        title="Complete database redesign",
        problem="Slow query lookups",
        evidence="p95 is 400ms",
        proposal="Overhaul schema, migrate tables",
        expected_gain=6.0,
        complexity=10, # ROI = 6/10 = 0.6 (fails vs simple 4.2/2 = 2.1)
        confidence=80
    )
    assert prop_occam["status"] == ProposalStatus.REJECTED.value
    assert any("occam" in r.lower() for r in prop_occam["reasons"])


def test_transition_status(temp_proposal_db):
    prop = ProposalEngine.create_proposal(
        title="Index database keys",
        problem="Slow query lookups",
        evidence="p95 query latency is 400ms",
        proposal="Create B-tree indexes on keys",
        expected_gain=15.0,
        complexity=2,
        confidence=90
    )
    prop_id = prop["id"]

    updated = ProposalEngine.transition_status(prop_id, ProposalStatus.SANDBOX_APPROVED)
    assert updated["status"] == ProposalStatus.SANDBOX_APPROVED.value

    # Verify in list
    assert ProposalEngine.list_proposals()[0]["status"] == ProposalStatus.SANDBOX_APPROVED.value


# ===========================================================================
# REST API Integration Tests
# ===========================================================================

def test_api_proposal_endpoints(temp_proposal_db):
    client = TestClient(app)

    # 1. Observe issue
    obs_payload = {
        "issue": "latency spike in database",
        "severity": "high"
    }
    response = client.post("/proposal/observe", json=obs_payload)
    assert response.status_code == 200
    res_data = response.json()
    assert "observation" in res_data
    assert "hypotheses" in res_data

    # 2. Register negative knowledge
    neg_payload = {
        "title": "Add global index",
        "reason": "Index causes write locks"
    }
    response = client.post("/proposal/negative-knowledge", json=neg_payload)
    assert response.status_code == 200
    assert response.json()["entry"]["title"] == "Add global index"

    # 3. Create proposal
    prop_payload = {
        "title": "Database indexing",
        "problem": "Slow queries",
        "evidence": "Observed lag",
        "proposal": "Create indexes on query columns",
        "expected_gain": 20.0,
        "complexity": 2,
        "confidence": 90
    }
    response = client.post("/proposal/create", json=prop_payload)
    assert response.status_code == 200
    prop = response.json()
    assert prop["title"] == "Database indexing"
    assert prop["status"] == ProposalStatus.PENDING.value
    prop_id = prop["id"]

    # 4. List proposals
    response = client.get("/proposal/list")
    assert response.status_code == 200
    assert len(response.json()["proposals"]) == 1

    # 5. Approve proposal
    response = client.post(f"/proposal/approve/{prop_id}", params={"status": "sandbox_approved"})
    assert response.status_code == 200
    assert response.json()["status"] == ProposalStatus.SANDBOX_APPROVED.value
