"""Cancellation Token Manager (Program 11.5).

Propagates abort switches down to long-running task executors.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class CancellationToken:
    """Carries boolean flags supporting explicit execution interrupts."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        logger.warning("Cancellation token triggered.")

    def is_cancelled(self) -> bool:
        return self._cancelled

    def check(self) -> None:
        """Helper raising RuntimeError if token was aborted."""
        if self._cancelled:
            raise RuntimeError("Task execution aborted by cancellation token.")
