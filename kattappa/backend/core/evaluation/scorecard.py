"""Balanced Scorecard Performance Schema (Program 13.0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Scorecard:
    """Holds accumulated execution performance metrics for a specific planner version."""
    planner_version: str
    total_plans: int = 0
    success_rate: float = 0.0
    avg_duration_error: float = 0.0  # Mean absolute percentage error
    avg_cost_error: float = 0.0      # Mean absolute percentage error
    recovery_rate: float = 0.0      # Ratio of plans requiring recovery
    user_approval_rate: float = 1.0  # Ratio of plans approved by operator
    combined_score: float = 0.0     # Score out of 100 representing overall quality

    def to_dict(self) -> Dict[str, Any]:
        return {
            "planner_version": self.planner_version,
            "total_plans": self.total_plans,
            "success_rate": self.success_rate,
            "avg_duration_error": self.avg_duration_error,
            "avg_cost_error": self.avg_cost_error,
            "recovery_rate": self.recovery_rate,
            "user_approval_rate": self.user_approval_rate,
            "combined_score": self.combined_score,
        }

    def compute_combined_score(self) -> float:
        """Balanced scorecard formula avoiding reward hacking by penalizing errors and recoveries."""
        if self.total_plans == 0:
            return 0.0

        # Weights mapping (total = 1.0)
        w_success = 0.4
        w_duration_accuracy = 0.2
        w_cost_accuracy = 0.15
        w_recovery_penalty = 0.15
        w_approval = 0.1

        # Accuracy scores (1.0 - error), clamped to [0.0, 1.0]
        duration_acc = max(0.0, 1.0 - self.avg_duration_error)
        cost_acc = max(0.0, 1.0 - self.avg_cost_error)
        
        # Recovery penalty (higher recovery rate lowers the score component)
        recovery_score = max(0.0, 1.0 - self.recovery_rate)

        weighted_sum = (
            self.success_rate * w_success +
            duration_acc * w_duration_accuracy +
            cost_acc * w_cost_accuracy +
            recovery_score * w_recovery_penalty +
            self.user_approval_rate * w_approval
        )

        self.combined_score = round(weighted_sum * 100, 2)
        return self.combined_score
