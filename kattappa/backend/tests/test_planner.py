"""Unit tests for Program 5G-2: Hierarchical Task Network (HTN) Planner.
"""
from __future__ import annotations

import pytest

from backend.core.planning.goal import Goal
from backend.core.planning.task import Task, Operator, Method, Plan, PlannerState
from backend.core.planning.planner import HTNPlanner, PlanValidator, HeuristicScorer


def test_heuristic_method_scorer():
    """Verifies that HeuristicScorer correctly sorts methods based on cost."""
    # Define Operators with cost
    op_fast = Operator("op_fast", "fast_action", estimated_cost=1.0)
    op_slow = Operator("op_slow", "slow_action", estimated_cost=10.0)

    operators = {"fast_action": op_fast, "slow_action": op_slow}

    # Method A uses fast action, Method B uses slow action
    m_a = Method("m_a", "task_name", ["fast_action"])
    m_b = Method("m_b", "task_name", ["slow_action"])

    ranked = HeuristicScorer.rank_methods([m_b, m_a], operators)
    assert ranked[0][1].method_id == "m_a", "Method with lower cost must be ranked first"
    assert ranked[0][0] == 1.0


def test_htn_recursive_decomposition_and_backtracking():
    """Verifies that HTNPlanner decomposes compound tasks and backtracks on precondition failures."""
    planner = HTNPlanner()

    # Goal: "Install Software"
    # Starting state: "has_downloaded": False
    goal = Goal("goal_01", "Install Software", constraints=["install_task"])

    # Register primitive actions (Operators)
    # 1. Download
    planner.register_operator(Operator(
        operator_id="op_dl",
        name="DownloadAction",
        preconditions={},
        effects={"has_downloaded": True},
        estimated_cost=2.0,
    ))
    # 2. Run Installer
    planner.register_operator(Operator(
        operator_id="op_inst",
        name="InstallAction",
        preconditions={"has_downloaded": True},
        effects={"has_installed": True},
        estimated_cost=3.0,
    ))

    # Register compound task decomposition method
    # Method decomposes "install_task" -> ["DownloadAction", "InstallAction"]
    planner.register_method(Method(
        method_id="m_install",
        task_name="install_task",
        subtasks=["DownloadAction", "InstallAction"],
    ))

    # Evaluate plan
    state = PlannerState(current_goal="goal_01", variables={"has_downloaded": False})
    plan = planner.find_plan(goal, state)

    assert plan is not None
    assert len(plan.steps) == 2
    assert plan.steps[0].name == "DownloadAction"
    assert plan.steps[1].name == "InstallAction"
    assert plan.expected_cost == 5.0


def test_htn_recursive_decomposition_cycles():
    """Verifies that recursive loops are detected and rejected."""
    planner = HTNPlanner()
    goal = Goal("g1", "LoopGoal", constraints=["loop_task"])

    # Method decomposes loop_task -> loop_task (infinite recursion cycle)
    planner.register_method(Method("m_loop", "loop_task", ["loop_task"]))

    state = PlannerState("g1", {})
    plan = planner.find_plan(goal, state)
    assert plan is None, "Infinite recursion loop must return None"


def test_plan_validation_fails_preconditions():
    """Verifies that PlanValidator correctly flags precondition checks failures."""
    # Op requires key=True, but initial state has key=False
    op = Operator("op", "Action", preconditions={"key": True})
    plan = Plan("p1", "g1", steps=[op])

    success, errors = PlanValidator.validate_plan(plan, {"key": False})
    assert success is False
    assert len(errors) == 1
    assert "failed precondition check" in errors[0]
