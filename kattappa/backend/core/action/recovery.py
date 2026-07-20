"""Bounded retry policy for transient executor failures."""

from __future__ import annotations

from dataclasses import dataclass

MAX_RETRIES = 3
TRANSIENT_ERROR_CODES = frozenset({"FILE_IO_ERROR", "SHELL_TIMEOUT", "SHELL_IO_ERROR"})


@dataclass(frozen=True, slots=True)
class RecoveryPolicy:
    """Decide retries while enforcing Kattappa's global retry ceiling."""

    max_retries: int = MAX_RETRIES

    def __post_init__(self) -> None:
        """Reject negative or unsafe retry budgets at configuration time."""

        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int):
            raise TypeError("max_retries must be an integer")
        if not 0 <= self.max_retries <= MAX_RETRIES:
            raise ValueError(f"max_retries must be between 0 and {MAX_RETRIES}")

    def should_retry(self, error_code: str, retry_count: int) -> bool:
        """Return true only for transient errors below the configured ceiling."""

        if retry_count < 0:
            raise ValueError("retry_count must not be negative")
        return error_code in TRANSIENT_ERROR_CODES and retry_count < self.max_retries
