"""Regression Detector Validation System (Program 13.0).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional
from backend.core.evaluation.scorecard import Scorecard
from backend.core.evaluation.metric_registry import MetricRegistry

logger = logging.getLogger(__name__)


class RegressionDetector:
    """Detects planning performance degradation against baselines and warning boundaries."""

    def __init__(self, registry: Optional[MetricRegistry] = None) -> None:
        self.registry = registry or MetricRegistry()

    def detect_regression(self, current: Scorecard, baseline: Scorecard) -> Dict[str, Any]:
        """Compares current scorecard metrics against baseline scorecard values."""
        degradations: List[str] = []

        # 1. Success rate degradation check (drops by more than 5%)
        if current.success_rate < (baseline.success_rate - 0.05):
            degradations.append(
                f"Success rate degraded from {baseline.success_rate * 100}% to {current.success_rate * 100}%."
            )

        # 2. Combined score check (drops by more than 5.0 points)
        if current.combined_score < (baseline.combined_score - 5.0):
            degradations.append(
                f"Combined score dropped from {baseline.combined_score} to {current.combined_score}."
            )

        # 3. Absolute threshold violations checks
        for metric_name, value in [
            ("success_rate", current.success_rate),
            ("avg_duration_error", current.avg_duration_error),
            ("avg_cost_error", current.avg_cost_error),
            ("recovery_rate", current.recovery_rate),
            ("user_approval_rate", current.user_approval_rate),
        ]:
            if self.registry.check_threshold(metric_name, value):
                degradations.append(
                    f"Metric '{metric_name}' value {value} violated warning threshold limits."
                )

        has_regression = len(degradations) > 0
        if has_regression:
            logger.warning(
                "Regression detected for planner version '%s'! Warnings: %s",
                current.planner_version,
                degradations,
            )

        return {
            "has_regression": has_regression,
            "degradations": degradations,
            "current_score": current.combined_score,
            "baseline_score": baseline.combined_score,
        }

