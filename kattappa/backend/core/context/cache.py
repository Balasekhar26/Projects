"""LRU/TTL Context Cache Manager (Program 9).

Caches retrieved ContextBundle payloads to reduce redundant database scans.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Optional

from backend.core.context.models import ContextBundle


class ContextCache:
    """Manages fast context access using LRU eviction limits and TTL expiration checks."""

    def __init__(self, capacity: int = 10, ttl_seconds: float = 60.0) -> None:
        self.capacity = capacity
        self.ttl = ttl_seconds
        # OrderedDict acts as a simple LRU cache
        self.cache: OrderedDict[str, tuple[ContextBundle, float]] = OrderedDict()

    def get(self, session_id: str) -> Optional[ContextBundle]:
        """Fetches bundle from cache, returning None if expired or missing."""
        if session_id not in self.cache:
            return None

        bundle, timestamp = self.cache[session_id]
        # Check TTL
        if time.time() - timestamp > self.ttl:
            del self.cache[session_id]
            return None

        # Mark as recently used
        self.cache.move_to_end(session_id)
        return bundle

    def put(self, session_id: str, bundle: ContextBundle) -> None:
        """Saves bundle to cache, evicting the oldest key if capacity limits are hit."""
        if session_id in self.cache:
            del self.cache[session_id]

        if len(self.cache) >= self.capacity:
            # Pop oldest (FIFO/LRU since we move hits to end)
            self.cache.popitem(last=False)

        self.cache[session_id] = (bundle, time.time())

    def clear(self) -> None:
        self.cache.clear()
