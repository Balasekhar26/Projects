"""Execution Retry Manager Policies (Program 5G-6).

Calculates wait delays based on exponential or linear backoff policies.
"""
from __future__ import annotations

import time
import logging

logger = logging.getLogger(__name__)


class RetryManager:
    """Manages retry limits and calculates wait intervals for failing task nodes."""

    @staticmethod
    def should_retry(
        node_id: str,
        current_attempt: int,
        max_retries: int = 3,
    ) -> bool:
        """Checks if the attempt count is within max limits."""
        return current_attempt < max_retries

    @staticmethod
    def get_backoff_delay(
        attempt: int,
        policy: str = "exponential",
        base_delay: float = 1.0,
    ) -> float:
        """Computes delay before retrying the step again.

        Supports 'linear' and 'exponential' delay shapes.
        """
        if policy == "linear":
            return base_delay * attempt
        # Default: exponential backoff (e.g. 1s, 2s, 4s...)
        return base_delay * (2 ** (attempt - 1))
