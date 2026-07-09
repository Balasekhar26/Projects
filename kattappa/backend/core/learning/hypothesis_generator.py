"""Hypothesis Generator (Program 29.0).

Analyzes recent failure profiles, execution telemetry, and budget issues
to propose optimization hypotheses and parameter tuning options.
"""
from __future__ import annotations

from typing import Any, Dict, List


class HypothesisGenerator:
    """Analyzes system failure statistics to formulate targeted improvement parameter sets."""

    @classmethod
    def propose_hypotheses(cls, analytics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Scans failure logs and tool accuracies to recommend adjustments.

        Returns:
            List of dicts: [{"hypothesis": str, "parameters": dict}]
        """
        proposals: List[Dict[str, Any]] = []

        failures = analytics.get("failures", {})
        tools = analytics.get("tools", {})

        # 1. Budget violations analysis
        if failures.get("BudgetExceededError", 0) > 0:
            proposals.append({
                "hypothesis": "Increasing total session limits and cost budget bounds will resolve execution blocks.",
                "parameters": {
                    "max_cost": 2.0,       # double budget
                    "max_calls": 150,      # increase calls
                    "max_duration": 450.0, # increase time
                },
            })

        # 2. Policy violation checks
        if failures.get("PolicyViolationError", 0) > 0:
            proposals.append({
                "hypothesis": "Decoupling directory path restrictions to workspace directories unblocks file tasks.",
                "parameters": {
                    "allow_network": True,
                },
            })

        # 3. High error rates in particular tools
        for tool_name, metrics in tools.items():
            error_rate = metrics.get("error_rate", 0.0)
            if error_rate > 0.3:  # high error rate
                proposals.append({
                    "hypothesis": f"Applying retry margins to high-error tool '{tool_name}' will improve success rate.",
                    "parameters": {
                        f"tool_{tool_name}_retries": 3,
                        "retry_delay_sec": 2.0,
                    },
                })

        # 4. Standard optimizer defaults (fallbacks if clean run but want optimization)
        success_rate = analytics.get("performance", {}).get("success_rate", 1.0)
        if success_rate < 0.8 and not proposals:
            proposals.append({
                "hypothesis": "Adjusting system learning rate and planner retry steps increases goal completion.",
                "parameters": {
                    "planner_max_steps": 15,
                    "lr": 1e-5,
                },
            })

        return proposals
