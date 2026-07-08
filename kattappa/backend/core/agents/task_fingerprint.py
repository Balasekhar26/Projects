"""Task Fingerprint Deduplicator (Program 16.0).

Computes a SHA-256 fingerprint over (goal_id, action, sorted params) and
caches task results for a configurable TTL window.  Before the scheduler
dispatches a new task it checks the store; if a matching fingerprint exists
and is still within TTL the cached result is returned immediately, saving
redundant computation and preventing two agents from executing identical work
in parallel.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class _CacheEntry:
    task_id: str
    result: Any
    created_at: float = field(default_factory=time.monotonic)


class TaskFingerprintStore:
    """Thread-safe SHA-256 fingerprint cache with TTL-based expiry."""

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._lock = threading.Lock()
        self._cache: Dict[str, _CacheEntry] = {}
        self.ttl_seconds = ttl_seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def fingerprint(goal_id: str, action: str, params: Dict[str, Any]) -> str:
        """Compute a deterministic hex fingerprint for a task specification."""
        canonical = json.dumps(
            {"goal_id": goal_id, "action": action, "params": params},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def is_duplicate(self, fp: str) -> bool:
        """Return True if a live (within TTL) result exists for this fingerprint."""
        with self._lock:
            entry = self._cache.get(fp)
            if entry is None:
                return False
            if time.monotonic() - entry.created_at > self.ttl_seconds:
                del self._cache[fp]
                return False
            return True

    def register(self, fp: str, task_id: str, result: Any = None) -> None:
        """Store the result for a fingerprint after a task completes."""
        with self._lock:
            self._cache[fp] = _CacheEntry(task_id=task_id, result=result)

    def get_cached_result(self, fp: str) -> Optional[Any]:
        """Retrieve the cached result for a fingerprint, or None if absent/expired."""
        with self._lock:
            entry = self._cache.get(fp)
            if entry is None:
                return None
            if time.monotonic() - entry.created_at > self.ttl_seconds:
                del self._cache[fp]
                return None
            return entry.result

    def expire_old(self) -> int:
        """Sweep and remove all expired entries. Returns the number removed."""
        now = time.monotonic()
        with self._lock:
            expired = [
                fp for fp, e in self._cache.items()
                if now - e.created_at > self.ttl_seconds
            ]
            for fp in expired:
                del self._cache[fp]
        return len(expired)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
