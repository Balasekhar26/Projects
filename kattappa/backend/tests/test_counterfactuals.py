from __future__ import annotations

import json
import pytest
from backend.core.simulation_engine import SimulationEngine, PlanStep


@pytest.fixture(autouse=True)
def isolated_sim_db(tmp_path, monkeypatch):
    from backend.core.config import BackendConfig
    import backend.core.config as config_module
    
    test_db = tmp_path / "kattappa_counter_test.db"
    
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
    yield test_db


def test_counterfactual_engine_execution(isolated_sim_db):
    plan = [
        {"step_id": "step1", "agent": "browser", "action": "SEARCH_WEB"},
        {"step_id": "step2", "agent": "coder", "action": "WRITE_FILE"},
    ]
    
    results = SimulationEngine.run_counterfactual_simulations(
        plan,
        goal="Build feature A",
        workflow_id="wf_cf_test"
    )
    
    assert "run_id" in results
    assert results["goal"] == "Build feature A"
    assert results["workflow_id"] == "wf_cf_test"
    
    scenarios = results["scenarios"]
    assert "Reality" in scenarios
    assert "No Action" in scenarios
    assert "Delay 7 Days" in scenarios
    assert "Budget Decrease 50%" in scenarios
    
    # Verify No Action properties
    no_action = scenarios["No Action"]
    assert no_action["predicted_success"] == 0.0
    assert no_action["predicted_risk"] == 0.0
    assert no_action["predicted_duration_ms"] == 0
    
    # Verify Reality properties
    reality = scenarios["Reality"]
    assert reality["predicted_success"] > 0.0
    assert reality["predicted_duration_ms"] > 0
    
    # Verify Delay 7 Days properties
    delay = scenarios["Delay 7 Days"]
    expected_delay_ms = 7 * 24 * 3600 * 1000
    assert delay["predicted_duration_ms"] == reality["predicted_duration_ms"] + expected_delay_ms
    assert abs(delay["predicted_success"] - reality["predicted_success"] * 0.95) < 0.001
    
    # Verify Budget Decrease 50% properties
    budget = scenarios["Budget Decrease 50%"]
    assert abs(budget["predicted_success"] - reality["predicted_success"] * 0.80) < 0.001
    assert abs(budget["predicted_risk"] - min(0.95, reality["predicted_risk"] * 2.0)) < 0.001
    
    # Check persistence in SQLite
    conn = SimulationEngine._get_sqlite_conn()
    run_row = conn.execute("SELECT * FROM simulation_runs WHERE run_id = ?", (results["run_id"],)).fetchone()
    assert run_row is not None
    assert run_row["goal"] == "Build feature A"
    
    scenario_rows = conn.execute("SELECT * FROM counterfactual_scenarios WHERE run_id = ?", (results["run_id"],)).fetchall()
    assert len(scenario_rows) == 4
    
    scenario_names = [s["name"] for s in scenario_rows]
    assert "Reality" in scenario_names
    assert "No Action" in scenario_names
    assert "Delay 7 Days" in scenario_names
    assert "Budget Decrease 50%" in scenario_names
    
    conn.close()
