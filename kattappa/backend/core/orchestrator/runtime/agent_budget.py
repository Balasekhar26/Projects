"""Agent Budget Enforcer (Program 16.0) — relocated to orchestrator/runtime/.

Lightweight ceiling guard checked by the TaskScheduler during agent execution.
Raises BudgetExceeded when any configured limit is breached, causing the
scheduler to treat the task as a failure and trigger standard retry/abort logic.
"""
from __future__ import annotations

from dataclasses import dataclass


class BudgetExceeded(Exception):
    """Raised when an agent task violates its assigned execution budget."""
    def __init__(self, dimension: str, used: float, limit: float) -> None:
        self.dimension = dimension
        self.used = used
        self.limit = limit
        super().__init__(
            f"Budget exceeded on {dimension}: used={used:.3f}, limit={limit:.3f}"
        )


@dataclass
class AgentBudget:
    """Immutable budget envelope assigned to a single agent task.

    All limits are optional (None = unlimited). Set a limit to 0.0 to disable
    the dimension entirely, which will always raise on first check.
    """
    token_limit: float | None = None
    dollar_limit: float | None = None
    time_limit_seconds: float | None = None

    def check_tokens(self, used_tokens: float) -> None:
        if self.token_limit is not None and used_tokens > self.token_limit:
            raise BudgetExceeded("tokens", used_tokens, self.token_limit)

    def check_dollars(self, spent_dollars: float) -> None:
        if self.dollar_limit is not None and spent_dollars > self.dollar_limit:
            raise BudgetExceeded("dollars", spent_dollars, self.dollar_limit)

    def check_time(self, elapsed_seconds: float) -> None:
        if self.time_limit_seconds is not None and elapsed_seconds > self.time_limit_seconds:
            raise BudgetExceeded("time_seconds", elapsed_seconds, self.time_limit_seconds)

    def check_all(self, used_tokens: float, spent_dollars: float, elapsed_seconds: float) -> None:
        """Checks all three dimensions in priority order (time first)."""
        self.check_time(elapsed_seconds)
        self.check_tokens(used_tokens)
        self.check_dollars(spent_dollars)
