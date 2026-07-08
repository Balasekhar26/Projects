"""Planner Router Domain System (Program 15.0).
"""
from __future__ import annotations

from typing import Any, Dict


class PlannerRouter:
    """Selects the optimal planner variant based on latency targets, risk level, and task complexity."""

    @staticmethod
    def route_planner(
        task_complexity: int,
        latency_budget_seconds: float,
        requires_risk_aware: bool = False
    ) -> str:
        """Determines planner variant name: 'HTN_Planner', 'Fast_Planner', or 'RiskAware_Planner'."""
        # 1. High risk constraints prioritize the risk-aware planning compiler
        if requires_risk_aware:
            return "RiskAware_Planner"

        # 2. Stringent real-time limits (< 5 seconds) route to the Fast Reactive planner
        if latency_budget_seconds > 0.0 and latency_budget_seconds <= 5.0:
            return "Fast_Planner"

        # 3. Large, complex task trees fallback to the HTN planner
        if task_complexity >= 5:
            return "HTN_Planner"

        # Default fallback
        return "HTN_Planner"
