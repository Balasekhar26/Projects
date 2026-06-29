"""Unit and integration tests for Program 5G-5: Temporal & Resource Scheduler.
"""
from __future__ import annotations

import pytest

from backend.core.planning.task import Operator, Plan
from backend.core.planning.plan_graph import PlanNode, DependencyGraph, PlanCompiler
from backend.core.planning.scheduler import ScheduledTask, CriticalPathAnalyzer, Scheduler


def test_critical_path_method_analysis():
    """Verifies that CriticalPathAnalyzer correctly solves ES, EF, LS, LF, and slack."""
    # Graph structure:
    # A (time=3) -> B (time=4)
    # Both are on the critical path, slack should be 0.
    graph = DependencyGraph()

    opA = Operator("opA", "ActionA", estimated_time=3.0)
    opB = Operator("opB", "ActionB", estimated_time=4.0)

    n1 = PlanNode("ActionA_0", opA)
    n2 = PlanNode("ActionB_1", opB)

    graph.add_node(n1)
    graph.add_node(n2)
    graph.add_edge("ActionA_0", "ActionB_1")

    scheduled = CriticalPathAnalyzer.analyze(graph)
    assert len(scheduled) == 2

    taskA = scheduled["ActionA_0"]
    taskB = scheduled["ActionB_1"]

    assert taskA.earliest_start == 0.0
    assert taskA.earliest_finish == 3.0
    assert taskB.earliest_start == 3.0
    assert taskB.earliest_finish == 7.0

    # Backwards pass checks
    assert taskB.latest_finish == 7.0
    assert taskB.latest_start == 3.0
    assert taskA.latest_finish == 3.0
    assert taskA.latest_start == 0.0

    assert taskA.slack == 0.0
    assert taskB.slack == 0.0
    assert taskA.is_critical is True
    assert taskB.is_critical is True


def test_resource_constrained_scheduling():
    """Verifies that Scheduler shifts task start times forward to resolve resource capacity overlaps."""
    # Two independent tasks that can run in parallel (no dependency edges)
    # Both require the 'gpu' resource.
    # GPU capacity = 1.
    # Both have duration = 5.
    op1 = Operator("op1", "Task1", parameters={"required_resources": ["gpu"]}, estimated_time=5.0)
    op2 = Operator("op2", "Task2", parameters={"required_resources": ["gpu"]}, estimated_time=5.0)

    plan = Plan("p1", "g1", steps=[op1, op2])
    graph = PlanCompiler.compile_plan_to_graph(plan)

    # Schedule with gpu limit = 1
    scheduled = Scheduler.schedule_with_resources(graph, {"gpu": 1})

    task1 = scheduled["Task1_0"]
    task2 = scheduled["Task2_1"]

    # One must run first (at 0.0 to 5.0), and the other must be delayed to start at 5.0 (after first releases GPU)
    starts = {task1.earliest_start, task2.earliest_start}
    finishes = {task1.earliest_finish, task2.earliest_finish}

    assert starts == {0.0, 5.0}
    assert finishes == {5.0, 10.0}
