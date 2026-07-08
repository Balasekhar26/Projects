from __future__ import annotations

import pytest
from backend.core.simulation_engine import SimulationEngine, PlanStep


@pytest.fixture(autouse=True)
def isolated_cal_db(tmp_path, monkeypatch):
    from backend.core.config import BackendConfig
    import backend.core.config as config_module
    
    test_db = tmp_path / "kattappa_cal_test.db"
    
    mock_config = BackendConfig(
        root=tmp_path,
        backend_root=tmp_path,
        ollama_host="http://127.0.0.1:11434",
        model_map={},
        chroma_path=tmp_path / "chroma",
        sqlite_path=test_db,
        memory_collection="kattappa_memory",
        shell_enabled=False,
        desktop_enabled=True,
        screen_capture_enabled=False,
        guidance_overlay_enabled=True,
        teach_mode_enabled=True,
        screenshots_dir=tmp_path / "screenshots",
        audio_dir=tmp_path / "audio",
        logs_dir=tmp_path / "logs",
        workspace_dir=tmp_path / "workspace",
        hardware_profile="BALANCED",
        context_budget=4096,
    )
    
    monkeypatch.setattr(config_module, "load_config", lambda: mock_config)
    monkeypatch.setenv("KATTAPPA_DATA_DIR", str(tmp_path))
    yield test_db


def test_decision_forecast_and_outcome_logging(isolated_cal_db):
    SimulationEngine.record_decision_forecast(
        decision_id="dec_1",
        decision="Upgrade Reflection Layer",
        predicted_success=0.80,
        predicted_cost=3.2,
        predicted_time="4 days"
    )
    
    conn = SimulationEngine._get_sqlite_conn()
    row = conn.execute("SELECT * FROM decision_forecasts WHERE decision_id = ?", ("dec_1",)).fetchone()
    assert row is not None
    assert row["decision"] == "Upgrade Reflection Layer"
    assert row["predicted_success"] == 0.80
    assert row["status"] == "pending"
    
    SimulationEngine.record_decision_outcome(
        decision_id="dec_1",
        actual_success=0.60,
        actual_cost=3.8,
        actual_time="5 days"
    )
    
    row2 = conn.execute("SELECT * FROM decision_forecasts WHERE decision_id = ?", ("dec_1",)).fetchone()
    assert row2["actual_success"] == 0.60
    assert row2["actual_cost"] == 3.8
    assert row2["actual_time"] == "5 days"
    assert row2["status"] == "resolved"
    conn.close()


def test_calibration_error_and_prediction_adjustment(isolated_cal_db):
    # 1. Run baseline simulation
    plan = [{"step_id": "step1", "agent": "browser", "action": "SEARCH_WEB"}]
    baseline_report = SimulationEngine.simulate_plan(plan)
    baseline_prob = baseline_report.success_probability
    
    # 2. Add forecast data indicating system is over-confident (predicts 0.8, reality is 0.4)
    SimulationEngine.record_decision_forecast("dec_a", "Refactor memory", 0.8, 10, "1 day")
    SimulationEngine.record_decision_outcome("dec_a", 0.4, 12, "1.2 days")
    
    SimulationEngine.record_decision_forecast("dec_b", "Optimize indexing", 0.8, 20, "2 days")
    SimulationEngine.record_decision_outcome("dec_b", 0.4, 25, "2.5 days")
    
    # 3. Recalibrate
    cal_results = SimulationEngine.recalibrate_from_ledger()
    assert cal_results["status"] == "success"
    assert cal_results["total_decisions"] == 2
    # MAE = abs(0.8 - 0.4) = 0.4
    assert abs(cal_results["mean_absolute_error"] - 0.4) < 0.001
    assert abs(cal_results["root_mean_squared_error"] - 0.4) < 0.001
    
    # 4. Check that global calibration modifier adjusts future plan predictions
    # Calibration ratio = 0.4 / 0.8 = 0.5
    # Future prediction should be scaled down by 0.5
    calibrated_report = SimulationEngine.simulate_plan(plan)
    calibrated_prob = calibrated_report.success_probability
    
    assert calibrated_prob < baseline_prob
    assert abs(calibrated_prob - (baseline_prob * 0.5)) < 0.05
