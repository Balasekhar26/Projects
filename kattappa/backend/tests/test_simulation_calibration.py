from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.config import load_config, BackendConfig
from backend.core.simulation_calibration import SimulationCalibrator
from backend.core.simulation_engine import SimulationEngine, PlanStep


@pytest.fixture(autouse=True)
def mock_db_and_weights(tmp_path, monkeypatch):
    original_config = load_config()
    test_db = tmp_path / "kattappa_test.db"
    test_weights = tmp_path / "backend" / "data" / "simulation_calibration_weights.json"

    # Configure custom config with test paths
    test_config = BackendConfig(
        root=original_config.root,
        backend_root=original_config.backend_root,
        ollama_host=original_config.ollama_host,
        model_map=original_config.model_map,
        chroma_path=original_config.chroma_path,
        sqlite_path=test_db,
        memory_collection=original_config.memory_collection,
        shell_enabled=original_config.shell_enabled,
        desktop_enabled=original_config.desktop_enabled,
        screen_capture_enabled=original_config.screen_capture_enabled,
        guidance_overlay_enabled=original_config.guidance_overlay_enabled,
        teach_mode_enabled=original_config.teach_mode_enabled,
        screenshots_dir=original_config.screenshots_dir,
        audio_dir=original_config.audio_dir,
        logs_dir=original_config.logs_dir,
        workspace_dir=original_config.workspace_dir,
        hardware_profile=original_config.hardware_profile,
        context_budget=original_config.context_budget,
    )
    monkeypatch.setattr("backend.core.config.load_config", lambda: test_config)
    monkeypatch.setattr("backend.core.simulation_calibration.load_config", lambda: test_config)
    monkeypatch.setattr("backend.core.workflow_memory.load_config", lambda: test_config)
    monkeypatch.setattr("backend.core.simulation_calibration.runtime_data_root", lambda: tmp_path)
    monkeypatch.setattr("backend.core.action_memory.runtime_data_root", lambda: tmp_path)

    # Reset calibrator caches
    SimulationCalibrator._schema_ensured = False
    SimulationCalibrator._cached_weights = {}
    yield test_db, test_weights


def test_simulation_calibrator_flow(mock_db_and_weights):
    _, weights_file = mock_db_and_weights

    # Record some predictions & actual outcomes
    # 1. Coder: success predicted 0.8, actual success False (0.0) -> overpredicted success
    # 2. Coder: success predicted 0.8, actual success True (1.0) -> correct
    # Avg predicted success = 0.8, Avg actual = 0.5. Calibration factor = 0.5 / 0.8 = 0.625
    SimulationCalibrator.record_prediction_outcome(
        agent="coder",
        action="RUN_TESTS",
        predicted_success=0.8,
        actual_success=False,
        predicted_duration_ms=1000,
        actual_duration_ms=2000,
        predicted_rollback=0.1,
        actual_rollback=True,
    )
    SimulationCalibrator.record_prediction_outcome(
        agent="coder",
        action="RUN_TESTS",
        predicted_success=0.8,
        actual_success=True,
        predicted_duration_ms=1000,
        actual_duration_ms=1000,
        predicted_rollback=0.1,
        actual_rollback=False,
    )

    report = SimulationCalibrator.recalibrate()
    assert report["status"] == "success"
    assert report["count"] == 2
    assert report["brier_score"] == pytest.approx(0.34, abs=0.01) # error1: (0.8-0.0)^2 = 0.64; error2: (0.8-1.0)^2 = 0.04; mean = 0.34

    weights = SimulationCalibrator.get_all_weights()
    assert "coder:RUN_TESTS" in weights
    assert weights["coder:RUN_TESTS"]["success_factor"] == pytest.approx(0.625)
    assert weights["coder:RUN_TESTS"]["duration_factor"] == pytest.approx(1.5)
    assert weights["coder:RUN_TESTS"]["rollback_factor"] == pytest.approx(2.0) # clamped max limit is 2.0

    assert weights_file.exists()


def test_simulation_engine_dynamic_calibration_integration(mock_db_and_weights):
    # Setup test weights directly to override prediction behavior
    weights = {
        "coder:RUN_TESTS": {
            "success_factor": 0.5,
            "duration_factor": 2.0,
            "rollback_factor": 1.5,
        }
    }
    SimulationCalibrator._cached_weights = weights

    step = PlanStep(step_id="step_test", agent="coder", action="RUN_TESTS")
    prediction, _, _ = SimulationEngine._predict_step(
        step,
        active_policies=[],
        reflection_agent_stats={},
        reflection_recommendations=[],
        context={},
    )

    # Let's verify that success_probability and expected_duration_ms were scaled by our factors!
    # Without calibration factor, predicted duration is 5000ms. scaled duration should be 10000ms
    assert prediction.expected_duration_ms == 10000


def test_calibration_api(mock_db_and_weights):
    client = TestClient(app)
    response = client.post(
        "/cognitive/calibration/record",
        json={
            "agent": "browser",
            "action": "SEARCH_WEB",
            "predicted_success": 0.9,
            "actual_success": True,
            "predicted_duration_ms": 1000,
            "actual_duration_ms": 900,
            "predicted_rollback": 0.05,
            "actual_rollback": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    recal = client.post("/cognitive/calibration/recalibrate")
    assert recal.status_code == 200
    assert recal.json()["report"]["status"] == "success"

    weights = client.get("/cognitive/calibration/weights")
    assert weights.status_code == 200
    assert "browser:SEARCH_WEB" in weights.json()["weights"]


def test_simulation_engine_workflow_memory_calibration(mock_db_and_weights):
    from backend.core.workflow_memory import WorkflowMemory

    # Save a successful workflow run
    steps_1 = [
        {"agent": "coder", "action": "WRITE_FILE", "success": True, "duration_ms": 1000},
        {"agent": "coder", "action": "RUN_TESTS", "success": True, "duration_ms": 2000},
    ]
    WorkflowMemory.save_workflow_run(
        workflow_id="wf_emp_1",
        goal="Build and test core code",
        status="completed",
        success=True,
        total_duration_ms=3000,
        steps=steps_1,
    )

    # Save a failed workflow run (duration 6000ms, with a rollback)
    steps_2 = [
        {"agent": "coder", "action": "WRITE_FILE", "success": True, "duration_ms": 1000},
        {"agent": "coder", "action": "RUN_TESTS", "success": False, "duration_ms": 5000, "rollback_executed": True, "rollback_success": True},
    ]
    WorkflowMemory.save_workflow_run(
        workflow_id="wf_emp_2",
        goal="Build and test core code",
        status="completed",
        success=False,
        total_duration_ms=6000,
        steps=steps_2,
    )

    # Simulate a plan with same steps/goal
    plan = [
        {"step_id": "s1", "agent": "coder", "action": "WRITE_FILE"},
        {"step_id": "s2", "agent": "coder", "action": "RUN_TESTS"},
    ]
    report = SimulationEngine.simulate_plan(
        plan=plan,
        goal="Build and test core code"
    )

    report_dict = report.to_dict()
    # verify calibration incorporates empirical data
    assert report_dict["goal"] == "Build and test core code"
    assert report_dict["success_probability"] == pytest.approx(0.48, abs=0.02)
    assert report_dict["rollback_risk"] == pytest.approx(0.23, abs=0.02)
    assert report_dict["estimated_duration_ms"] > 0
    assert len(report_dict["likely_failures"]) > 0
