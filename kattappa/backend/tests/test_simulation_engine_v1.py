from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture()
def isolated_simulation(tmp_path, monkeypatch):
    import backend.core.action_memory as action_memory_module
    import backend.core.simulation_engine as simulation_engine_module

    monkeypatch.setattr(action_memory_module, "runtime_data_root", lambda: tmp_path)
    monkeypatch.setattr(simulation_engine_module, "runtime_data_root", lambda: tmp_path)
    return tmp_path, action_memory_module.ActionMemory, simulation_engine_module.SimulationEngine


def _seed_action_history(action_memory, action: str, agent: str, successes: int, failures: int) -> None:
    index = 0
    for _ in range(successes):
        action_memory.record(
            action_id=f"{action}_{agent}_ok_{index}",
            workflow_id="wf_seed",
            agent=agent,
            action=action,
            success=True,
            duration_ms=1000 + index,
            confidence_score=0.9,
        )
        index += 1
    for _ in range(failures):
        action_memory.record(
            action_id=f"{action}_{agent}_fail_{index}",
            workflow_id="wf_seed",
            agent=agent,
            action=action,
            success=False,
            duration_ms=2000 + index,
            confidence_score=0.2,
            rollback_executed=True,
        )
        index += 1


def test_plan_simulation_uses_action_memory_history(isolated_simulation):
    _, action_memory, simulation_engine = isolated_simulation
    _seed_action_history(action_memory, "BROWSER_SEARCH", "browser", successes=8, failures=2)
    _seed_action_history(action_memory, "CREATE_FILE", "coder", successes=4, failures=1)

    report = simulation_engine.simulate_plan(
        [
            {"step_id": "s1", "agent": "browser", "action": "BROWSER_SEARCH"},
            {"step_id": "s2", "agent": "coder", "action": "CREATE_FILE"},
        ],
        goal="Find a reference and write a note",
        workflow_id="wf_plan",
    ).to_dict()

    assert report["goal"] == "Find a reference and write a note"
    assert report["workflow_id"] == "wf_plan"
    assert 0.0 < report["success_probability"] < 1.0
    assert report["estimated_duration_ms"] > 0
    assert report["data_sources"]["action_memory"] == "enabled"
    assert report["step_predictions"][0]["evidence_count"] == 10
    assert report["step_predictions"][1]["evidence_count"] == 5
    assert report["likely_failures"]


def test_plan_simulation_applies_strategy_policy_and_reflection_signal(isolated_simulation):
    tmp_path, action_memory, simulation_engine = isolated_simulation
    _seed_action_history(action_memory, "DESKTOP_OPEN_APP", "desktop", successes=5, failures=5)

    data_dir = tmp_path / "backend" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "policy_ledger.json").write_text(
        json.dumps([
            {
                "policy_id": "POL-DESKTOP-DEFER",
                "status": "ACTIVE",
                "title": "Defer unreliable desktop opens",
                "condition": {"agent": "desktop", "action_type": "DESKTOP_OPEN_APP"},
                "effect": {"action": "defer", "cooldown_sec": 2},
            }
        ]),
        encoding="utf-8",
    )
    (data_dir / "reflection_reports.json").write_text(
        json.dumps([
            {
                "report_id": "RPT-SIM",
                "agent_stats": [
                    {
                        "agent": "desktop",
                        "success_rate": 0.40,
                        "avg_confidence": 0.55,
                        "total_actions": 10,
                    }
                ],
                "recommendations": [
                    {
                        "id": "REC-DESKTOP",
                        "priority": "HIGH",
                        "observation": "desktop DESKTOP_OPEN_APP is unreliable",
                        "recommendation": "Use a fallback agent before desktop launch.",
                    }
                ],
            }
        ]),
        encoding="utf-8",
    )

    report = simulation_engine.simulate_plan(
        [{"step_id": "open", "agent": "desktop", "action": "DESKTOP_OPEN_APP"}],
        goal="Open an app",
    ).to_dict()

    step = report["step_predictions"][0]
    assert step["success_probability"] < 0.45
    assert report["policy_adjustments"][0]["policy_id"] == "POL-DESKTOP-DEFER"
    assert report["reflection_signals"]
    assert report["rollback_risk_level"] in {"medium", "high"}
    assert "caution" in report["recommendation"] or "revise" in report["recommendation"]


def test_plan_simulation_api(isolated_simulation):
    _, action_memory, _ = isolated_simulation
    _seed_action_history(action_memory, "RUN_TESTS", "coder", successes=9, failures=1)

    client = TestClient(app)
    response = client.post(
        "/simulate/plan",
        json={
            "goal": "Run validation",
            "workflow_id": "wf_api",
            "plan": [{"step_id": "test", "agent": "coder", "action": "RUN_TESTS"}],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["goal"] == "Run validation"
    assert data["workflow_id"] == "wf_api"
    assert data["step_predictions"][0]["action"] == "RUN_TESTS"
    assert data["success_probability"] > 0.70


def test_empty_plan_simulation_is_safe_noop(isolated_simulation):
    _, _, simulation_engine = isolated_simulation

    report = simulation_engine.simulate_plan([], goal="Nothing to run").to_dict()

    assert report["success_probability"] == 1.0
    assert report["estimated_duration_ms"] == 0
    assert report["recommendation"] == "no executable steps supplied"
