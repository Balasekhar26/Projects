"""Unit and integration tests for Program 12.1 HTN Planner Foundation.
"""
from __future__ import annotations

import pytest
from backend.core.planning.goal import Goal
from backend.core.planning.planner_types import GoalPriority, GoalStatus
from backend.core.planning.plan_node import PlanNode
from backend.core.planning.plan import Plan
from backend.core.planning.task_library import TaskLibrary, TaskDefinition
from backend.core.planning.htn_planner import HTNPlanner
from backend.core.execution.typed_errors import ValidationError


def test_goal_and_plan_separation():
    """Verifies that Goal and Plan are separated and represent stable intent vs disposable plan."""
    # Stable Goal
    goal = Goal(
        goal_id="goal-101",
        name="Setup Demo",
        priority=GoalPriority.HIGH,
        status=GoalStatus.PROPOSED,
        budget_limit=50.0
    )

    # Disposable versioned Plan V1
    plan_v1 = Plan(
        plan_id="plan-101v1",
        goal_id=goal.goal_id,
        generation=1,
    )

    # Derived Plan V2 for fallback/replanning
    plan_v2 = Plan(
        plan_id="plan-101v2",
        goal_id=goal.goal_id,
        parent_plan_id=plan_v1.plan_id,
        generation=2,
        created_from_failure_event="evt-fail-999"
    )

    assert plan_v1.goal_id == goal.goal_id
    assert plan_v2.parent_plan_id == "plan-101v1"
    assert plan_v2.generation == 2
    assert plan_v2.created_from_failure_event == "evt-fail-999"


def test_htn_planner_deterministic_decomposition():
    """Verifies that HTN decomposition expands compound tasks into ordered primitive nodes."""
    planner = HTNPlanner()
    
    # "PrepareDemoSystem" should expand sequentially into 5 primitive steps:
    # VerifyHardware -> DownloadBinary -> ConfigureSettings -> RunDiagnostics -> GenerateReport
    plan = planner.generate_plan(
        goal_id="demo-goal",
        root_task_name="PrepareDemoSystem",
        initial_state=["internet_available"]
    )


    assert plan.goal_id == "demo-goal"
    assert plan.generation == 1
    
    # 5 primitive leaf nodes should be in the graph
    assert len(plan.graph.nodes) == 5
    
    # Verify topological order is correct
    topo_order = plan.graph.get_topological_sort()
    assert len(topo_order) == 5
    
    # Resolve names of topo order nodes
    task_names = [plan.graph.nodes[node_id].title for node_id in topo_order]
    assert set(task_names) == {"VerifyHardware", "DownloadBinary", "ConfigureSettings", "RunDiagnostics", "GenerateReport"}
    
    assert task_names.index("DownloadBinary") < task_names.index("ConfigureSettings")
    assert task_names.index("ConfigureSettings") < task_names.index("RunDiagnostics")
    assert task_names.index("VerifyHardware") < task_names.index("RunDiagnostics")
    assert task_names.index("RunDiagnostics") < task_names.index("GenerateReport")


    # Confirm CPM critical path total duration (19.5s due to parallel VerifyHardware)
    path, duration = plan.graph.calculate_critical_path()
    assert duration == 19.5



def test_htn_planner_recursion_limit():
    """Verifies that HTN planner enforces recursion depth limits."""
    library = TaskLibrary()
    # Create circular compound dependency
    library.register_task(TaskDefinition(
        name="TaskA",
        is_primitive=False,
        subtasks=["TaskB"]
    ))
    library.register_task(TaskDefinition(
        name="TaskB",
        is_primitive=False,
        subtasks=["TaskA"]
    ))

    planner = HTNPlanner(library)
    
    with pytest.raises(ValidationError) as excinfo:
        planner.generate_plan(goal_id="g1", root_task_name="TaskA", max_depth=4)
    
    assert "Maximum recursion depth" in str(excinfo.value)


def test_htn_planner_budget_limit():
    """Verifies that HTN planner rejects plans exceeding estimated duration or cost budgets."""
    planner = HTNPlanner()

    # PrepareDemoSystem needs 21.5s. Setting planner_budget to 15.0 should trigger validation error
    with pytest.raises(ValidationError) as excinfo:
        planner.generate_plan(
            goal_id="g1",
            root_task_name="PrepareDemoSystem",
            initial_state=["internet_available"],
            planner_budget=15.0
        )


    assert "Exceeded planner budget" in str(excinfo.value)
