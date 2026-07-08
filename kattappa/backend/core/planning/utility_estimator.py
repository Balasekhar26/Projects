"""Utility Estimator Formula Model (Program 12.3).
"""
from __future__ import annotations

from typing import Any, Dict


class UtilityEstimator:
    """Computes expected plan utility based on reward, cost vector weights, and risk penalties."""

    def __init__(self, cost_weight: float = 1.0, risk_weight: float = 20.0) -> None:
        self.cost_weight = cost_weight
        self.risk_weight = risk_weight

    def calculate_utility(
        self,
        success_probability: float,
        reward: float,
        expected_cost: float,
        risk_score: float,
    ) -> float:
        """Utility = (success_probability * reward) - (expected_cost * cost_weight) - (risk_score * risk_weight)"""
        expected_reward = success_probability * reward
        cost_penalty = expected_cost * self.cost_weight
        risk_penalty = risk_score * self.risk_weight

        utility = expected_reward - cost_penalty - risk_penalty
        return round(utility, 3)
