"""Unit tests for Program 36.0: Decision Network Engine.

Verifies expected utility calculations, scenario weighting adjustments,
and optimal plan policy selection.
"""
from __future__ import annotations

import pytest

from backend.core.planning.task import Plan, Operator
from backend.core.planning.decision_network import DecisionNetworkEngine


@pytest.fixture
def plan_choices():
    # ── Plan A: Direct API path (cheap, fast, highly reliable) ────────────────
    op1_a = Operator(
        operator_id="op_api",
        name="api_fetch",
        estimated_cost=1.0,
        estimated_time=2.0,
    )
    plan_a = Plan(
        plan_id="plan_api",
        goal_id="goal_1",
        steps=[op1_a],
        expected_cost=1.0,
        expected_duration=2.0,
        expected_reward=10.0,
        expected_risk=0.05,
    )

    # ── Plan B: Browser Scraping path (expensive, slow, unreliable) ──────────
    op1_b = Operator(
        operator_id="op_browser",
        name="browser_scrape",
        estimated_cost=5.0,
        estimated_time=15.0,
    )
    plan_b = Plan(
        plan_id="plan_browser",
        goal_id="goal_1",
        steps=[op1_b],
        expected_cost=5.0,
        expected_duration=15.0,
        expected_reward=10.0,
        expected_risk=0.30,
    )

    return plan_a, plan_b


# ── Decision Network Tests ────────────────────────────────────────────────────

class TestDecisionNetwork:
    def test_compute_expected_utility_reliable_plan(self, plan_choices):
        plan_a, _ = plan_choices
        
        # Scenario weights prioritizing success and safety
        weights = {"w_success": 1.0, "w_cost": 0.1, "w_duration": 0.05, "w_risk": 0.2}
        
        # High success probability map (API is 99% reliable)
        probs = {"api_fetch": 0.99}
        
        eu = DecisionNetworkEngine.compute_expected_utility(plan_a, probs, weights)
        
        # P(success) = 0.99
        # U(success) = 1.0*10.0 - 0.1*1.0 - 0.05*2.0 - 0.2*0.05 = 10.0 - 0.1 - 0.1 - 0.01 = 9.79
        # U(failure) = - 0.1*1.0 - 0.05*2.0 - 0.2*0.05 - 5.0*0.2 = -0.1 - 0.1 - 0.01 - 1.0 = -1.21
        # EU = 0.99*9.79 + 0.01*(-1.21) = 9.6921 - 0.0121 = 9.68
        assert eu == 9.680

    def test_scenario_weights_shift_preference(self, plan_choices):
        plan_a, plan_b = plan_choices
        
        # Scenario 1: Standard Weights (prefers Plan A API)
        weights_std = {"w_success": 1.0, "w_cost": 0.2, "w_duration": 0.1, "w_risk": 0.5}
        probs = {"api_fetch": 0.99, "browser_scrape": 0.60}  # Browser is shaky
        
        best, score = DecisionNetworkEngine.select_optimal_policy([plan_a, plan_b], probs, weights_std)
        assert best.plan_id == "plan_api"
        
        # Scenario 2: Speed-Critical Weights (high reward, low cost sensitivity)
        # If API was somehow extremely expensive, e.g. cost = 50, browser cost = 5
        # Let's verify we pick B if B's success utility outweighs cost constraints
        plan_a_expensive = Plan(
            plan_id="plan_api_exp",
            goal_id="goal_1",
            steps=[plan_a.steps[0]],
            expected_cost=100.0,  # massive cost
            expected_duration=2.0,
            expected_reward=10.0,
            expected_risk=0.05,
        )
        
        weights_cheap = {"w_success": 1.0, "w_cost": 1.0, "w_duration": 0.05, "w_risk": 0.1}
        best_cheap, _ = DecisionNetworkEngine.select_optimal_policy([plan_a_expensive, plan_b], probs, weights_cheap)
        
        # Prefers B now because Cost factor is heavily penalized (w_cost=1.0)
        assert best_cheap.plan_id == "plan_browser"
