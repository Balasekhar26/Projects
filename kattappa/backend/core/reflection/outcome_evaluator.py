"""Outcome Success and Cost Evaluator (Program 34.0).

Compares plan expectations (cost, durations, postconditions) against actual variables
to compute detailed success metrics and performance variance ratios.
"""
from __future__ import annotations

from typing import Any, Dict

from backend.core.planning.task import Plan


class OutcomeEvaluator:
    """Computes mathematical scores and variances of completed plan runs."""

    @classmethod
    def evaluate_outcome(
        cls,
        plan: Plan,
        final_variables: Dict[str, Any],
        actual_cost: float,
        actual_duration: float,
    ) -> Dict[str, Any]:
        """Analyzes state achievements and returns detailed scores and metrics."""
        # 1. Determine if goal variables are satisfied
        # Identify expected target values based on the cumulative effects of plan steps
        target_conditions: Dict[str, Any] = {}
        for step in plan.steps:
            target_conditions.update(step.effects)

        is_success = True
        for key, expected_val in target_conditions.items():
            if final_variables.get(key) != expected_val:
                is_success = False
                break

        # 2. Compute cost and time variance ratios
        cost_variance_ratio = 1.0
        if plan.expected_cost > 0:
            cost_variance_ratio = actual_cost / plan.expected_cost

        duration_variance_ratio = 1.0
        if plan.expected_duration > 0:
            duration_variance_ratio = actual_duration / plan.expected_duration

        # 3. Success score calculation
        if not is_success:
            score = 0.0
        else:
            # Base success score of 0.8 for completing the goal
            score = 0.8
            
            # Add small bonuses/penalties based on resource efficiency
            # If actual cost is lower than expected, gain a minor bonus, else subtract penalty
            cost_bonus = 0.1 * (1.0 - cost_variance_ratio)
            duration_bonus = 0.1 * (1.0 - duration_variance_ratio)
            
            score += cost_bonus + duration_bonus
            # Clip between 0.1 and 1.0
            score = max(0.1, min(1.0, score))

        return {
            "is_success": is_success,
            "score": round(score, 3),
            "cost_variance_ratio": round(cost_variance_ratio, 3),
            "duration_variance_ratio": round(duration_variance_ratio, 3),
            "expected_cost": plan.expected_cost,
            "actual_cost": actual_cost,
            "expected_duration": plan.expected_duration,
            "actual_duration": actual_duration,
        }
