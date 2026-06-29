from __future__ import annotations

import json
import pytest
from backend.core.executive_planner import ExecutivePlanner
from backend.core.cognitive_simulation_sandbox import VerificationPredictionEngine
from backend.core.reflection_engine import ReflectionEngine
from backend.core.human_memory import HumanMemory
from backend.core.reasoning_engine import ReasoningEngine
from backend.core.goal_memory import GoalMemory


@pytest.fixture(autouse=True)
def clean_db():
    from backend.core.project_memory import ProjectMemory
    GoalMemory._schema_ensured = False
    ProjectMemory._schema_ensured = False
    ExecutivePlanner._schema_ensured = False
    GoalMemory.reset()
    ProjectMemory.reset()

    # Re-initialize ledger and ensure schemas
    conn = ExecutivePlanner._get_sqlite_conn()
    try:
        conn.execute("DELETE FROM sim_calibrations")
        conn.execute("DELETE FROM global_resource_ledger")
        conn.execute("DELETE FROM adaptation_tracks")
        conn.execute("DELETE FROM simulation_risks")
        conn.execute("DELETE FROM resource_forecasts")
        conn.execute("DELETE FROM blueprint_dependencies")
        conn.execute("DELETE FROM blueprint_agents")
        conn.execute("DELETE FROM blueprint_nodes")
        conn.execute("DELETE FROM plan_blueprints")
        conn.execute("DELETE FROM planner_candidates")
        for r_type, cap in [("TOKEN_BUDGET", 10000000.0), ("COMPUTE_CORES", 64.0), ("HUMAN_ATTENTION_TOKENS", 100.0)]:
            conn.execute(
                "INSERT OR REPLACE INTO global_resource_ledger (resource_type, total_capacity, reserved_units, consumed_units) VALUES (?, ?, 0.0, 0.0)",
                (r_type, cap)
            )
        conn.commit()
    finally:
        conn.close()

    yield

    conn = ExecutivePlanner._get_sqlite_conn()
    try:
        conn.execute("DELETE FROM sim_calibrations")
        conn.execute("DELETE FROM global_resource_ledger")
        conn.execute("DELETE FROM adaptation_tracks")
        conn.execute("DELETE FROM simulation_risks")
        conn.execute("DELETE FROM resource_forecasts")
        conn.execute("DELETE FROM blueprint_dependencies")
        conn.execute("DELETE FROM blueprint_agents")
        conn.execute("DELETE FROM blueprint_nodes")
        conn.execute("DELETE FROM plan_blueprints")
        conn.execute("DELETE FROM planner_candidates")
        conn.commit()
    finally:
        conn.close()


def test_planner_v2_candidates_generation():
    steps = [
        {"action": "Check configuration file", "description": "Ensure configuration path is valid.", "effort": 2},
        {"action": "Deploy production modules", "description": "Run installation sequences.", "effort": 5}
    ]
    res = ExecutivePlanner.create_executive_plan(
        goal_id="goal_planner_v2_test",
        plan_title="Deploy Backend Services",
        plan_description="Verify that port 8000 and target host are specified.",
        plan_steps=steps,
        domain="DevOps"
    )
    assert res["status"] == "ok"
    assert res["blueprint_status"] == "APPROVED"
    assert res["blueprint_id"] is not None

    # Check candidates table directly
    conn = ExecutivePlanner._get_sqlite_conn()
    try:
        rows = conn.execute("SELECT * FROM planner_candidates WHERE goal_id = ? ORDER BY created_at DESC", ("goal_planner_v2_test",)).fetchall()
        assert len(rows) == 3
        names = {r["plan_name"] for r in rows}
        assert "Plan A: Standard Path" in names
        assert "Plan B: Cautious Path" in names
        assert "Plan C: Fast Path" in names

        # Exactly one SELECTED, others REJECTED
        selected = [r for r in rows if r["selection_status"] == "SELECTED"]
        rejected = [r for r in rows if r["selection_status"] == "REJECTED"]
        assert len(selected) == 1
        assert len(rejected) == 2
    finally:
        conn.close()


def test_simulation_v2_reversibility_and_token_cost():
    # Optimistic path: no destructive actions
    steps = [
        {"action": "Write new server routing", "description": "Save code blocks to routing.py."}
    ]
    report = VerificationPredictionEngine.predict(success_criteria={}, plan_steps=steps)
    assert report.reversibility_score == 1.0
    assert report.estimated_token_cost == 15000.0

    # Non-reversible: deletion actions present
    steps_destructive = [
        {"action": "Delete database config", "description": "Remove database files."}
    ]
    report_dest = VerificationPredictionEngine.predict(success_criteria={}, plan_steps=steps_destructive)
    assert report_dest.reversibility_score < 1.0
    assert report_dest.estimated_token_cost == 15000.0


def test_reflection_automated_belief_updates():
    # Test reflection triggers low reliability belief
    logs_error = "Traceback (most recent call): exception: ValueError. exit_code=1."
    ReflectionEngine.analyze_and_propose(logs_error)
    
    belief = HumanMemory.get_active_belief("system_stability_status")
    assert belief is not None
    assert "LOW_RELIABILITY_WARNING" in belief["value"]

    # Test reflection triggers high reliability belief
    logs_clean = "Execution successful. Completed run_task. Exiting clean."
    ReflectionEngine.analyze_and_propose(logs_clean)

    belief_clean = HumanMemory.get_active_belief("system_stability_status")
    assert belief_clean is not None
    assert "HIGH_RELIABILITY" in belief_clean["value"]
