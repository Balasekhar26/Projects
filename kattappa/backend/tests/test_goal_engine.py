import pytest
from datetime import datetime, timedelta
from backend.core.autonomy.goal_manager import Goal
from backend.core.goal.priority_engine import PriorityEngine
from backend.core.goal.constraint_solver import ConstraintSolver
from backend.core.goal.dependency_resolver import DependencyResolver
from backend.core.goal.goal_engine import GoalEngine

def test_priority_engine_scores() -> None:
    g1 = Goal("g1", "Objective 1", priority=2)
    g2 = Goal("g2", "Objective 2", priority=2, deadline=datetime.now() + timedelta(minutes=5))
    
    score1 = PriorityEngine.calculate_priority_score(g1)
    score2 = PriorityEngine.calculate_priority_score(g2)
    
    # g2 should have a much higher priority score due to the close deadline
    assert score2 > score1

def test_constraint_solver_limits() -> None:
    # Expired deadline should fail validation
    g_past = Goal("g_past", "Expired task", deadline=datetime.now() - timedelta(minutes=1))
    assert not ConstraintSolver.validate_constraints(g_past)
    
    # Over budget (₹6 lakh limit) should fail
    g_cost = Goal("g_cost", "Buy server budget 600000")
    assert not ConstraintSolver.validate_constraints(g_cost, available_budget=500000.0)
    
    # Safe cost passes
    g_safe = Goal("g_safe", "Buy RAM budget 40000")
    assert ConstraintSolver.validate_constraints(g_safe, available_budget=500000.0)

def test_dependency_resolver_ordering() -> None:
    # DAG: A depends on B, B depends on C
    deps = {
        "A": ["B"],
        "B": ["C"],
        "C": []
    }
    order = DependencyResolver.resolve_execution_order(deps)
    assert order == ["C", "B", "A"]
    
    # Cycle: A depends on B, B depends on A
    cycle_deps = {
        "A": ["B"],
        "B": ["A"]
    }
    with pytest.raises(ValueError, match="Cycle detected"):
        DependencyResolver.resolve_execution_order(cycle_deps)

def test_goal_engine_orchestration() -> None:
    engine = GoalEngine()
    
    g1 = Goal("g1", "Objective 1", priority=1)
    g2 = Goal("g2", "Objective 2", priority=5)
    
    goals = [g1, g2]
    # g2 depends on g1
    deps = {
        "g2": ["g1"],
        "g1": []
    }
    
    execution_list = engine.orchestrate_goals(goals, deps)
    # Execution order must respect dependency flow: g1 first, then g2
    assert execution_list == ["g1", "g2"]
