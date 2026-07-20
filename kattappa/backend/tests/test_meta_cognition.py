import pytest
from backend.core.meta.assumption_tracker import AssumptionTracker
from backend.core.meta.strategy_evaluator import StrategyEvaluator
from backend.core.meta.meta_reasoner import MetaReasoner

def test_assumption_tracking() -> None:
    tracker = AssumptionTracker()
    tracker.register_assumption("plan_1", "network_connected", "yes")
    tracker.register_assumption("plan_1", "disk_space_free_gb", "20")
    
    # State matches assumptions
    states_ok = {"network_connected": "yes", "disk_space_free_gb": "20"}
    assert tracker.verify_assumptions("plan_1", states_ok)
    
    # Assumption broken
    states_bad = {"network_connected": "no", "disk_space_free_gb": "20"}
    assert not tracker.verify_assumptions("plan_1", states_bad)

def test_strategy_evaluation() -> None:
    candidates = [
        {"name": "SimpleLookup", "success_rate": 0.85, "est_execution_time": 2.0},
        {"name": "DeepGraphRAG", "success_rate": 0.98, "est_execution_time": 8.0}
    ]
    
    best = StrategyEvaluator.select_best_strategy(candidates)
    
    # SimpleLookup score: 0.7 * 0.85 + 0.3 * (1/3) = 0.595 + 0.10 = 0.695
    # DeepGraphRAG score: 0.7 * 0.98 + 0.3 * (1/9) = 0.686 + 0.03 = 0.719
    # DeepGraphRAG should win due to high success rate
    assert best == "DeepGraphRAG"

def test_loop_detection() -> None:
    reasoner = MetaReasoner()
    
    reasoner.log_action("click save")
    reasoner.log_action("click save")
    assert not reasoner.detect_logical_loops()
    
    reasoner.log_action("click save") # 3rd identical action in a row
    assert reasoner.detect_logical_loops()
