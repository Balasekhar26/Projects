import pytest

from backend.core.goal_hierarchy import GoalHierarchy, HierarchyLevel
from backend.core.ecl.goal_decomposer import ECLGoalDecomposer
from backend.core.ecl.policy_engine import ECLPolicyEngine
from backend.core.ecl.budget_manager import ECLBudgetManager
from backend.core.ecl.simulation_runner import ECLSimulationRunner
from backend.core.ecl.router import ECLRouter
from backend.core.ecl.coordinator import ECLCoordinator


@pytest.fixture(autouse=True)
def clean_goal_hierarchy_db(tmp_path):
    """Ensures each test gets a clean goal hierarchy database."""
    temp_db_path = str(tmp_path / "goal_hierarchy_test.db")
    
    orig_get_conn = GoalHierarchy._get_conn
    
    def mock_get_conn():
        import sqlite3
        conn = sqlite3.connect(temp_db_path)
        conn.row_factory = sqlite3.Row
        GoalHierarchy._ensure_schema(conn)
        return conn
        
    GoalHierarchy._get_conn = mock_get_conn
    
    yield
    
    GoalHierarchy._get_conn = orig_get_conn


def test_goal_decomposition_registers_nodes():
    res = ECLGoalDecomposer.decompose(
        goal_title="Refactor Frontend Bundle Size",
        goal_desc="Optimize JS splits"
    )
    assert res["goal_id"].startswith("goal_")
    assert res["title"] == "Refactor Frontend Bundle Size"
    
    # Query database nodes
    conn = GoalHierarchy._get_conn()
    try:
        nodes = conn.execute("SELECT * FROM goal_hierarchy").fetchall()
        # Verify Level 1, 2, and 3 nodes are registered
        levels = [n["level"] for n in nodes]
        assert "GOAL" in levels
        assert "SUBGOAL" in levels
        assert "TASK" in levels
    finally:
        conn.close()


def test_policy_engine_validation():
    # Safe plan
    safe_steps = [{"title": "Optimize images", "description": "Compress raw assets"}]
    valid, reason = ECLPolicyEngine.validate_plan("Optimize UI Assets", safe_steps)
    assert valid is True
    assert reason is None
    
    # Unsafe plan (Violates deletion policy)
    unsafe_steps = [{"title": "Clear workspace", "description": "Run rm -rf /"}]
    valid, reason = ECLPolicyEngine.validate_plan("Cleanup Target", unsafe_steps)
    assert valid is False
    assert "Unverified broad deletion prohibited" in reason


def test_budget_allocations():
    low_budget = ECLBudgetManager.calculate_budget("LOW")
    assert low_budget["token_limit"] == 5000
    assert low_budget["time_limit_sec"] == 10.0
    
    high_budget = ECLBudgetManager.calculate_budget("HIGH")
    assert high_budget["token_limit"] == 50000
    assert high_budget["time_limit_sec"] == 60.0


def test_simulation_runner_viability_scores():
    steps = [
        {"task_id": "t1", "action": "read_files", "params": {"path": "."}},
        {"task_id": "t2", "action": "delete_backup", "params": {"target": "backup.tar.gz"}}
    ]
    res = ECLSimulationRunner.evaluate_viability("Task Deletion Flow", steps)
    assert res["success"] is True
    assert "best_branch_id" in res
    assert len(res["branch_reports"]) > 0


def test_router_model_and_tool_mapping():
    # Code keywords route to coder
    route_code = ECLRouter.route_task("Write a python script to parse logs")
    assert route_code["model_role"] == "coder"
    assert route_code["recommended_tool"] == "file_agent"
    
    # Reason keywords route to general/power
    route_reason = ECLRouter.route_task("Explain difference between threads and processes")
    assert route_reason["model_role"] in ("general", "power")
    
    # Default general routing
    route_gen = ECLRouter.route_task("Say hello to the operator")
    assert route_gen["model_role"] == "general"


def test_ecl_coordinator_transaction():
    # End-to-end execution of a clean ECL transaction
    res = ECLCoordinator.plan_and_execute(
        goal_title="Verify Local Cache Integrity",
        goal_desc="Validate hashes of active files",
        priority="LOW"
    )
    assert res["success"] is True
    assert res["status"] == "COMPLETED"
    assert res["viability_score"] > 0.0
