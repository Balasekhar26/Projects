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
from backend.core.proposal_governance import (
    ProposalStatus,
    ProtectedCoreRegistry,
    TrackRecordStore,
)
from backend.core.proposal_engine import ProposalEngine
from backend.core.sandbox_lab import EphemeralSandboxContext, ReplayEngine
from backend.core.deployment_advisor import CanaryReleaseCoordinator


@pytest.fixture
def temp_audit_db(monkeypatch):
    """Sets a temporary folder for proposals and sandbox experiment artifacts."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_audit_test_")
    monkeypatch.setattr("backend.core.proposal_engine.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.core.proposal_governance.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.core.sandbox_lab.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.core.deployment_advisor.runtime_data_root", lambda: Path(temp_dir))
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


# -- 1. Sandbox Process Isolation ---------------------------------------------
def test_sandbox_process_isolation_pid():
    parent_pid = os.getpid()

    # The mock processor should fail if executed in the same process
    def mock_trace_processor(trace):
        if os.getpid() == parent_pid:
            return {"success": False}
        return {"success": True}

    results = ReplayEngine.replay_traces(mock_trace_processor)
    assert len(results) == 5
    # Verify that it succeeded, which proves that it executed in a child process
    assert all(r["success"] is True for r in results)


# -- 2. Transitive Protected Core Check ---------------------------------------
def test_transitive_protected_core(monkeypatch):
    # Setup mock dependency graph
    # validators -> helper_x
    # helper_x -> helper_y
    # router is independent
    mock_graph = {
        "validators": {"helper_x"},
        "helper_x": {"helper_y"},
        "router": set(),
    }
    
    monkeypatch.setattr(ProtectedCoreRegistry, "build_dependency_graph", lambda: mock_graph)
    # Clear cache
    monkeypatch.setattr(ProtectedCoreRegistry, "_cached_graph", None)

    # Directly protected
    assert ProtectedCoreRegistry.is_transitively_protected("validators") is True
    assert ProtectedCoreRegistry.is_transitively_protected("validators.py") is True

    # Indirectly protected (transitive dependencies)
    assert ProtectedCoreRegistry.is_transitively_protected("helper_x") is True
    assert ProtectedCoreRegistry.is_transitively_protected("helper_y") is True

    # Safe modules
    assert ProtectedCoreRegistry.is_transitively_protected("router") is False


# -- 3. Held-Out Canary Validation -------------------------------------------
def test_held_out_canary_validation(temp_audit_db):
    # Verify canary step fails and rolls back when simulated regression is True
    prop = ProposalEngine.create_proposal(
        title="Sync cache updates",
        problem="delay",
        evidence="delay",
        proposal="sync cache element keys",
        expected_gain=12.0,
        complexity=1,
        confidence=85
    )
    prop_id = prop["id"]

    res = CanaryReleaseCoordinator.advance_canary(prop_id, simulated_held_out_regression=True)
    assert res["current_step"] == "ROLLBACK"
    assert "Held-Out Validation Failure" in res["anomaly"]


# -- 4. Negative-Knowledge Decay & Expiration ---------------------------------
def test_negative_knowledge_decay(temp_audit_db):
    # Verify that a negative knowledge entry created 30 days ago has decayed and does not block
    now = time.time()
    stale_time = now - (30 * 86400)
    from backend.core.proposal_engine import _negative_knowledge_path
    path = _negative_knowledge_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    entries = [
        {
            "title": "Cuda Memory Overload",
            "reason": "exhausted memory pool",
            "confidence": 1.0,
            "logged_at": stale_time
        }
    ]
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    # Stale entry should have confidence below 0.3, meaning it doesn't block
    assert ProposalEngine.negative_knowledge_exists("Cuda Memory Overload") is False

    # A recent failure (2 days ago) should still block
    recent_time = now - (2 * 86400)
    entries2 = [
        {
            "title": "Cuda Memory Overload",
            "reason": "exhausted memory pool",
            "confidence": 1.0,
            "logged_at": recent_time
        }
    ]
    path.write_text(json.dumps(entries2, indent=2), encoding="utf-8")

    # Confidence is ~0.90, so it blocks
    assert ProposalEngine.negative_knowledge_exists("Cuda Memory Overload") is True


# -- 5. Production Value Score (PVS) ------------------------------------------
def test_pvs_score_calculation(temp_audit_db):
    # Run 1: Gain = 20.0, Cost = 10.0 -> PVS = 2.0
    TrackRecordStore.record_run(
        proposal_id="p-1",
        stage="production",
        success=True,
        research_cost=10.0,
        actual_production_gain=20.0
    )

    records = TrackRecordStore.get_track_records()
    assert records[0]["pvs"] == 2.0
    assert TrackRecordStore.get_pipeline_pvs() == 2.0

    # Run 2: Gain = 10.0, Cost = 5.0 -> total gain = 30.0, total cost = 15.0 -> overall PVS = 2.0
    TrackRecordStore.record_run(
        proposal_id="p-2",
        stage="production",
        success=True,
        research_cost=5.0,
        actual_production_gain=10.0
    )
    assert TrackRecordStore.get_pipeline_pvs() == 2.0


def test_api_pvs_endpoint(temp_audit_db):
    client = TestClient(app)

    # Pre-populate human reviews and run records to test PVS and IY
    TrackRecordStore.record_human_review(
        proposal_id="p-100",
        gate="gate_1",
        approved=True,
        review_time_seconds=30.0
    )
    TrackRecordStore.record_run(
        proposal_id="p-100",
        stage="production",
        success=True,
        research_cost=15.0,
        actual_production_gain=30.0
    )

    response = client.get("/proposal/track-records")
    assert response.status_code == 200
    data = response.json()
    assert "pipeline_pvs" in data
    assert data["pipeline_pvs"] == 2.0
    assert "pipeline_iy" in data
    assert data["pipeline_iy"] == 1.0
    assert "pipeline_prr" in data
    assert "pipeline_nkhr" in data
    assert "pipeline_rf" in data


# -- 6. Improvement Registry Audit Ledger ------------------------------------
def test_improvement_registry_creation_and_append_only(temp_audit_db):
    from backend.core.proposal_governance import ImprovementRegistry, ProposalStatus
    from backend.core.proposal_engine import ProposalEngine

    # 1. Create a proposal
    prop = ProposalEngine.create_proposal(
        title="Sync cache updates",
        problem="delay",
        evidence="delay",
        proposal="sync cache element keys",
        expected_gain=12.0,
        complexity=1,
        confidence=85
    )
    prop_id = prop["id"]

    # Verify initial creation automatically created the registry entry
    details = ImprovementRegistry.get_improvement_details(f"imp_{prop_id}")
    assert len(details) == 1
    assert details[0]["final_outcome"] == "PROPOSED"
    assert details[0]["proposed_fix"] == "sync cache element keys"
    assert details[0]["problem"] == "delay"

    # 2. Transition status to approved/lab_testing and verify append-only behavior (new entry added, old preserved)
    ProposalEngine.transition_status(prop_id, ProposalStatus.APPROVED_GATE_1)
    
    details = ImprovementRegistry.get_improvement_details(f"imp_{prop_id}")
    assert len(details) == 2
    assert details[0]["final_outcome"] == "PROPOSED"  # Original entry is preserved!
    assert details[1]["final_outcome"] == "PROPOSED"  # Updated transition is appended!
    assert details[1]["approval_status"] == ProposalStatus.APPROVED_GATE_1.value

    # Verify get_improvements returns the latest consolidated status
    improvements = ImprovementRegistry.get_improvements(proposal_id=prop_id)
    assert len(improvements) == 1
    assert improvements[0]["approval_status"] == ProposalStatus.APPROVED_GATE_1.value


def test_improvement_registry_status_propagation_and_rollback(temp_audit_db):
    from backend.core.proposal_governance import ImprovementRegistry, TrackRecordStore, ProposalStatus
    from backend.core.proposal_engine import ProposalEngine
    from backend.core.deployment_advisor import CanaryReleaseCoordinator

    # 1. Create proposal
    prop = ProposalEngine.create_proposal(
        title="Optimizer speed",
        problem="slow training",
        evidence="profile logs",
        proposal="adjust learning rate steps",
        expected_gain=20.0,
        complexity=2,
        confidence=90
    )
    prop_id = prop["id"]

    # 2. Transition to LAB_TESTING (Sandbox) and record Sandbox failure
    ProposalEngine.transition_status(prop_id, ProposalStatus.APPROVED_GATE_1)
    ProposalEngine.transition_status(prop_id, ProposalStatus.LAB_TESTING)
    TrackRecordStore.record_run(
        proposal_id=prop_id,
        stage="sandbox",
        success=False,
        actual_sandbox_gain=5.0,
        research_cost=10.0
    )
    ProposalEngine.transition_status(prop_id, ProposalStatus.REJECTED)

    # Outcome should propagate to SANDBOX_FAILED
    improvements = ImprovementRegistry.get_improvements(proposal_id=prop_id)
    assert len(improvements) == 1
    assert improvements[0]["final_outcome"] == "SANDBOX_FAILED"
    assert improvements[0]["sandbox_gain"] == 5.0

    # 3. Create another proposal that will successfully deploy, then rollback
    time.sleep(1.1)
    prop2 = ProposalEngine.create_proposal(
        title="Memory optimization",
        problem="high usage",
        evidence="mem profile",
        proposal="garbage collect tensor refs",
        expected_gain=30.0,
        complexity=2,
        confidence=95
    )
    prop2_id = prop2["id"]

    ProposalEngine.transition_status(prop2_id, ProposalStatus.APPROVED_GATE_1)
    ProposalEngine.transition_status(prop2_id, ProposalStatus.LAB_TESTING)
    TrackRecordStore.record_run(prop2_id, "sandbox", True, actual_sandbox_gain=30.0, research_cost=15.0)

    ProposalEngine.transition_status(prop2_id, ProposalStatus.BENCHMARKING)
    TrackRecordStore.record_run(prop2_id, "benchmark", True, research_cost=15.0)

    ProposalEngine.transition_status(prop2_id, ProposalStatus.APPROVED_GATE_2)
    ProposalEngine.transition_status(prop2_id, ProposalStatus.CANARY)
    
    # Progress Canary
    CanaryReleaseCoordinator.advance_canary(prop2_id)
    
    # Trigger rollback
    CanaryReleaseCoordinator.advance_canary(prop2_id, simulated_anomaly="Memory leak detected in production")

    # Outcome should propagate to ROLLED_BACK
    details = ImprovementRegistry.get_improvement_details(f"imp_{prop2_id}")
    latest_outcome = details[-1]["final_outcome"]
    assert latest_outcome == "ROLLED_BACK"
    assert details[-1]["rollback_status"] == "rolled_back"


def test_improvement_registry_stats_and_api(temp_audit_db):
    from backend.core.proposal_governance import ImprovementRegistry, TrackRecordStore, ProposalStatus
    from backend.core.proposal_engine import ProposalEngine
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # 1. Proposal 1: Success deployment
    p1 = ProposalEngine.create_proposal("P1", "Prob1", "Ev1", "Fix1", expected_gain=10.0, complexity=1, confidence=100)
    p1_id = p1["id"]
    ProposalEngine.transition_status(p1_id, ProposalStatus.APPROVED_GATE_1)
    ProposalEngine.transition_status(p1_id, ProposalStatus.LAB_TESTING)
    TrackRecordStore.record_run(p1_id, "sandbox", True, actual_sandbox_gain=10.0, research_cost=5.0)
    ProposalEngine.transition_status(p1_id, ProposalStatus.BENCHMARKING)
    TrackRecordStore.record_run(p1_id, "benchmark", True, research_cost=5.0)
    ProposalEngine.transition_status(p1_id, ProposalStatus.APPROVED_GATE_2)
    ProposalEngine.transition_status(p1_id, ProposalStatus.CANARY)
    ProposalEngine.transition_status(p1_id, ProposalStatus.DEPLOYED)
    TrackRecordStore.record_run(p1_id, "production", True, actual_production_gain=10.0, research_cost=5.0)
    
    # Propagate the DEPLOYED_SUCCESSFUL transition
    ImprovementRegistry.register_or_update(p1_id, "DEPLOYED_SUCCESSFUL")

    # 2. Proposal 2: Rejected by gate
    time.sleep(1.1)
    p2 = ProposalEngine.create_proposal("P2", "Prob2", "Ev2", "Fix2", expected_gain=15.0, complexity=1, confidence=80)
    p2_id = p2["id"]
    ProposalEngine.transition_status(p2_id, ProposalStatus.REJECTED)

    # Get stats
    stats = ImprovementRegistry.get_stats()
    assert stats["total"] == 2
    assert stats["successful"] == 1
    assert stats["rejected"] == 1
    
    # IQS checking
    assert stats["avg_iqs"] == 0.68

    # GRA checking
    assert stats["avg_gra"] == 1.0

    # API endpoints checking
    response = client.get("/improvements")
    assert response.status_code == 200
    assert len(response.json()) == 2

    response_details = client.get(f"/improvements/imp_{p1_id}")
    assert response_details.status_code == 200
    assert len(response_details.json()) >= 2  # Has multiple transitions

    response_stats = client.get("/improvements/stats")
    assert response_stats.status_code == 200
    assert response_stats.json()["successful"] == 1


def test_improvement_registry_integrity_checks(temp_audit_db):
    from backend.core.proposal_governance import ImprovementRegistry, _improvement_registry_path
    import threading

    # 1. Missing proposal reference handling
    record = ImprovementRegistry.register_or_update("missing_prop_123")
    assert record["proposal_id"] == "missing_prop_123"
    assert record["improvement_id"] == "imp_missing_prop_123"
    assert record["problem"] == "Unknown problem"
    assert record["proposed_fix"] == "No fix description logged"

    # 2. Duplicate registration attempts
    ImprovementRegistry.register_or_update("missing_prop_123")
    ImprovementRegistry.register_or_update("missing_prop_123")
    
    details = ImprovementRegistry.get_improvement_details("imp_missing_prop_123")
    assert len(details) == 3

    # 3. Concurrent writes test
    threads = []
    def concurrent_writer(thread_idx):
        for i in range(5):
            ImprovementRegistry.register_or_update(f"concurrent_prop_{thread_idx}_{i}")
            
    for t_idx in range(5):
        t = threading.Thread(target=concurrent_writer, args=(t_idx,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    registry_list = ImprovementRegistry._load_registry()
    assert len(registry_list) == 28

    # 4. Corrupted ledger recovery
    path = _improvement_registry_path()
    path.write_text("INVALID_GARBAGE_JSON_STRING!!!!{{{", encoding="utf-8")
    
    recovered = ImprovementRegistry._load_registry()
    assert isinstance(recovered, list)
    backup_files = list(path.parent.glob("improvement_registry_corrupted_*.json"))
    assert len(backup_files) >= 1


def test_improvement_registry_lifecycle_reconstruction_and_rollback_replay(temp_audit_db):
    from backend.core.proposal_governance import ImprovementRegistry, TrackRecordStore, ProposalStatus
    from backend.core.proposal_engine import ProposalEngine
    from backend.core.deployment_advisor import CanaryReleaseCoordinator

    # 1. Create a proposal that goes through a complex lifecycle and ends with a rollback
    prop = ProposalEngine.create_proposal(
        title="Query cache bypass",
        problem="stale reads",
        evidence="redis latency",
        proposal="bypass cache on specific queries",
        expected_gain=15.0,
        complexity=1,
        confidence=90
    )
    prop_id = prop["id"]
    improvement_id = f"imp_{prop_id}"

    # Move through steps
    ProposalEngine.transition_status(prop_id, ProposalStatus.APPROVED_GATE_1)
    ProposalEngine.transition_status(prop_id, ProposalStatus.LAB_TESTING)
    TrackRecordStore.record_run(prop_id, "sandbox", True, actual_sandbox_gain=15.0, research_cost=10.0)

    ProposalEngine.transition_status(prop_id, ProposalStatus.BENCHMARKING)
    TrackRecordStore.record_run(prop_id, "benchmark", True, research_cost=10.0)

    ProposalEngine.transition_status(prop_id, ProposalStatus.APPROVED_GATE_2)
    ProposalEngine.transition_status(prop_id, ProposalStatus.CANARY)
    CanaryReleaseCoordinator.advance_canary(prop_id)

    # Trigger a rollback
    CanaryReleaseCoordinator.advance_canary(prop_id, simulated_anomaly="Bypassed queries caused high DB load")

    # Fetch all details for this improvement_id from the ledger
    details = ImprovementRegistry.get_improvement_details(improvement_id)
    assert len(details) > 0

    # 2. Reconstruct the complete lifecycle from the ledger transitions alone
    reconstructed_states = []
    for event in details:
        status = event["approval_status"]
        if not reconstructed_states or reconstructed_states[-1] != status:
            reconstructed_states.append(status)
    
    expected_sequence = [
        "pending",
        ProposalStatus.APPROVED_GATE_1.value,
        ProposalStatus.LAB_TESTING.value,
        ProposalStatus.BENCHMARKING.value,
        ProposalStatus.APPROVED_GATE_2.value,
        ProposalStatus.CANARY.value,
        # After rollback, the proposal status becomes REJECTED in ProposalEngine, and final_outcome becomes ROLLED_BACK
        ProposalStatus.REJECTED.value,
    ]
    # Verify that the reconstructed states match the actual transitions
    assert reconstructed_states == expected_sequence

    # Reconstruct final outcomes
    reconstructed_outcomes = []
    for event in details:
        outcome = event["final_outcome"]
        if not reconstructed_outcomes or reconstructed_outcomes[-1] != outcome:
            reconstructed_outcomes.append(outcome)

    assert reconstructed_outcomes == ["PROPOSED", "DEPLOYED", "REJECTED", "ROLLED_BACK"]

    # Verify that the rollback step is fully replayable/verifiable from the ledger alone
    rollback_events = [e for e in details if e["rollback_status"] == "rolled_back"]
    assert len(rollback_events) >= 1
    assert rollback_events[0]["final_outcome"] == "ROLLED_BACK"


