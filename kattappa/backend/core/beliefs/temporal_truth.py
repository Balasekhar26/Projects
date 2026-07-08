"""Belief Management Component 7: Temporal Truth.

Enforces validity boundaries (valid_from / valid_until) on beliefs.
Some facts (e.g. current location, goal, battery) expire over time.
"""
from __future__ import annotations

import time
from typing import Optional

from backend.core.beliefs.belief import Belief


class TemporalTruthValidator:
    """Enforces validity boundaries and checks if beliefs are currently true."""

    @staticmethod
    def is_valid_at(belief: Belief, timestamp: float) -> bool:
        """Returns True if the belief is temporally valid at the given timestamp."""
        if belief.valid_from > timestamp:
            return False
        if belief.valid_until is not None and belief.valid_until < timestamp:
            return False
        return True

    @classmethod
    def is_currently_valid(cls, belief: Belief) -> bool:
        """Returns True if the belief is currently valid (relative to current system time)."""
        return cls.is_valid_at(belief, time.time())
