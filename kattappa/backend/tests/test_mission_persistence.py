import pytest
import time
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.mission_state import MissionState
from backend.core.mission_checkpoint import MissionCheckpoint
from backend.core.mission_graph import MissionGraph
from backend.core.failure_recovery import FailureRecoveryEngine
from backend.core.mission_forecasting import MissionForecasting
from backend.core.cross_mission_learning import CrossMissionLearning


@pytest.fixture(autouse=True)
def mock_persistent_paths(monkeypatch, tmp_path):
    # Route all JSON file paths to temp directories during tests
    monkeypatch.setattr("backend.core.mission_state._state_file_path", lambda: tmp_path / "mission_states.json")
    monkeypatch.setattr("backend.core.mission_checkpoint._checkpoint_file_path", lambda: tmp_path / "mission_checkpoints.json")
    monkeypatch.setattr("backend.core.failure_recovery._failure_file_path", lambda: tmp_path / "failure_recovery.json")
    monkeypatch.setattr("backend.core.cross_mission_learning._knowledge_file_path", lambda: tmp_path / "cross_mission_knowledge.json")
    monkeypatch.setattr("backend.core.mission_memory._mission_file_path", lambda: tmp_path / "mission_memory.json")


def test_checkpointing_and_rollback():
    # Make sure we start with empty/seeded state
    states = MissionState.load_states()
    assert "mis_drone_jam" in states

    # 1. Setup a test mission
    mission_id = "mis_test_persistence"
    initial_state = {
        "id": mission_id,
        "stage": "Research",
        "progress": 25.0,
        "blocked": False,
        "blockers": [],
        "resources": ["Test Resource"],
        "confidence_score": 0.9,
        "next_action": "Initial step.",
        "completed_stages": [],
        "pending_stages": ["Research", "Design", "Verify"]
    }
    MissionState.set_state(mission_id, initial_state)

    # Verify state was saved
    retrieved = MissionState.get_state(mission_id)
    assert retrieved is not None
    assert retrieved["progress"] == 25.0

    # 2. Create checkpoint
    chp = MissionCheckpoint.create_checkpoint(mission_id, retrieved)
    assert chp["checkpoint_id"].startswith("chp_")
    assert chp["snapshot_data"]["progress"] == 25.0

    # 3. Modify state to represent progress failure
    MissionState.update_progress(mission_id, progress=50.0, stage="Design")
    current_state = MissionState.get_state(mission_id)
    assert current_state["progress"] == 50.0
    assert current_state["stage"] == "Design"

    # 4. Rollback to checkpoint
    rolled_back = MissionCheckpoint.rollback_to_checkpoint(mission_id, chp["checkpoint_id"])
    assert rolled_back is not None
    assert rolled_back["progress"] == 25.0
    assert rolled_back["stage"] == "Research"

    # Verify state in storage has reverted
    stored_state = MissionState.get_state(mission_id)
    assert stored_state["progress"] == 25.0
    assert stored_state["stage"] == "Research"


def test_mission_graph_gatekeeping():
    stages = ["Research", "Design", "Simulation", "Testing", "Documentation"]
    
    # Prerequisite of Research is empty
    assert MissionGraph.get_prerequisites(stages, "Research") == []
    # Prerequisite of Design is Research
    assert MissionGraph.get_prerequisites(stages, "Design") == ["Research"]
    # Prerequisite of Simulation is Research and Design
    assert MissionGraph.get_prerequisites(stages, "Simulation") == ["Research", "Design"]

    # Test can_transition
    assert MissionGraph.can_transition(stages, completed_stages=[], target_stage="Research") is True
    assert MissionGraph.can_transition(stages, completed_stages=[], target_stage="Design") is False
    assert MissionGraph.can_transition(stages, completed_stages=["Research"], target_stage="Design") is True
    assert MissionGraph.can_transition(stages, completed_stages=["Research"], target_stage="Simulation") is False
    assert MissionGraph.can_transition(stages, completed_stages=["Research", "Design"], target_stage="Simulation") is True

    # Test validate_transition raises error
    MissionGraph.validate_transition(stages, completed_stages=["Research"], target_stage="Design") # Should not raise
    with pytest.raises(ValueError) as excinfo:
        MissionGraph.validate_transition(stages, completed_stages=[], target_stage="Simulation")
    assert "Prerequisite stages not completed: Research, Design" in str(excinfo.value)


def test_failure_recovery_rca_and_retry_limits():
    mission_id = "mis_retry_test"
    initial_state = {
        "id": mission_id,
        "stage": "Design",
        "progress": 40.0,
        "blocked": False,
        "blockers": [],
        "resources": [],
        "confidence_score": 0.8,
        "next_action": "Compile front-end code.",
        "completed_stages": ["Research"],
        "pending_stages": ["Design", "Verify"]
    }
    MissionState.set_state(mission_id, initial_state)

    # First Failure -> retry_count = 1
    fail1 = FailureRecoveryEngine.trigger_failure(
        mission_id=mission_id,
        stage="Design",
        agent="Coder",
        reason="Vite React compile syntax error in App.tsx"
    )
    assert fail1["retry_count"] == 1
    assert "syntax issues" in fail1["recovery_path"].lower()
    
    # State should be blocked & waiting approval
    state = MissionState.get_state(mission_id)
    assert state["blocked"] is True
    assert state["status"] == "waiting_approval"
    assert len(state["blockers"]) == 1

    # Second Failure -> retry_count = 2
    fail2 = FailureRecoveryEngine.trigger_failure(
        mission_id=mission_id,
        stage="Design",
        agent="Coder",
        reason="Vite compile syntax error remains unresolved"
    )
    assert fail2["retry_count"] == 2
    assert state["blocked"] is True

    # Third Failure -> retry_count = 3 (Max retries exceeded)
    fail3 = FailureRecoveryEngine.trigger_failure(
        mission_id=mission_id,
        stage="Design",
        agent="Coder",
        reason="Vite compile syntax error fails to fix after manual patch"
    )
    assert fail3["retry_count"] == 3
    
    # State should now freeze to status='failed'
    state = MissionState.get_state(mission_id)
    assert state["status"] == "failed"
    assert "Unrecoverable stage failures" in state["blockers"][0]

    # Test recovery resolution
    FailureRecoveryEngine.resolve_failure(fail3["failure_id"])
    state = MissionState.get_state(mission_id)
    assert state["blocked"] is False
    assert state["status"] == "running"


