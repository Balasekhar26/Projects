"""Plan Evaluator Forecasting Drift Scorer (Program 13.0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class PlanEvaluation:
    plan_id: str
    duration_error: float
    cost_error: float
    success: bool
    recovery_triggered: bool
    user_approved: bool
    risk_underestimated: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


class PlanEvaluator:
    """Evaluates forecast accuracy drift between plan simulations and actual execution logs."""

    @staticmethod
    def evaluate(
        plan_id: str,
        predicted: Dict[str, Any],
        actual: Dict[str, Any]
    ) -> PlanEvaluation:
        """Compares predicted metrics against actuals to calculate error vectors."""
        # Retrieve values with standard defaults
        pred_duration = float(predicted.get("expected_duration", 1.0))
        actual_duration = float(actual.get("duration", 0.0))

        pred_cost = float(predicted.get("expected_cost", 0.0))
        actual_cost = float(actual.get("cost", 0.0))

        # Absolute Percentage Error calculation
        duration_err = abs(actual_duration - pred_duration) / max(0.1, pred_duration)
        if pred_cost > 0.0:
            cost_err = abs(actual_cost - pred_cost) / pred_cost
        else:
            cost_err = 0.0 if actual_cost == 0.0 else 1.0

        # Assess risk underestimations
        pred_risk = float(predicted.get("risk_score", 0.0))
        actual_risk_occurred = bool(actual.get("risk_event_occurred", False))
        risk_underestimated = actual_risk_occurred and (pred_risk < 0.3)

        return PlanEvaluation(
            plan_id=plan_id,
            duration_error=round(duration_err, 3),
            cost_error=round(cost_err, 3),
            success=bool(actual.get("success", True)),
            recovery_triggered=bool(actual.get("recovery_triggered", False)),
            user_approved=bool(actual.get("user_approved", True)),
            risk_underestimated=risk_underestimated,
            metadata={
                "pred_duration": pred_duration,
                "actual_duration": actual_duration,
                "pred_cost": pred_cost,
                "actual_cost": actual_cost,
            }
        )
