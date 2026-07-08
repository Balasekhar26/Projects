"""Tool Selector Success Rate Estimator (Program 15.0).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set


class ToolSelector:
    """Selects and ranks alternative tools based on historical success metrics and active tabu exclusions."""

    def __init__(self, default_success_rates: Optional[Dict[str, float]] = None) -> None:
        self.success_rates = default_success_rates or {
            "BrowserTool": 0.65,
            "APITool": 0.96,
            "CLI_Tool": 0.88,
        }

    def update_success_rate(self, tool_name: str, success: bool) -> None:
        """Dynamically tracks success traces to adjust weights (standard alpha smoothing)."""
        alpha = 0.1
        current = self.success_rates.get(tool_name, 0.5)
        outcome = 1.0 if success else 0.0
        self.success_rates[tool_name] = round(current + alpha * (outcome - current), 3)

    def select_best_tool(self, candidates: List[str], tabu_list: Optional[Set[str]] = None) -> str:
        """Returns the candidate tool with highest success rate that is not marked as tabu."""
        tabus = tabu_list or set()
        
        valid_candidates = [c for c in candidates if c not in tabus]
        if not valid_candidates:
            # Fallback to candidates if everything is tabu (prevent blocking)
            valid_candidates = candidates

        # Sort descending by success rate
        sorted_tools = sorted(
            valid_candidates,
            key=lambda t: self.success_rates.get(t, 0.5),
            reverse=True,
        )
        return sorted_tools[0] if sorted_tools else ""
