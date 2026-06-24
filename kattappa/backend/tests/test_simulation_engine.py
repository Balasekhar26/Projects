from __future__ import annotations

import pytest
import sqlite3
from backend.core.simulation_engine import SimulationEngine, PlanStep


@pytest.fixture(autouse=True)
def isolated_simulation_engine(tmp_path, monkeypatch):
    from backend.core.config import BackendConfig
    from backend.core.action_memory import ActionMemory, AgentStatistics
    import backend.core.config as config_module
    import backend.core.simulation_engine as simulation_engine_module

    test_db = tmp_path / "kattappa_sim_test.db"
    monkeypatch.setenv("KATTAPPA_DATA_DIR", str(tmp_path))

    # Create isolated config
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

    # Patch ActionMemory queries to return empty stats so _predict_step always
    # uses default fallbacks, regardless of shared action_memory.db state.
    def _empty_action_stats(action: str):
        return {
            "action": action,
            "total_executions": 0,
            "success_count": 0,
            "failure_count": 0,
            "success_rate": 0.0,
            "avg_duration_ms": 0.0,
            "avg_confidence": 0.0,
            "rollback_count": 0,
        }

    def _empty_agent_stats(agent: str):
        return AgentStatistics(
            agent=agent,
            total_actions=0,
            success_count=0,
            failure_count=0,
            rollback_count=0,
            success_rate=0.0,
            avg_duration_ms=0.0,
            avg_confidence=0.0,
            rollback_rate=0.0,
        )

    monkeypatch.setattr(ActionMemory, "get_action_type_statistics", staticmethod(_empty_action_stats))
    monkeypatch.setattr(ActionMemory, "get_agent_statistics", classmethod(lambda cls, agent: _empty_agent_stats(agent)))

    # Clear active calibrations
    import backend.core.simulation_calibration as cal_module
    cal_module.SimulationCalibrator._cached_weights = {}

    yield test_db


def test_wilson_confidence_interval():
    # Cold start (evidence_count = 0)
    low, high = SimulationEngine._wilson_interval(0, 0)
    assert low == 0.0
    assert high == 1.0
    
    # Normal case: 8 successes in 10 trials
    low, high = SimulationEngine._wilson_interval(8, 10)
    assert 0.0 < low < high < 1.0
    assert abs(low - 0.49) < 0.1 # low bound should be around 0.49 for 8/10 at 95%
    assert abs(high - 0.94) < 0.1 # high bound should be around 0.94
    
    # Check bounds
    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0


def test_resource_cost_and_risk_score(isolated_simulation_engine):
    step = PlanStep(step_id="step_test", agent="coder", action="RUN_TESTS")
    
    prediction, _, _ = SimulationEngine._predict_step(
        step,
        active_policies=[],
        reflection_agent_stats={},
        reflection_recommendations=[],
        context={},
    )
    
    # Default duration for test/RUN_TESTS action is 5000ms.
    # Coder multiplier is 1.5. Expected resource cost is (5000 / 1000) * 1.5 = 7.5.
    assert prediction.resource_cost == 7.5
    
    # Verify risk score: failure_prob * 0.7 + rollback_risk * 0.3
    expected_risk = prediction.failure_probability * 0.7 + prediction.rollback_risk * 0.3
    assert abs(prediction.risk_score - expected_risk) < 0.001


def test_protected_core_safety_invariant(isolated_simulation_engine):
    # The SimulationEngine must be strictly read-only relative to governance tables.
    # We verify that invoking simulation APIs does not create/write to executive_governance.db
    # or touch permissions tables in the system.
    
    # Ensure no executive governance file exists in temp directory initially
    gov_db_path = isolated_simulation_engine.parent / "executive_governance.db"
    assert not gov_db_path.exists()
    
    # Run a prediction
    SimulationEngine.simulate_plan(
        [{"step_id": "test_step", "agent": "browser", "action": "SEARCH_WEB"}],
        goal="Search something safely"
    )
    
    # Verify no governance DB or tasks were written by the simulator
    assert not gov_db_path.exists()
