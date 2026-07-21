"""Task Fingerprint Deduplicator (Program 16.0) — relocated to orchestrator/runtime/.

Computes a SHA-256 fingerprint over (goal_id, action, sorted params) and
caches task results for a configurable TTL window.
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

    @staticmethod
    def fingerprint(goal_id: str, action: str, params: Dict[str, Any]) -> str:
        canonical = json.dumps(
            {"goal_id": goal_id, "action": action, "params": params},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def is_duplicate(self, fp: str) -> bool:
        with self._lock:
            entry = self._cache.get(fp)
            if entry is None:
                return False
            if time.monotonic() - entry.created_at > self.ttl_seconds:
                del self._cache[fp]
                return False
            return True

    def register(self, fp: str, task_id: str, result: Any = None) -> None:
        with self._lock:
            self._cache[fp] = _CacheEntry(task_id=task_id, result=result)

    def get_cached_result(self, fp: str) -> Optional[Any]:
        with self._lock:
            entry = self._cache.get(fp)
            if entry is None:
                return None
            if time.monotonic() - entry.created_at > self.ttl_seconds:
                del self._cache[fp]
                return None
            return entry.result

    def expire_old(self) -> int:
        now = time.monotonic()
        with self._lock:
            expired = [fp for fp, e in self._cache.items()
                       if now - e.created_at > self.ttl_seconds]
            for fp in expired:
                del self._cache[fp]
        return len(expired)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
