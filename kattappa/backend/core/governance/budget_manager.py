"""Budget Manager & Cost Tracker (Program 28.0).

Monitors and limits financial (token cost) and computational (call count,
run duration) resource consumption during task execution.
"""
from __future__ import annotations


class BudgetExceededError(RuntimeError):
    """Raised when resource usage violates active budget restrictions."""


class BudgetManager:
    """Tracks token consumption costs and overall session step count limits."""

    def __init__(
        self,
        max_cost: float = 1.0,         # Max cost in USD (e.g. $1.00 limit)
        max_calls: int = 100,          # Max execution tool calls / steps
        max_duration: float = 300.0,   # Max execution time in seconds
        prompt_token_rate: float = 0.0015 / 1000.0,      # USD per prompt token
        completion_token_rate: float = 0.0020 / 1000.0,  # USD per completion token
    ) -> None:
        self.max_cost = max_cost
        self.max_calls = max_calls
        self.max_duration = max_duration
        self.prompt_token_rate = prompt_token_rate
        self.completion_token_rate = completion_token_rate

        # Accumulated metrics
        self.total_cost = 0.0
        self.total_calls = 0
        self.total_duration = 0.0

    def add_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration: float = 0.0,
        is_call: bool = False,
    ) -> None:
        """Accumulates resource usage and raises BudgetExceededError if bounds are breached."""
        cost = (input_tokens * self.prompt_token_rate) + (output_tokens * self.completion_token_rate)
        self.total_cost += cost
        self.total_duration += duration
        if is_call:
            self.total_calls += 1

        # Evaluate restrictions
        if self.total_cost > self.max_cost:
            raise BudgetExceededError(
                f"Token cost budget exceeded: ${self.total_cost:.5f} / ${self.max_cost:.5f}"
            )

        if self.total_calls > self.max_calls:
            raise BudgetExceededError(
                f"Tool execution call limit exceeded: {self.total_calls} / {self.max_calls}"
            )

        if self.total_duration > self.max_duration:
            raise BudgetExceededError(
                f"Execution duration limit exceeded: {self.total_duration:.2f}s / {self.max_duration:.2f}s"
            )

    def get_status(self) -> dict[str, float | int]:
        """Returns usage percentages for monitoring metrics."""
        return {
            "cost_usd": self.total_cost,
            "cost_pct": round(self.total_cost / self.max_cost, 4) if self.max_cost > 0 else 0.0,
            "calls_count": self.total_calls,
            "calls_pct": round(self.total_calls / self.max_calls, 4) if self.max_calls > 0 else 0.0,
            "duration_sec": self.total_duration,
            "duration_pct": round(self.total_duration / self.max_duration, 4) if self.max_duration > 0 else 0.0,
        }
