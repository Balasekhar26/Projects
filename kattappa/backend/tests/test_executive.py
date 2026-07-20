import pytest
from backend.core.autonomy.goal_manager import Goal
from backend.core.executive.utility_calculator import UtilityCalculator
from backend.core.executive.arbitration_engine import ArbitrationEngine
from backend.core.executive.executive_controller import ExecutiveController

def test_utility_calculator_scoring() -> None:
    g1 = Goal("g1", "Task 1", priority=5)
    
    # High success rate, fast execution
    score_high = UtilityCalculator.calculate_utility(g1, success_probability=0.95, est_time_sec=10.0)
    # Low success rate, slow execution
    score_low = UtilityCalculator.calculate_utility(g1, success_probability=0.50, est_time_sec=300.0)
    
    assert score_high > score_low

def test_arbitration_interruption_signals() -> None:
    arbiter = ArbitrationEngine()
    
    # Incoming priority is higher -> interrupt
    assert arbiter.should_interrupt(current_active_priority=3, incoming_priority=5)
    
    # Incoming priority is lower -> do not interrupt
    assert not arbiter.should_interrupt(current_active_priority=5, incoming_priority=3)

def test_executive_controller_conflict_resolution() -> None:
    controller = ExecutiveController()
    
    g1 = Goal("g1", "Task 1", priority=2)
    g2 = Goal("g2", "Task 2", priority=5)
    
    goals = [g1, g2]
    predictions = {
        "g1": {"success_prob": 0.95, "time_sec": 10.0}, # high utility
        "g2": {"success_prob": 0.40, "time_sec": 600.0} # low utility due to poor success and slow speed
    }
    
    sorted_goals = controller.process_and_arbitrate_goals(goals, predictions)
    # g1 must be first due to higher calculated utility
    assert sorted_goals[0].goal_id == "g1"
    assert sorted_goals[1].goal_id == "g2"
