"""Inference Response TTL Cache (Program 10).

Caches full InferenceResponse payloads keyed by request prompts.
"""
from __future__ import annotations

import hashlib
import time
from typing import Dict, Optional

from backend.core.inference.models import InferenceResponse


class ResponseCache:
    """Stores query response bundles to prevent redundant model calls."""

    def __init__(self, ttl_seconds: float = 60.0) -> None:
        self.ttl = ttl_seconds
        self.cache: Dict[str, tuple[InferenceResponse, float]] = {}

    def _hash_key(self, prompt: str, system: str) -> str:
        data = f"{system}:::{prompt}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def get(self, prompt: str, system: str = "") -> Optional[InferenceResponse]:
        key = self._hash_key(prompt, system)
        if key not in self.cache:
            return None

        response, timestamp = self.cache[key]
        if time.time() - timestamp > self.ttl:
            del self.cache[key]
            return None

        return response

    def put(self, prompt: str, system: str, response: InferenceResponse) -> None:
        key = self._hash_key(prompt, system)
        self.cache[key] = (response, time.time())

    def clear(self) -> None:
        self.cache.clear()
