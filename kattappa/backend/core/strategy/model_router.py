"""Model Router Cost-Latency Optimizer (Program 15.0).
"""
from __future__ import annotations

from typing import Any, Dict


class ModelRouter:
    """Routes execution tasks to optimal LLMs based on cost limits, latency, and task capability profiles."""

    @staticmethod
    def route_model(
        task_category: str,
        dollar_budget: float,
        latency_budget_seconds: float
    ) -> str:
        """Determines target model identifier: 'local_small', 'code_specialist', or 'cloud_reasoning'."""
        # 1. Low dollar budgets force small local execution models
        if dollar_budget > 0.0 and dollar_budget < 0.05:
            return "local_small"

        # 2. Strict latency constraints force local deployment routing
        if latency_budget_seconds > 0.0 and latency_budget_seconds < 2.0:
            return "local_small"

        # 3. Specialized coding tasks route to code specialists
        if task_category in {"coding", "debugging", "synthesis"}:
            return "code_specialist"

        # 4. Complex planning, logic, and reasoning defaults to cloud reasoning engines
        return "cloud_reasoning"
