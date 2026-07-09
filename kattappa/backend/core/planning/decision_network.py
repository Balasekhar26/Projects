"""Decision Network Engine (Program 36.0).

Calculates expected utilities of alternative plans under uncertainty parameters
and evaluates context-aware scenario weights to select optimal execution policies.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from backend.core.planning.task import Plan

logger = logging.getLogger(__name__)


class DecisionNetworkEngine:
    """Computes expected utilities and selects optimal plan policies under uncertainty."""

    @classmethod
    def compute_expected_utility(
        cls,
        plan: Plan,
        success_probability_map: Dict[str, float],
        scenario_weights: Dict[str, float],
    ) -> float:
        """Calculates Expected Utility (EU) based on success probabilities and scenario weights.

        EU = P(success) * U(success) + (1 - P(success)) * U(failure)
        """
        # 1. Compute success probability as the product of step success probabilities
        p_success = 1.0
        for step in plan.steps:
            prob = success_probability_map.get(step.name, 0.95)  # Default fallback probability
            p_success *= prob

        # 2. Get scenario weights
        w_success = scenario_weights.get("w_success", 1.0)
        w_cost = scenario_weights.get("w_cost", 0.1)
        w_duration = scenario_weights.get("w_duration", 0.05)
        w_risk = scenario_weights.get("w_risk", 0.2)

        # 3. Compute Success Utility
        u_success = (
            (w_success * plan.expected_reward)
            - (w_cost * plan.expected_cost)
            - (w_duration * plan.expected_duration)
            - (w_risk * plan.expected_risk)
        )

        # 4. Compute Failure Utility (penalizes resources consumed + extra risk penalty)
        u_failure = (
            - (w_cost * plan.expected_cost)
            - (w_duration * plan.expected_duration)
            - (w_risk * plan.expected_risk)
            - (5.0 * w_risk)  # penalty for execution failure
        )

        # 5. Compute Expected Utility
        expected_utility = (p_success * u_success) + ((1.0 - p_success) * u_failure)
        return round(expected_utility, 3)

    @classmethod
    def select_optimal_policy(
        cls,
        plans: List[Plan],
        success_probability_map: Dict[str, float],
        scenario_weights: Dict[str, float],
    ) -> Tuple[Plan, float]:
        """Evaluates expected utilities and returns the optimal Plan and its score."""
        if not plans:
            raise ValueError("Plans list cannot be empty.")

        best_plan = plans[0]
        best_utility = cls.compute_expected_utility(best_plan, success_probability_map, scenario_weights)

        for plan in plans[1:]:
            utility = cls.compute_expected_utility(plan, success_probability_map, scenario_weights)
            if utility > best_utility:
                best_utility = utility
                best_plan = plan

        return best_plan, best_utility