def test_mission_forecasting():
    # 1. Test non-existent mission forecast
    fc_none = MissionForecasting.get_forecast("non_existent_id")
    assert fc_none["completion_percentage"] == 0.0
    assert fc_none["risk_score"] == 10.0

    # 2. Test healthy mission forecast
    mission_id = "mis_forecast_test"
    state = {
        "id": mission_id,
        "stage": "Research",
        "progress": 50.0,
        "blocked": False,
        "blockers": [],
        "pending_stages": ["Research", "Design", "Verify"]
    }
    MissionState.set_state(mission_id, state)
    
    fc_healthy = MissionForecasting.get_forecast(mission_id)
    assert fc_healthy["completion_percentage"] == 50.0
    assert fc_healthy["risk_score"] == 10.0
    assert fc_healthy["success_probability"] == 95.0
    # Time remaining: (100 - 50) * 2 = 100
    assert fc_healthy["time_remaining_minutes"] == 100.0

    # 3. Test blocked mission forecast
    MissionState.set_blocked(mission_id, blocked=True, blocker="Missing RF hardware license")
    fc_blocked = MissionForecasting.get_forecast(mission_id)
    assert fc_blocked["risk_score"] == 40.0 # base_risk(10) + blocked_penalty(30)
    assert fc_blocked["success_probability"] == 75.0 # base_success(95) - blocked_penalty(20)
    assert fc_blocked["time_remaining_minutes"] == 145.0 # 100 + 45.0 penalty

    # 4. Add active failures to forecast
    FailureRecoveryEngine.trigger_failure(
        mission_id=mission_id,
        stage="Research",
        agent="Researcher",
        reason="API connection timed out"
    )
    fc_failed = MissionForecasting.get_forecast(mission_id)
    # base_risk = 10 + 30 (blocked) + 15 (1 active failure) = 55.0
    # base_success = 95 - 20 (blocked) - 10 (1 active failure) = 65.0
    assert fc_failed["risk_score"] == 55.0
    assert fc_failed["success_probability"] == 65.0


def test_cross_mission_warnings():
    # Publish finding
    entry = CrossMissionLearning.publish_finding(
        mission_id="mis_drone_jam",
        topic="STM32 SPI Clock Speed Bug",
        details="SPI clock prescaler triggers latency errors on STM32F4."
    )
    assert entry["knowledge_id"].startswith("knw_")
    assert entry["topic"] == "STM32 SPI Clock Speed Bug"

    # Scan for matches
    warnings1 = CrossMissionLearning.scan_for_warnings("Running testing with STM32 SPI communications.")
    assert len(warnings1) >= 1
    assert any(w["topic"] == "STM32 SPI Clock Speed Bug" for w in warnings1)

    # Try scan that doesn't match
    warnings2 = CrossMissionLearning.scan_for_warnings("Running FastAPI server deploy script.")
    assert len(warnings2) == 0


def test_dashboard_apis_and_integration():
    client = TestClient(app)

    # 1. GET /dashboard/executive-brain/persistent-missions
    resp = client.get("/dashboard/executive-brain/persistent-missions")
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "ok"
    assert "active_missions" in res_data["data"]
    assert "recovery_queue" in res_data["data"]
    assert "cross_learning" in res_data["data"]

    # 2. POST /dashboard/executive-brain/cross-learning/publish
    pub_resp = client.post("/dashboard/executive-brain/cross-learning/publish", json={
        "mission_id": "mis_drone_jam",
        "topic": "FastAPI Uvicorn Timeout",
        "details": "Increasing worker count resolves concurrency starvation."
    })
    assert pub_resp.status_code == 200
    pub_data = pub_resp.json()
    assert pub_data["status"] == "ok"
    assert pub_data["data"]["topic"] == "FastAPI Uvicorn Timeout"

    # Trigger a failure to test manual resolution endpoint
    fail = FailureRecoveryEngine.trigger_failure(
        mission_id="mis_drone_jam",
        stage="Design",
        agent="Coder",
        reason="API connection timed out"
    )

    # 3. POST /dashboard/executive-brain/missions/recover
    rec_resp = client.post("/dashboard/executive-brain/missions/recover", json={
        "failure_id": fail["failure_id"]
    })
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert rec_data["status"] == "ok"
    assert "resolved" in rec_data["message"].lower()

    # Verify in-memory state is resolved
    failures = FailureRecoveryEngine.load_failures()
    assert any(f["failure_id"] == fail["failure_id"] and f["resolved"] for f in failures)
