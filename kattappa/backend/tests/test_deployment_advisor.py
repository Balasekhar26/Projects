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
from backend.core.proposal_governance import ProposalStatus
from backend.core.proposal_engine import ProposalEngine
from backend.core.deployment_advisor import (
    DeploymentAdvisor,
    CanaryReleaseCoordinator,
    AutomaticRollbackEngine,
)


@pytest.fixture
def temp_dep_db(monkeypatch):
    """Sets a temporary folder for proposals, negative knowledge, and canary artifacts."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_dep_test_")
    monkeypatch.setattr("backend.core.proposal_engine.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.core.proposal_governance.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.core.deployment_advisor.runtime_data_root", lambda: Path(temp_dir))
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_deployment_advisor_floors():
    # Pass case
    res = DeploymentAdvisor.assess_deployment(
        proposal_id="p-1",
        benchmark_scores={"safety": 0.96, "planning": 0.88, "memory": 0.90, "latency": 100.0},
        baseline_scores={"safety": 0.95, "planning": 0.85, "memory": 0.85, "latency": 100.0},
    )
    assert res["recommendation"] == "APPROVE"
    assert res["floors_met"] is True
    assert res["regression_free"] is True

    # Fail floor check (safety floor is 0.95, got 0.90)
    res_fail = DeploymentAdvisor.assess_deployment(
        proposal_id="p-1",
        benchmark_scores={"safety": 0.90, "planning": 0.88, "memory": 0.90, "latency": 100.0},
        baseline_scores={"safety": 0.95, "planning": 0.85, "memory": 0.85, "latency": 100.0},
    )
    assert res_fail["recommendation"] == "DENY"
    assert res_fail["floors_met"] is False


def test_deployment_advisor_regression_noise():
    # Fail 5% regression noise check (planning dropped from 0.90 to 0.85, which is > 5% drop)
    res_reg = DeploymentAdvisor.assess_deployment(
        proposal_id="p-1",
        benchmark_scores={"safety": 0.96, "planning": 0.85, "memory": 0.90, "latency": 100.0},
        baseline_scores={"safety": 0.96, "planning": 0.90, "memory": 0.90, "latency": 100.0},
    )
    assert res_reg["recommendation"] == "DENY"
    assert res_reg["regression_free"] is False

    # Fail latency regression noise check (latency increased from 100 to 110, which is > 5% increase)
    res_lat = DeploymentAdvisor.assess_deployment(
        proposal_id="p-1",
        benchmark_scores={"safety": 0.96, "planning": 0.88, "memory": 0.90, "latency": 110.0},
        baseline_scores={"safety": 0.95, "planning": 0.85, "memory": 0.85, "latency": 100.0},
    )
    assert res_lat["recommendation"] == "DENY"
    assert res_lat["regression_free"] is False


def test_canary_rollout_steps(temp_dep_db):
    proposal_id = "p-canary-1"
    
    # 1st step: 0% -> 1%
    s1 = CanaryReleaseCoordinator.advance_canary(proposal_id)
    assert s1["current_step"] == "1%"
    assert s1["active"] is True

    # 2nd step: 1% -> 5%
    s2 = CanaryReleaseCoordinator.advance_canary(proposal_id)
    assert s2["current_step"] == "5%"

    # Skip to rollback if anomaly is simulated
    s_rb = CanaryReleaseCoordinator.advance_canary(proposal_id, simulated_anomaly="high latency")
    assert s_rb["current_step"] == "ROLLBACK"
    assert s_rb["active"] is False


def test_automatic_rollback_and_postmortem(temp_dep_db):
    # Pre-register proposal
    prop = ProposalEngine.create_proposal(
        title="Sync cache memory keys",
        problem="Lag",
        evidence="Latency spike",
        proposal="Optimize dict index lookup",
        expected_gain=12.0,
        complexity=1,
        confidence=90
    )
    prop_id = prop["id"]

    # Trigger rollback
    rb_report = AutomaticRollbackEngine.rollback(prop_id, reason="Safety infraction")
    assert rb_report["status"] == "rolled_back"
    assert rb_report["reason"] == "Safety infraction"
    
    # Verify proposal transitioned to REJECTED status
    proposals = ProposalEngine.list_proposals()
    assert proposals[0]["status"] == ProposalStatus.REJECTED.value

    # Verify postmortem registered Negative Knowledge entry automatically
    assert ProposalEngine.negative_knowledge_exists("Sync cache memory keys") is True


def test_api_deployment_endpoints(temp_dep_db):
    client = TestClient(app)

    # Pre-register proposal
    prop = ProposalEngine.create_proposal(
        title="Compact index values",
        problem="Large metadata size",
        evidence="Observed metadata bloat",
        proposal="Compress schema tables",
        expected_gain=10.0,
        complexity=2,
        confidence=85
    )
    prop_id = prop["id"]

    # 1. Assess deployment endpoint
    assess_payload = {
        "benchmark_scores": {"safety": 0.96, "planning": 0.88, "memory": 0.90, "latency": 100.0},
        "baseline_scores": {"safety": 0.95, "planning": 0.85, "memory": 0.85, "latency": 100.0}
    }
    response = client.post(f"/deployment/assess/{prop_id}", json=assess_payload)
    assert response.status_code == 200
    assert response.json()["recommendation"] == "APPROVE"

    # 2. Canary release steps endpoint
    canary_payload = {
        "simulated_anomaly": None
    }
    response = client.post(f"/deployment/canary/step/{prop_id}", json=canary_payload)
    assert response.status_code == 200
    assert response.json()["current_step"] == "1%"

    # 3. Canary step rollback trigger
    canary_rb_payload = {
        "simulated_anomaly": "High error rate"
    }
    response = client.post(f"/deployment/canary/step/{prop_id}", json=canary_rb_payload)
    assert response.status_code == 200
    assert response.json()["current_step"] == "ROLLBACK"

    # 4. Direct rollback endpoint
    rollback_payload = {
        "reason": "Direct administrator trigger"
    }
    response = client.post(f"/deployment/rollback/{prop_id}", json=rollback_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "rolled_back"
