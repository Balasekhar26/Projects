import pytest
import os
import tempfile
from backend.agents.planner import TaskGraph, TaskStep
from backend.core.memory.memory_store import MemoryStore
from backend.core.evaluation.evaluation_engine import EvaluationEngine
from backend.core.planner.planner_engine import PlannerEngine

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_eval_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    MemoryStore.clear_database()
    yield temp_dir
    MemoryStore.clear_database()

def test_prediction_storage() -> None:
    EvaluationEngine.record_prediction(
        task_id="t1",
        predicted_confidence=0.90,
        predicted_duration=45.0,
        predicted_memory_usage=1.5,
        predicted_success_probability=0.95
    )
    
    conn = MemoryStore._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM execution_predictions WHERE task_id = 't1'")
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["predicted_confidence"] == 0.90
    assert rows[0]["predicted_success_probability"] == 0.95

def test_drift_calculation_and_calibration_update() -> None:
    EvaluationEngine.record_prediction(
        task_id="t_drift",
        predicted_confidence=0.90,
        predicted_duration=30.0,
        predicted_memory_usage=1.0,
        predicted_success_probability=0.95
    )
    
    EvaluationEngine.record_outcome(
        task_id="t_drift",
        actual_duration=35.0,
        actual_memory_usage=1.2,
        actual_cpu_usage=10.0,
        success=True
    )
    
    conn = MemoryStore._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM confidence_drift WHERE task_id = 't_drift'")
    drift_rows = cursor.fetchall()
    assert len(drift_rows) == 1
    assert abs(drift_rows[0]["prediction_error"] - (-0.05)) < 1e-4
    assert abs(drift_rows[0]["confidence_error"] - (-0.10)) < 1e-4

    calib = MemoryStore.get_calibration("confidence")
    assert calib is not None
    assert calib["current_bias"] == -0.10
    assert abs(calib["correction_factor"] - 1.10) < 1e-4

def test_calibrate_confidence_scaling() -> None:
    MemoryStore.update_calibration(
        metric_name="confidence",
        current_bias=0.15,
        correction_factor=0.85
    )
    
    calibrated = EvaluationEngine.calibrate_confidence(0.90)
    assert calibrated == 0.77

def test_planner_integration_calibration() -> None:
    MemoryStore.update_calibration(
        metric_name="confidence",
        current_bias=0.20,
        correction_factor=0.80
    )
    
    graph = PlannerEngine.decompose("compile java project")
    assert graph.debate_confidence == 0.79
