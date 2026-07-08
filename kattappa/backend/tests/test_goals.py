"""Unit tests for Program 5G-1: Goal Representation Framework.
"""
from __future__ import annotations

import pytest

from backend.core.planning.goal import Goal, GoalRegistry


def test_goal_instantiation():
    """Verifies fields mapping on Goal instance."""
    goal = Goal(
        goal_id="g1",
        name="Task 1",
        priority="High",
        deadline=1700000000.0,
        reward=200.0,
        failure_cost=-100.0,
    )
    assert goal.goal_id == "g1"
    assert goal.priority == "High"
    assert goal.deadline == 1700000000.0
    assert goal.reward == 200.0
    assert goal.failure_cost == -100.0


def test_goal_registry_cycle_prevention():
    """Verifies that dependency loop cycles raise ValueError during registration."""
    registry = GoalRegistry()

    g_a = Goal("A", "Backup system")
    g_b = Goal("B", "Deploy updates", dependencies=["A"])

    registry.register_goal(g_a)
    registry.register_goal(g_b)

    # Attempt to introduce a cycle: A depends on B
    g_cycle = Goal("A", "Backup system", dependencies=["B"])
    with pytest.raises(ValueError):
        registry.register_goal(g_cycle)


def test_goal_topological_sorting():
    """Verifies that topological sorting returns goal IDs sorted parents-before-children."""
    registry = GoalRegistry()

    # D depends on C, C depends on B, B depends on A
    g_a = Goal("A", "Initialize sandbox")
    g_b = Goal("B", "Compile binaries", dependencies=["A"])
    g_c = Goal("C", "Run tests", dependencies=["B"])
    g_d = Goal("D", "Report status", dependencies=["C"])

    registry.register_goal(g_a)
    registry.register_goal(g_b)
    registry.register_goal(g_c)
    registry.register_goal(g_d)

    order = registry.get_topological_order()
    assert order == ["A", "B", "C", "D"]


def test_goal_trace_visualizer():
    """Verifies trace compiler contains goal details."""
    registry = GoalRegistry()
    registry.register_goal(Goal("g1", "First Task"))

    trace = registry.generate_dependency_trace()
    assert "Goal Dependency Diagram Trace" in trace
    assert "First Task" in trace
