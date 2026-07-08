"""Inference Cost and Token Tracker (Program 10).

Logs and audits accumulated financial usage fees across cognitive runs.
"""
from __future__ import annotations

from typing import Any, Dict, Optional



class CostManager:
    """Audits input/output token usage metrics and overall financial cost totals."""

    _instance: Optional[CostManager] = None

    def __init__(self) -> None:
        self.total_cost: float = 0.0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.call_count: int = 0

    @classmethod
    def get_instance(cls) -> CostManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def record_usage(self, cost: float, input_tokens: int, output_tokens: int) -> None:
        self.total_cost += cost
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.call_count += 1

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_cost_usd": self.total_cost,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_calls": self.call_count,
        }

    def reset(self) -> None:
        self.total_cost = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0
