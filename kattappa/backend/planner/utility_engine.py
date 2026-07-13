from typing import Any, Dict, List, Optional

class UtilityEngine:
    """Computes expected utility tradeoffs for goal stack items and alternative decomposition paths."""

    @staticmethod
    def calculate_utility(
        reward: float,
        success_probability: float,
        estimated_cost: float,
        estimated_time: float,
        failure_penalty: float = 0.0,
        risk_coefficient: float = 1.0
    ) -> float:
        """Utility Equation: ((reward * success_probability) - (risk_coefficient * failure_penalty)) / (cost * time)"""
        # Ensure cost and time are non-zero to avoid division by zero
        cost_term = max(0.01, estimated_cost)
        time_term = max(0.01, estimated_time)
        
        expected_success = reward * success_probability
        expected_failure = risk_coefficient * failure_penalty
        
        # Penalties are represented as negative bounds
        net_expected_value = expected_success - abs(expected_failure)
        
        # Return scaled utility
        return net_expected_value / (cost_term * time_term)

    @staticmethod
    def should_prune_branch(
        current_utility: float,
        minimum_utility_threshold: float
    ) -> bool:
        """Checks if a planner sub-goal branch utility score falls below strict thresholds."""
        return current_utility < minimum_utility_threshold
