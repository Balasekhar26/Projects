from __future__ import annotations

import pytest
import time
import json
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.executive_planner import ExecutivePlanner
from backend.core.goal_memory import GoalMemory
from backend.core.personal_project_manager import PersonalProjectManager


@pytest.fixture(autouse=True)
def clean_db():
    from backend.core.project_memory import ProjectMemory
    GoalMemory._schema_ensured = False
    ProjectMemory._schema_ensured = False
    ExecutivePlanner._schema_ensured = False
    GoalMemory.reset()
    ProjectMemory.reset()

    # Re-initialize ledger
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
        conn.commit()
    finally:
        conn.close()


def test_schema_initialization():
    conn = ExecutivePlanner._get_sqlite_conn()
    try:
        tables = [
            "plan_blueprints", "blueprint_nodes", "blueprint_dependencies",
            "blueprint_agents", "resource_forecasts", "simulation_risks",
            "context_sweeps", "adaptation_tracks", "sim_calibrations", "global_resource_ledger"
        ]
        for t in tables:
            row = conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{t}'").fetchone()
            assert row is not None, f"Table {t} does not exist!"
    finally:
        conn.close()


def test_memory_sweep():
    sweep = ExecutivePlanner.perform_memory_sweep("Build drone delivery framework")
    assert sweep["extracted_failure_profile"] is not None
    assert "battery capacity" in sweep["extracted_failure_profile"]


def test_constraint_synthesis():
    constraints = ExecutivePlanner.synthesize_constraints(
        "Build a solar charging circuit",
        "The project has a budget limit of ₹5000 and should finish in 2 weeks. Avoid paid API options."
    )
    assert constraints["max_budget"] == 5000.0
    assert constraints["max_time_days"] == 14
    assert "paid API" in constraints["avoid_patterns"]


def test_feasibility_gate():
    # Route vs Battery physical limit clash
    feasible, msg = ExecutivePlanner.evaluate_feasibility(
        "Deploy drone delivery route 25 km",
        "Battery range is 15 km",
        {"max_budget": 100.0}
    )
    assert not feasible
    assert "exceeds maximum battery" in msg

    # Perpetual motion check
    feasible, msg = ExecutivePlanner.evaluate_feasibility(
        "Build perpetual motion charger",
        "Generates infinite energy",
        {"max_budget": 100.0}
    )
    assert not feasible
    assert "Violates thermodynamic constraints" in msg

    # Safe plan check
    feasible, msg = ExecutivePlanner.evaluate_feasibility(
        "Develop web interface",
        "Standard react app",
        {"max_budget": 100.0}
    )
    assert feasible


def test_resource_ledger_overcommits_block():
    conn = ExecutivePlanner._get_sqlite_conn()
    try:
        # Overcommit TOKEN_BUDGET
        conn.execute("UPDATE global_resource_ledger SET reserved_units = 9999000.0 WHERE resource_type = 'TOKEN_BUDGET'")
        conn.commit()

        success, msg, _, _ = ExecutivePlanner.allocate_resources_and_agents(
            conn,
            [{"action": "Deploy", "requires_approval": False}] * 5,
            {"max_budget": 100.0}
        )
        assert not success
        assert "RESOURCE_UNAVAILABLE" in msg
    finally:
        conn.close()


def test_attention_backpressure_threshold_block():
    conn = ExecutivePlanner._get_sqlite_conn()
    try:
        # Plan with 10 touchpoints (approvals) exceeds maximum allowable attention budget (8.0)
        success, msg, _, _ = ExecutivePlanner.allocate_resources_and_agents(
            conn,
            [{"action": "Approval step", "requires_approval": True}] * 10,
            {"max_budget": 100.0}
        )
        assert not success
        assert "exceeding attention threshold" in msg
    finally:
        conn.close()


def test_simulation_calibration_brier_score():
    conn = ExecutivePlanner._get_sqlite_conn()
    try:
        # Feed uncalibrated history (Brier score > 0.25)
        # Predicted success: 0.9, Actual success: 0 (Failed)
        now = time.time()
        for i in range(10):
            conn.execute(
                "INSERT INTO sim_calibrations (calibration_id, domain, predicted_success_rate, actual_success, timestamp) VALUES (?, 'Robotics', 0.9, 0, ?)",
                (f"cal_{i}", now)
            )
        conn.commit()

        scale = ExecutivePlanner.calculate_calibration_factor(conn, "Robotics")
        assert scale == 1.2  # Gate widened by 1.2x due to poor simulation calibration
    finally:
        conn.close()


