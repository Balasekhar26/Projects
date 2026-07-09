"""Unit tests for Program 43.0: Meta-Cognition Engine.

Verifies self-awareness states, confidence manager calibration, escalation gates,
introspection loops, and dynamic planner selectors.
"""
from __future__ import annotations

import pytest

from backend.core.planning import (
    SelfAwarenessState,
    ConfidenceManager,
    ComputeAllocator,
    IntrospectionEngine,
    MetaReasoner,
)


class TestMetaCognition:
    def test_confidence_calibration(self):
        state = SelfAwarenessState(
            confidence=1.0,
            uncertainty=0.2,
            fatigue_metric=1.0,
            failure_count=1,
        )
        
        # 1.0 - 0.2 (uncertainty) - (0.05 * 4.0 complexity) - 0.1 (failures) - 0.05 (fatigue)
        # = 0.8 - 0.2 - 0.1 - 0.05 = 0.45
        calibrated = ConfidenceManager.calibrate_confidence(state, complexity=4.0)
        assert calibrated == 0.45

    def test_escalation_action_gates(self):
        assert ConfidenceManager.get_escalation_action(0.30) == "ASK_HUMAN"
        assert ConfidenceManager.get_escalation_action(0.55) == "EXECUTE_CONSERVATIVE"
        assert ConfidenceManager.get_escalation_action(0.85) == "AUTONOMOUS"

    def test_compute_allocator_scaling(self):
        critical_compute = ComputeAllocator.allocate_compute("CRITICAL", complexity=5.0)
        assert critical_compute["token_budget"] == 45000  # 30000 * 1.5
        assert critical_compute["simulation_iterations"] == 75  # 50 * 1.5
        assert critical_compute["planning_timeout"] == 45.0  # 30 * 1.5

        normal_compute = ComputeAllocator.allocate_compute("LOW", complexity=0.0)
        assert normal_compute["token_budget"] == 4000
        assert normal_compute["simulation_iterations"] == 5
        assert normal_compute["planning_timeout"] == 5.0

    def test_introspection_loops(self):
        state_clear = SelfAwarenessState(uncertainty=0.1, failure_count=0)
        assert IntrospectionEngine.introspect(state_clear, current_plan_success_prob=0.95) == "PROCEED"

        # Low success probability should prompt thinking longer
        assert IntrospectionEngine.introspect(state_clear, current_plan_success_prob=0.50) == "THINK_LONGER"

        # High failure rates should prompt requesting help
        state_stuck = SelfAwarenessState(uncertainty=0.1, failure_count=3)
        assert IntrospectionEngine.introspect(state_stuck, current_plan_success_prob=0.95) == "NEED_HELP"

    def test_meta_reasoner_planner_routing(self):
        # Low complexity task -> simple rule planner
        assert MetaReasoner.select_planner_strategy(complexity=2.0, uncertainty=0.1) == "RULE_PLANNER"
        
        # High complexity, low uncertainty -> HTN planner
        assert MetaReasoner.select_planner_strategy(complexity=5.0, uncertainty=0.2) == "HTN_PLANNER"
        
        # High complexity, high uncertainty -> hybrid decision network search
        assert MetaReasoner.select_planner_strategy(complexity=5.0, uncertainty=0.7) == "HYBRID_DECISION_NETWORK"
