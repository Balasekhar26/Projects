from __future__ import annotations

import json
import math
import os
import shutil
import socket
import tempfile
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.proposal_governance import ProposalStatus
from backend.core.proposal_engine import ProposalEngine
from backend.core.sandbox_lab import (
    RiskLevel,
    ExperimentRiskClassifier,
    EphemeralSandboxContext,
    ReplayEngine,
    SafetyAuditor,
    ArtifactStore,
    ResultPackager,
    ExperimentPackage,
)


@pytest.fixture
def temp_sandbox_db(monkeypatch):
    """Sets a temporary folder for proposals and sandbox experiment artifacts."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_sandbox_test_")
    monkeypatch.setattr("backend.core.proposal_engine.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.core.proposal_governance.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.core.sandbox_lab.runtime_data_root", lambda: Path(temp_dir))
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_risk_classifier():
    # R4 (Forbidden Protected Core)
    assert ExperimentRiskClassifier.classify("Modify validators", "some proposal", ["validators"]) == RiskLevel.R4
    assert ExperimentRiskClassifier.classify("Update consensus engine", "some proposal", []) == RiskLevel.R4

    # R3 (Critical System modification)
    assert ExperimentRiskClassifier.classify("Update policy metrics", "some proposal", []) == RiskLevel.R3
    assert ExperimentRiskClassifier.classify("Fix benchmark performance", "some proposal", []) == RiskLevel.R3

    # R2 (Architecture modification)
    assert ExperimentRiskClassifier.classify("Add custom validator interface", "some proposal", []) == RiskLevel.R2
    assert ExperimentRiskClassifier.classify("Modify router consensus", "some proposal", []) == RiskLevel.R2

    # R1 (Local behavior change)
    assert ExperimentRiskClassifier.classify("Tweak cache size", "some proposal", []) == RiskLevel.R1

    # R0 (Documentation only)
    assert ExperimentRiskClassifier.classify("Format docstrings", "update some comment", []) == RiskLevel.R0


def test_ephemeral_sandbox_isolation():
    # Verify that files are read-only and socket connections are blocked inside sandbox
    with EphemeralSandboxContext():
        # Socket block
        with pytest.raises(RuntimeError, match="Outbound network access is disabled"):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Write open block
        with pytest.raises(IOError, match="Write operations are blocked"):
            open("temp_sandbox_file.txt", "w")
            
        # Read open should still work on existing mock file (we can read ourselves for example)
        # Using __file__ as a safe readable target
        with open(__file__, "r") as f:
            content = f.read(10)
            assert len(content) == 10


def test_replay_engine():
    # Mock trace processor
    def mock_processor(trace):
        return {"success": True}

    results = ReplayEngine.replay_traces(mock_processor)
    assert len(results) == 5
    assert all(r["success"] is True for r in results)
    assert all(r["error"] is None for r in results)


def test_safety_auditor():
    # Text violation
    passed, msg = SafetyAuditor.audit_execution("attempts to delete database table", [])
    assert passed is False
    assert "Safety violation detected" in msg

    # Blocked write attempt audit
    failed_results = [
        {"request_id": "req-1", "success": False, "error": "Write operations are blocked in the sandbox environment."}
    ]
    passed, msg = SafetyAuditor.audit_execution("clean proposal", failed_results)
    assert passed is False
    assert "Unauthorized file mutation" in msg


def test_result_packager_prs(temp_sandbox_db):
    package = ExperimentPackage(
        proposal_id="prop-1",
        parent_proposal_id=None,
        risk_class=RiskLevel.R1,
        expected_gain=10.0,
        expected_risk=0.2,  # 20% predicted risk
        benchmark_targets=["accuracy"],
        rollback_targets=["router"],
        created_at=time.time(),
    )

    # 1. Success case: actual_risk = 0.0 (safety_passed=True)
    # Brier = (0.2 - 0.0)^2 = 0.04. PRS = 1.0 - 0.04 = 0.96
    report1 = ResultPackager.package_report(
        package=package,
        replay_results=[{"success": True}],
        safety_success=True,
        safety_message="",
        actual_gain=12.0
    )
    assert report1["prs_score"] == 0.96
    assert report1["recommendation"] == "PASS"

    # 2. Failure case: actual_risk = 1.0 (safety_passed=False)
    # Brier = (0.2 - 1.0)^2 = 0.64. PRS = 1.0 - 0.64 = 0.36
    package2 = ExperimentPackage(
        proposal_id="prop-2",
        parent_proposal_id=None,
        risk_class=RiskLevel.R1,
        expected_gain=10.0,
        expected_risk=0.2,
        benchmark_targets=["accuracy"],
        rollback_targets=["router"],
        created_at=time.time(),
    )
    report2 = ResultPackager.package_report(
        package=package2,
        replay_results=[{"success": True}],
        safety_success=False,
        safety_message="V bypass",
        actual_gain=5.0
    )
    assert report2["prs_score"] == 0.36
    assert report2["recommendation"] == "FAIL"

    # Cumulative PRS: Mean Brier = (0.04 + 0.64) / 2 = 0.34. Overall PRS = 1.0 - 0.34 = 0.66
    assert ResultPackager.get_overall_prs() == 0.66


def test_api_sandbox_endpoints(temp_sandbox_db):
    client = TestClient(app)

    # Pre-register a proposal to run sandbox experiments against
    prop = ProposalEngine.create_proposal(
        title="Sync cache keys",
        problem="Lag",
        evidence="Observed latency",
        proposal="Sync cache elements",
        expected_gain=15.0,
        complexity=1,
        confidence=90
    )
    prop_id = prop["id"]

    # 1. Run successful experiment
    run_payload = {
        "expected_risk": 0.1,
        "actual_gain": 12.0,
        "mock_failure": False
    }
    response = client.post(f"/sandbox/run-experiment/{prop_id}", json=run_payload)
    assert response.status_code == 200
    report = response.json()
    assert report["proposal_id"] == prop_id
    assert report["recommendation"] == "PASS"
    assert report["safety_passed"] is True

    # 2. Verify experiments listing
    response = client.get("/sandbox/experiments")
    assert response.status_code == 200
    assert len(response.json()["experiments"]) == 1

    # 3. Verify PRS score
    response = client.get("/sandbox/prs")
    assert response.status_code == 200
    assert "prs" in response.json()
