from __future__ import annotations

import json
import math
import os
import shutil
import socket
import subprocess
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
    TrackRecordStore,
)
from backend.core.proposal_engine import ProposalEngine
from backend.core.sandbox_lab import EphemeralSandboxContext, SafetyAuditor


@pytest.fixture
def temp_adv_db(monkeypatch):
    """Sets a temporary folder for proposals and sandbox experiment artifacts."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_adv_test_")
    monkeypatch.setattr("backend.core.proposal_engine.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.core.proposal_governance.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.core.sandbox_lab.runtime_data_root", lambda: Path(temp_dir))
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


# -- 1. Sandbox Escape Audit (Adversarial Suite) ------------------------------
def test_sandbox_socket_creation_block():
    with EphemeralSandboxContext():
        with pytest.raises(RuntimeError, match="Outbound network access is disabled"):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_sandbox_dns_lookup_block():
    with EphemeralSandboxContext():
        with pytest.raises(RuntimeError, match="DNS lookups are disabled"):
            socket.getaddrinfo("google.com", 80)

        with pytest.raises(RuntimeError, match="DNS lookups are disabled"):
            socket.gethostbyname("localhost")


def test_sandbox_file_write_block():
    with EphemeralSandboxContext():
        with pytest.raises(IOError, match="Write operations are blocked"):
            open("unauthorized_escape.txt", "w")


def test_sandbox_subprocess_spawn_block():
    with EphemeralSandboxContext():
        # Test subprocess.Popen directly
        with pytest.raises(RuntimeError, match="Subprocess spawning is disabled"):
            subprocess.Popen(["ls"])

        # Test subprocess.run
        with pytest.raises(RuntimeError, match="Subprocess spawning is disabled"):
            subprocess.run(["echo", "hello"])

        # Test os.system
        with pytest.raises(RuntimeError, match="Subprocess spawning is disabled"):
            os.system("echo hello")


def test_sandbox_environment_secret_stripping():
    # Set mock credentials/secrets in environment
    os.environ["DATABASE_PASSWORD"] = "super-secret-password-123"
    os.environ["API_KEY"] = "my-secret-key-456"
    os.environ["SAFE_VARIABLE"] = "safe-to-read"

    assert os.environ.get("DATABASE_PASSWORD") == "super-secret-password-123"
    assert os.environ.get("API_KEY") == "my-secret-key-456"
    assert os.environ.get("SAFE_VARIABLE") == "safe-to-read"

    with EphemeralSandboxContext():
        # Sensitive environment variables must be stripped
        assert "DATABASE_PASSWORD" not in os.environ
        assert "API_KEY" not in os.environ
        assert os.environ.get("SAFE_VARIABLE") == "safe-to-read"

    # Restored after sandbox exit
    assert os.environ.get("DATABASE_PASSWORD") == "super-secret-password-123"
    assert os.environ.get("API_KEY") == "my-secret-key-456"
    assert os.environ.get("SAFE_VARIABLE") == "safe-to-read"

    # Cleanup
    del os.environ["DATABASE_PASSWORD"]
    del os.environ["API_KEY"]
    del os.environ["SAFE_VARIABLE"]


# -- 2. Protected-Core Penetration Tests -------------------------------------
def test_protected_core_penetration_attempts(temp_adv_db):
    # Attempt 1: Touch protected module list explicitly
    prop1 = ProposalEngine.create_proposal(
        title="Speed up Validation",
        problem="Slow processing",
        evidence="Observed lag",
        proposal="Tweak validators module to bypass sandbox",
        expected_gain=10.0,
        complexity=1,
        confidence=90,
        affected_modules=["validators"]
    )
    assert prop1["status"] == ProposalStatus.REJECTED.value
    assert prop1["pis"] == 0.0
    assert any("protected core" in r or "Integrity Violation" in r for r in prop1["reasons"])

    # Attempt 2: Mention modifying benchmark arena in description
    prop2 = ProposalEngine.create_proposal(
        title="Optimize Benchmark Arena",
        problem="Slow runs",
        evidence="Observed lag",
        proposal="modify benchmark definitions and weights to gain higher scoring",
        expected_gain=15.0,
        complexity=2,
        confidence=95,
        affected_modules=["router"]
    )
    assert prop2["status"] == ProposalStatus.REJECTED.value
    assert prop2["pis"] == 0.0


# -- 3. Production Gain Tracking & GRA ---------------------------------------
def test_production_gain_and_gra_score(temp_adv_db):
    # Log runs for p1
    # Expected gain is resolved from proposal (let's create it first)
    prop = ProposalEngine.create_proposal(
        title="Sync cache",
        problem="lag",
        evidence="delay",
        proposal="sync cache",
        expected_gain=10.0,
        complexity=1,
        confidence=80
    )
    prop_id = prop["id"]

    TrackRecordStore.record_run(
        proposal_id=prop_id,
        stage="sandbox",
        success=True,
        actual_sandbox_gain=9.5,
        predicted_gain=10.0
    )

    TrackRecordStore.record_run(
        proposal_id=prop_id,
        stage="production",
        success=True,
        actual_production_gain=8.0
    )

    records = TrackRecordStore.get_track_records()
    assert len(records) == 1
    assert records[0]["predicted_gain"] == 10.0
    assert records[0]["actual_sandbox_gain"] == 9.5
    assert records[0]["actual_production_gain"] == 8.0

    # GRA: diff = 10.0 - 8.0 = 2.0. mse = 4.0. rmse = 2.0. GRA = 1.0 / (1.0 + 2.0) = 0.3333
    assert TrackRecordStore.get_gra_score() == 0.3333

    # Add a sleep to ensure the second proposal gets a different timestamp/ID
    time.sleep(1.1)

    # Add a second proposal to verify multi-pair RMSE
    prop2 = ProposalEngine.create_proposal(
        title="Index db",
        problem="slow queries",
        evidence="delay",
        proposal="index db table",
        expected_gain=5.0,
        complexity=1,
        confidence=85
    )
    prop_id2 = prop2["id"]
    assert prop_id2 != prop_id

    TrackRecordStore.record_run(
        proposal_id=prop_id2,
        stage="sandbox",
        success=True,
        actual_sandbox_gain=5.0,
        predicted_gain=5.0
    )

    TrackRecordStore.record_run(
        proposal_id=prop_id2,
        stage="production",
        success=True,
        actual_production_gain=5.0
    )

    # Pairs: (10.0, 8.0) and (5.0, 5.0)
    # diffs: 2.0 and 0.0. squares: 4.0 and 0.0. mse = 2.0. rmse = sqrt(2) = 1.4142.
    # GRA = 1.0 / (1.0 + 1.4142) = 0.4142
    assert TrackRecordStore.get_gra_score() == 0.4142


def test_api_gain_tracking_endpoints(temp_adv_db):
    client = TestClient(app)

    prop = ProposalEngine.create_proposal(
        title="Sync directory updates",
        problem="delay",
        evidence="delay",
        proposal="sync sweeps",
        expected_gain=12.0,
        complexity=1,
        confidence=85
    )
    prop_id = prop["id"]

    # 1. Gate 1 review approved
    review_payload = {
        "approved": True,
        "review_time_seconds": 45.0
    }
    response = client.post(f"/proposal/review/{prop_id}", params={"gate": "gate_1"}, json=review_payload)
    assert response.status_code == 200

    # 2. Record sandbox run -> LAB_TESTING
    run_payload = {
        "stage": "sandbox",
        "success": True,
        "metrics": {},
        "research_cost": 15.0,
        "predicted_gain": 12.0,
        "actual_sandbox_gain": 11.5
    }
    response = client.post(f"/proposal/record-result/{prop_id}", json=run_payload)
    assert response.status_code == 200

    # 3. Record benchmark run -> BENCHMARKING
    response = client.post(f"/proposal/record-result/{prop_id}", json={
        "stage": "benchmark",
        "success": True,
        "metrics": {}
    })
    assert response.status_code == 200

    # 4. Gate 2 review approved -> APPROVED_GATE_2
    review_payload2 = {
        "approved": True,
        "review_time_seconds": 45.0
    }
    response = client.post(f"/proposal/review/{prop_id}", params={"gate": "gate_2"}, json=review_payload2)
    assert response.status_code == 200

    # 5. Record canary run -> CANARY
    response = client.post(f"/proposal/record-result/{prop_id}", json={
        "stage": "canary",
        "success": True,
        "metrics": {}
    })
    assert response.status_code == 200

    # 6. Record production run -> DEPLOYED
    run_payload2 = {
        "stage": "production",
        "success": True,
        "metrics": {},
        "research_cost": 15.0,
        "actual_production_gain": 10.0
    }
    response = client.post(f"/proposal/record-result/{prop_id}", json=run_payload2)
    assert response.status_code == 200

    # Get track records and check GRA
    response = client.get("/proposal/track-records")
    assert response.status_code == 200
    data = response.json()
    assert "gra" in data
    # diff = 12.0 - 10.0 = 2.0. rmse = 2.0. gra = 1 / 3 = 0.3333
    assert data["gra"] == 0.3333
