"""Tool Circuit Breaker (Program 11.8).

Prevents repeated executions to degraded external tool APIs with Half-Open recovery.
"""
from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF-OPEN"


class ToolCircuitBreaker:
    """Manages circuit states (Closed, Open, Half-Open) per tool."""

    _instance: Optional[ToolCircuitBreaker] = None

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 5.0, max_probes: int = 2) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown_seconds
        self.max_probes = max_probes
        
        # Maps tool_name -> state
        self.states: Dict[str, CircuitState] = {}
        # Maps tool_name -> failure_count
        self.failures: Dict[str, int] = {}
        # Maps tool_name -> consecutive_success_count (used in Half-Open state)
        self.successes: Dict[str, int] = {}
        # Maps tool_name -> open_timestamp (when tripped to OPEN)
        self.tripped_at: Dict[str, float] = {}

    @classmethod
    def get_instance(cls) -> ToolCircuitBreaker:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_state(self, tool_name: str) -> CircuitState:
        """Determines state based on timestamps and counts."""
        state = self.states.get(tool_name, CircuitState.CLOSED)
        
        if state == CircuitState.OPEN:
            opened_time = self.tripped_at.get(tool_name, 0.0)
            if time.time() - opened_time > self.cooldown:
                logger.info("Circuit breaker cooldown expired for %s. Transitioning to HALF-OPEN.", tool_name)
                self.states[tool_name] = CircuitState.HALF_OPEN
                self.successes[tool_name] = 0
                return CircuitState.HALF_OPEN
                
        return self.states.get(tool_name, CircuitState.CLOSED)

    def is_available(self, tool_name: str) -> bool:
        """Returns True if execution is permitted (Closed or Half-Open)."""
        state = self.get_state(tool_name)
        return state != CircuitState.OPEN

    def record_failure(self, tool_name: str) -> None:
        """Increments failure counts. If Half-Open, trips immediately to OPEN."""
        state = self.get_state(tool_name)
        
        if state == CircuitState.HALF_OPEN:
            logger.warning("Probe failed in HALF-OPEN state for tool %s. Retripping to OPEN.", tool_name)
            self.trip(tool_name)
            return

        self.failures[tool_name] = self.failures.get(tool_name, 0) + 1
        logger.warning(
            "Recorded failure for tool %s (%d/%d)",
            tool_name, self.failures[tool_name], self.failure_threshold
        )
        
        if self.failures[tool_name] >= self.failure_threshold:
            self.trip(tool_name)

    def record_success(self, tool_name: str) -> None:
        """Resets or transitions states based on outcome success."""
        state = self.get_state(tool_name)
        
        if state == CircuitState.HALF_OPEN:
            self.successes[tool_name] = self.successes.get(tool_name, 0) + 1
            logger.info("Probe succeeded in HALF-OPEN state for tool %s (%d/%d)", tool_name, self.successes[tool_name], self.max_probes)
            if self.successes[tool_name] >= self.max_probes:
                logger.info("Required probes succeeded. Closing circuit breaker for tool: %s", tool_name)
                self.reset(tool_name)
        else:
            self.reset(tool_name)

    def trip(self, tool_name: str) -> None:
        self.states[tool_name] = CircuitState.OPEN
        self.tripped_at[tool_name] = time.time()
        logger.error("Circuit breaker state for tool %s is now OPEN", tool_name)

    def reset(self, tool_name: str) -> None:
        self.states[tool_name] = CircuitState.CLOSED
        self.failures[tool_name] = 0
        self.successes[tool_name] = 0
        if tool_name in self.tripped_at:
            del self.tripped_at[tool_name]
