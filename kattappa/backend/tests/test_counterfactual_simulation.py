"""Unit tests for Program 35.0: Counterfactual Simulation Engine.

Verifies alternative plan generation, simulation feasibility tracking,
and utility comparison recommendation checks.
"""
from __future__ import annotations

import pytest

from backend.core.planning.task import Plan, Operator
from backend.core.reflection.counterfactual_engine import CounterfactualSimulationEngine


@pytest.fixture
def baseline_plan():
    # Sum of costs: 5.0, sum of durations: 15.0
    op1 = Operator(
        operator_id="op_1",
        name="step_1",
        preconditions={"state": "A"},
        effects={"state": "B"},
        estimated_cost=2.0,
        estimated_time=5.0,
    )
    op2 = Operator(
        operator_id="op_2",
        name="step_2",
        preconditions={"state": "B"},
        effects={"state": "C"},
        estimated_cost=3.0,
        estimated_time=10.0,
    )
    
    return Plan(
        plan_id="plan_base_101",
        goal_id="goal_1",
        steps=[op1, op2],
        expected_cost=5.0,
        expected_duration=15.0,
        expected_reward=20.0,
        expected_risk=0.2,
        confidence=0.90,
    )


# ── Counterfactual Engine Tests ───────────────────────────────────────────────

class TestCounterfactualEngine:
    def test_generate_alternatives(self, baseline_plan):
        # We want to substitute "step_2" with a faster API tool
        faster_op = Operator(
            operator_id="op_2_fast",
            name="step_2_api",
            preconditions={"state": "B"},
            effects={"state": "C"},
            estimated_cost=1.0,  # cheaper
            estimated_time=2.0,  # faster
        )
        
        subs = {"step_2": [faster_op]}
        alts = CounterfactualSimulationEngine.generate_alternatives(baseline_plan, subs)
        
        assert len(alts) == 1
        alt_plan = alts[0]
        assert alt_plan.plan_id == "plan_base_101_alt_op_2_fast"
        assert alt_plan.expected_cost == 3.0  # op1 (2) + fast_op (1)
        assert alt_plan.expected_duration == 7.0  # op1 (5) + fast_op (2)

    def test_simulate_alternative_success(self, baseline_plan):
        # Successful simulation (preconditions met)
        initial_vars = {"state": "A"}
        res = CounterfactualSimulationEngine.simulate_alternative(baseline_plan, initial_vars)
        
        assert res["is_success"] is True
        assert res["simulated_cost"] == 5.0
        assert res["simulated_duration"] == 15.0
        assert res["final_variables"]["state"] == "C"

    def test_simulate_alternative_precondition_failed(self, baseline_plan):
        # Fails because preconditions of step_1 ("state": "A") not met
        initial_vars = {"state": "Z"}
        res = CounterfactualSimulationEngine.simulate_alternative(baseline_plan, initial_vars)
        
        assert res["is_success"] is False
        assert res["simulated_cost"] == 0.0

    def test_compare_utility_selects_cheaper_path(self, baseline_plan):
        # Original outcome
        orig_outcome = {
            "plan_id": "plan_base_101",
            "is_success": True,
            "actual_cost": 5.0,
            "actual_duration": 15.0,
        }
        
        # Better simulated outcome (cheaper & faster)
        sim_run = {
            "plan_id": "plan_base_101_alt_op_2_fast",
            "is_success": True,
            "simulated_cost": 3.0,
            "simulated_duration": 7.0,
            "final_variables": {"state": "C"},
        }
        
        comparison = CounterfactualSimulationEngine.compare_utility(
            original_outcome=orig_outcome,
            simulated_runs=[sim_run],
        )
        
        assert comparison["optimal_plan_id"] == "plan_base_101_alt_op_2_fast"
        # Original utility: 1.0 - 0.05*5.0 - 0.02*15.0 = 1.0 - 0.25 - 0.30 = 0.45
        # Alternative utility: 1.0 - 0.05*3.0 - 0.02*7.0 = 1.0 - 0.15 - 0.14 = 0.71
        assert comparison["original_utility"] == 0.45
        assert comparison["optimal_utility"] == 0.71
        assert comparison["utility_delta"] == 0.26
        assert "Substitute step operators" in comparison["recommendation"]
