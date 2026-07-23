from typing import Any
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
    
    def mock_get_conn(db_path: str | None = None):
        import sqlite3
        conn = sqlite3.connect(temp_db_path)
        conn.row_factory = sqlite3.Row
        GoalHierarchy._ensure_schema(conn)
        conn.execute("CREATE VIEW IF NOT EXISTS goal_nodes AS SELECT id, parent_id, level, title, status, progress, created_at, created_at AS updated_at FROM goal_hierarchy")
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
    assert "phase_timings" in res
    assert "goal_decomposition" in res["phase_timings"]
    assert "task_graph_execution" in res["phase_timings"]
    assert res["cleanup_complete"] is True


def test_ecl_policy_halt_structured_response():
    res = ECLCoordinator.plan_and_execute(
        goal_title="Purge all user databases with rm -rf /",
        goal_desc="Force delete production files",
        priority="HIGH"
    )
    assert res["success"] is False
    assert res["status"] == "FAILED"
    assert res["failed_phase"] == "policy_validation"
    assert res["error_type"] == "PolicyHalt"
    assert "error_message" in res
    assert res["cleanup_complete"] is True


def test_ecl_monotonic_deadline_timeout():
    # Execute with very short timeout to trigger deadline cancellation
    res = ECLCoordinator.plan_and_execute(
        goal_title="Long running computation step",
        goal_desc="Simulate delay",
        priority="LOW",
        timeout=0.001  # Ultra short timeout force-cancels execution
    )
    assert res["success"] is False
    assert res["status"] == "TIMEOUT"
    assert res["failed_phase"] == "task_graph_execution"
    assert res["error_type"] == "TimeoutError"
    assert res["cleanup_complete"] is True


def test_ecl_task_failure_results_in_failed_status():
    from backend.core.orchestrator.scheduler import TaskScheduler
    from backend.core.orchestrator.task_graph import TaskGraph
    from backend.core.orchestrator.base import Task, TaskResult, BaseAgent
    from backend.core.orchestrator.registry import AgentRegistry

    class FailingAgent(BaseAgent):
        @property
        def name(self) -> str:
            return "FailingAgent"

        def initialize(self) -> None:
            pass

        def execute(self, task: Task, context: Any) -> TaskResult:
            return TaskResult(success=False, output="", error="Simulated agent failure")

        def terminate(self, task_id: str) -> None:
            pass

    reg = AgentRegistry()
    reg.register(FailingAgent())

    graph = TaskGraph()
    task = Task(task_id="t_fail", agent_name="FailingAgent", action="fail", params={})
    task.max_attempts = 1
    graph.add_task(task)

    scheduler = TaskScheduler(registry=reg, max_workers=2)
    try:
        ctx = scheduler.run_graph(graph, graph_id="g_failing_test", timeout=5.0)
        cleanup = scheduler.check_cleanup_status("g_failing_test")
    finally:
        scheduler.close(wait=True)

    assert task.status == "FAILED"
    assert graph.is_finished() is True


def test_ecl_delayed_retry_interrupted_on_close():
    import time
    import threading
    from backend.core.orchestrator.scheduler import TaskScheduler
    from backend.core.orchestrator.task_graph import TaskGraph
    from backend.core.orchestrator.base import Task, TaskResult, BaseAgent
    from backend.core.orchestrator.registry import AgentRegistry

    class RetryableFailingAgent(BaseAgent):
        @property
        def name(self) -> str:
            return "RetryAgent"

        def initialize(self) -> None:
            pass

        def execute(self, task: Task, context: Any) -> TaskResult:
            return TaskResult(success=False, output="", error="Retryable error")

        def terminate(self, task_id: str) -> None:
            pass

    reg = AgentRegistry()
    reg.register(RetryableFailingAgent())

    graph = TaskGraph()
    task = Task(task_id="t_retry", agent_name="RetryAgent", action="retry", params={})
    task.max_attempts = 3
    graph.add_task(task)

    scheduler = TaskScheduler(registry=reg, max_workers=2)
    
    # Run graph in background thread
    bg_thread = threading.Thread(target=scheduler.run_graph, args=(graph, "g_retry_test"), kwargs={"timeout": 10.0})
    bg_thread.start()

    time.sleep(0.1)
    # Cancel graph immediately while retry thread is sleeping
    scheduler.cancel_graph("g_retry_test")
    scheduler.close(wait=True)
    bg_thread.join(timeout=2.0)

    cleanup = scheduler.check_cleanup_status()
    assert cleanup["active_retry_workers_remaining"] == 0
    assert cleanup["active_graphs_remaining"] == 0
    assert cleanup["cleanup_complete"] is True


