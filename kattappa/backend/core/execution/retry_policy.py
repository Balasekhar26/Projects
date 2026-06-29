"""Retry Policy Abstractions (Program 11.8).

Enables fixed, linear, and exponential jitter backoff strategies.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod


class RetryPolicy(ABC):
    """Abstract retry policy strategy interface."""

    @abstractmethod
    def get_delay(self, attempt: int) -> float:
        """Returns delay duration in seconds for current attempt count."""
        pass


class FixedRetryPolicy(RetryPolicy):
    def __init__(self, delay: float = 0.1) -> None:
        self.delay = delay

    def get_delay(self, attempt: int) -> float:
        return self.delay


class LinearRetryPolicy(RetryPolicy):
    def __init__(self, initial_delay: float = 0.05, multiplier: float = 0.05) -> None:
        self.initial_delay = initial_delay
        self.multiplier = multiplier

    def get_delay(self, attempt: int) -> float:
        return self.initial_delay + (attempt * self.multiplier)


class ExponentialBackoffPolicy(RetryPolicy):
    def __init__(self, base_delay: float = 0.01, max_delay: float = 1.0, jitter: bool = True) -> None:
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        delay = min(self.max_delay, self.base_delay * (2 ** attempt))
        if self.jitter:
            delay = random.uniform(0, delay)
        return delay
