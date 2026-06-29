"""Tool Circuit Breaker (Program 11.5).

Prevents repeated executions to degraded external tool APIs.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ToolCircuitBreaker:
    """Manages circuit states (Closed, Open, Half-Open) per tool."""

    _instance: Optional[ToolCircuitBreaker] = None

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 5.0) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown_seconds
        
        # Maps tool_name -> failure_count
        self.failures: Dict[str, int] = {}
        # Maps tool_name -> open_timestamp (when tripped)
        self.tripped_at: Dict[str, float] = {}

    @classmethod
    def get_instance(cls) -> ToolCircuitBreaker:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_available(self, tool_name: str) -> bool:
        """Returns True if the circuit is Closed. If Open but cooldown expired, transitions to Closed."""
        if tool_name not in self.tripped_at:
            return True

        opened_time = self.tripped_at[tool_name]
        if time.time() - opened_time > self.cooldown:
            # Cooldown passed, reset circuit
            logger.info("Circuit breaker cooldown expired for %s. Resetting to Closed.", tool_name)
            self.reset(tool_name)
            return True

        return False

    def record_failure(self, tool_name: str) -> None:
        """Increments failure count. Trips circuit to Open if threshold is reached."""
        self.failures[tool_name] = self.failures.get(tool_name, 0) + 1
        logger.warning(
            "Recorded failure for tool %s (%d/%d)",
            tool_name, self.failures[tool_name], self.failure_threshold
        )
        
        if self.failures[tool_name] >= self.failure_threshold:
            self.tripped_at[tool_name] = time.time()
            logger.error("Circuit breaker tripped to OPEN for tool: %s", tool_name)

    def record_success(self, tool_name: str) -> None:
        """Resets failure count on success."""
        self.reset(tool_name)

    def reset(self, tool_name: str) -> None:
        self.failures[tool_name] = 0
        if tool_name in self.tripped_at:
            del self.tripped_at[tool_name]
