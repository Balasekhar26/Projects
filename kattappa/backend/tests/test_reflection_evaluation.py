"""Unit tests for Program 34.0: Evaluation and Reflection Engine.

Verifies plan outcome scoring, markdown logs synthesis, and self-critique adaptation loops.
"""
from __future__ import annotations

import pytest

from backend.core.planning.task import Plan, Operator
from backend.core.reflection import OutcomeEvaluator, ReflectionGenerator, SelfCritiqueLoop


@pytest.fixture
def sample_plan():
    # Plan with 2 steps: Step 1 (A->B), Step 2 (B->C)
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
        plan_id="plan_test_456",
        goal_id="goal_xyz",
        steps=[op1, op2],
        expected_cost=5.0,     # Sum of steps cost
        expected_duration=15.0, # Sum of steps duration
        expected_reward=20.0,
        expected_risk=0.2,
        confidence=0.90,
    )


# ── Outcome Evaluator Tests ───────────────────────────────────────────────────

class TestOutcomeEvaluator:
    def test_evaluate_outcome_success_cost_bonus(self, sample_plan):
        # Actual variables match step 2 final postcondition (state == "C")
        # Actual cost is 4.0 (expected is 5.0 -> efficiency gain)
        # Actual duration is 15.0 (expected is 15.0 -> matching)
        final_vars = {"state": "C"}
        
        res = OutcomeEvaluator.evaluate_outcome(
            plan=sample_plan,
            final_variables=final_vars,
            actual_cost=4.0,
            actual_duration=15.0,
        )
        
        assert res["is_success"] is True
        # Base (0.8) + cost bonus (0.1 * (1 - 4/5) = 0.02) + duration bonus (0.0) = 0.82
        assert res["score"] == 0.82
        assert res["cost_variance_ratio"] == 0.80
        assert res["duration_variance_ratio"] == 1.0

    def test_evaluate_outcome_failure(self, sample_plan):
        # State did not reach postcondition (state != "C")
        final_vars = {"state": "B"}
        
        res = OutcomeEvaluator.evaluate_outcome(
            plan=sample_plan,
            final_variables=final_vars,
            actual_cost=6.0,
            actual_duration=20.0,
        )
        
        assert res["is_success"] is False
        assert res["score"] == 0.0


# ── Reflection Generator Tests ────────────────────────────────────────────────

class TestReflectionGenerator:
    def test_generate_success_reflection(self, sample_plan):
        eval_res = {
            "is_success": True,
            "score": 0.85,
            "expected_cost": 5.0,
            "actual_cost": 4.5,
            "cost_variance_ratio": 0.90,
            "expected_duration": 15.0,
            "actual_duration": 14.0,
            "duration_variance_ratio": 0.93,
        }
        
        text = ReflectionGenerator.generate_reflection(sample_plan, eval_res)
        
        assert "SUCCESS" in text
        assert "Variance: 90.00%" in text
        assert "budget-positive" in text

    def test_generate_failure_reflection(self, sample_plan):
        eval_res = {
            "is_success": False,
            "score": 0.0,
            "expected_cost": 5.0,
            "actual_cost": 3.0,
            "cost_variance_ratio": 0.60,
            "expected_duration": 15.0,
            "actual_duration": 10.0,
            "duration_variance_ratio": 0.67,
        }
        
        text = ReflectionGenerator.generate_reflection(
            plan=sample_plan,
            evaluation=eval_res,
            failed_step_index=1,
            failed_operator="step_2",
            failure_detail="Simulated network error",
        )
        
        assert "FAILURE" in text
        assert "crashed at step index `1`" in text
        assert "executing operator `step_2`" in text
        assert "Simulated network error" in text


# ── Self-Critique Loop Tests ──────────────────────────────────────────────────

class TestSelfCritique:
    def test_critique_timeout_adaptation(self):
        reflection = "FAILURE: Task exceeded deadline bounds during execution."
        current_cfg = {"timeout_seconds": 30, "max_retries": 3}
        
        new_cfg = SelfCritiqueLoop.critique_and_adapt(reflection, current_cfg)
        
        # Timeout scaled up: 30 * 1.5 = 45
        assert new_cfg["timeout_seconds"] == 45
        assert "adaptation_reason" in new_cfg
        assert "deadline" in new_cfg["adaptation_reason"]

    def test_critique_crash_blacklist_adaptation(self):
        reflection = "FAILURE: crashed while running operator `step_2`. System Error raised."
        current_cfg = {"timeout_seconds": 30, "max_retries": 3, "blacklisted_tools": []}
        
        new_cfg = SelfCritiqueLoop.critique_and_adapt(reflection, current_cfg)
        
        # Retries scaled: 3 + 2 = 5
        assert new_cfg["max_retries"] == 5
        # step_2 added to blacklist
        assert "step_2" in new_cfg["blacklisted_tools"]