def test_create_and_deploy_executive_plan():
    steps = [
        {"action": "Research circuit design", "requires_approval": False, "effort": 3},
        {"action": "Fabricate PCB prototype", "requires_approval": True, "effort": 6},
        {"action": "Validate daily charging rate", "requires_approval": True, "effort": 5}
    ]

    res = ExecutivePlanner.create_executive_plan(
        goal_id="goal_solar_cover",
        plan_title="Build solar-powered phone cover",
        plan_description="Recharge battery via photodiode. Target: >10% daily recharge rate.",
        plan_steps=steps,
        domain="Hardware"
    )
    assert res["status"] == "ok"
    assert res["blueprint_status"] == "APPROVED"
    assert res["blueprint_id"] is not None

    blueprint_id = res["blueprint_id"]

    # Deploy to PPM
    dep_res = ExecutivePlanner.deploy_blueprint_to_ppm(blueprint_id)
    assert dep_res["status"] == "ok"
    assert dep_res["blueprint_status"] == "DEPLOYED_TO_PPM"
    assert dep_res["project_id"] is not None


def test_plan_level_adaptation_and_replan_loop_halt():
    steps = [{"action": "Test software code", "requires_approval": False, "effort": 2}]
    res = ExecutivePlanner.create_executive_plan(
        goal_id="goal_web_app",
        plan_title="Deploy React Dashboard",
        plan_description="Expose metrics via REST.",
        plan_steps=steps,
        domain="Software"
    )
    blueprint_id = res["blueprint_id"]

    dep_res = ExecutivePlanner.deploy_blueprint_to_ppm(blueprint_id)
    project_id = dep_res["project_id"]

    # Adapt plan multiple times (failure loop)
    for i in range(3):
        adapt_res = ExecutivePlanner.adapt_plan(project_id, "ppm_t_failed")
        assert adapt_res["status"] == "ok"

    # 4th adaptation triggers plan-level budget halt and blocks project
    adapt_res = ExecutivePlanner.adapt_plan(project_id, "ppm_t_failed")
    assert adapt_res["status"] == "halted"
    assert "locked in BLOCKED state" in adapt_res["message"]


def test_dashboard_latest_snapshot_tier11():
    # Make sure we generate at least one blueprint
    steps = [{"action": "Test software code", "requires_approval": False, "effort": 2}]
    ExecutivePlanner.create_executive_plan(
        goal_id="goal_web_app_dash",
        plan_title="Deploy React Dashboard Tab",
        plan_description="Expose metrics via REST.",
        plan_steps=steps,
        domain="Software"
    )

    client = TestClient(app)
    resp = client.get("/dashboard/cognitive/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "tier_11_executive" in data["data"]
    tier11 = data["data"]["tier_11_executive"]
    assert tier11["total_blueprints_generated"] == 1
    assert tier11["approved_plans"] == 1


def test_api_plans_create_and_deploy_routes():
    client = TestClient(app)

    # 1. Create plan
    resp = client.post(
        "/dashboard/cognitive/executive/plans",
        json={
            "goal_id": "goal_test_api",
            "plan_title": "Build battery range 30 km",
            "plan_description": "route distance 10 km",
            "plan_steps": [{"action": "Setup", "requires_approval": False}],
            "domain": "Logistics"
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    blueprint_id = data["blueprint_id"]

    # 2. Get details
    resp = client.get(f"/dashboard/cognitive/executive/plans/{blueprint_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["blueprint"]["blueprint_id"] == blueprint_id

    # 3. Deploy
    resp = client.post(f"/dashboard/cognitive/executive/plans/{blueprint_id}/deploy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["blueprint_status"] == "DEPLOYED_TO_PPM"
    project_id = data["project_id"]

    # 4. Adapt
    resp = client.post(
        f"/dashboard/cognitive/executive/plans/{project_id}/adapt",
        json={"failed_task_id": "ppm_t_test"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["replan_count"] == 1
