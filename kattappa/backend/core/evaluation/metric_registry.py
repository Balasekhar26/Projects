"""Metric Registry KPI Metadata and Safety Thresholds (Program 13.0).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MetricDefinition:
    name: str
    description: str
    target_baseline: float
    warning_threshold: float
    is_lower_better: bool = False


class MetricRegistry:
    """Tracks registered KPIs, validation boundaries, and warnings thresholds."""

    def __init__(self) -> None:
        self.metrics: Dict[str, MetricDefinition] = {}
        self._register_default_metrics()

    def register_metric(self, definition: MetricDefinition) -> None:
        self.metrics[definition.name] = definition

    def check_threshold(self, name: str, value: float) -> bool:
        """Returns True if the value violates the warning threshold boundaries."""
        if name not in self.metrics:
            return False
        
        metric = self.metrics[name]
        if metric.is_lower_better:
            return value > metric.warning_threshold
        else:
            return value < metric.warning_threshold

    def _register_default_metrics(self) -> None:
        self.register_metric(MetricDefinition(
            name="success_rate",
            description="Percentage of plans executing to completion successfully",
            target_baseline=0.90,
            warning_threshold=0.80,
        ))
        self.register_metric(MetricDefinition(
            name="avg_duration_error",
            description="Mean absolute percentage error of duration forecast vs actuals",
            target_baseline=0.15,
            warning_threshold=0.30,
            is_lower_better=True,
        ))
        self.register_metric(MetricDefinition(
            name="avg_cost_error",
            description="Mean absolute percentage error of budget/cost forecast vs actuals",
            target_baseline=0.10,
            warning_threshold=0.25,
            is_lower_better=True,
        ))
        self.register_metric(MetricDefinition(
            name="recovery_rate",
            description="Percentage of plan executions that triggered recovery policy engine",
            target_baseline=0.05,
            warning_threshold=0.20,
            is_lower_better=True,
        ))
        self.register_metric(MetricDefinition(
            name="user_approval_rate",
            description="Percentage of plans that passed operator security/intent reviews",
            target_baseline=0.95,
            warning_threshold=0.90,
        ))
