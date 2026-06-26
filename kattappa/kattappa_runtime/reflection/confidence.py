"""
Confidence Tracker — per-domain confidence register.

Kattappa maintains one confidence score per skill domain.
The Reflection Engine calls update() after every action cycle
to adjust the score based on whether the action succeeded or not.

Score bounds: [0.0, 1.0]
Default starting confidence: 0.6 (moderately confident)

Confidence is persisted to a JSON file next to this module so it
survives process restarts.
"""

from __future__ import annotations

import json
import os
from threading import Lock
from typing import Dict

_DEFAULT_CONFIDENCE = 0.6
_BOUNDS = (0.0, 1.0)

# Path where confidence scores are persisted
_PERSIST_PATH = os.path.join(os.path.dirname(__file__), "confidence_scores.json")


class ConfidenceTracker:
    """Thread-safe per-domain confidence register with file persistence."""

    def __init__(self, persist_path: str = _PERSIST_PATH):
        self._path = persist_path
        self._lock = Lock()
        self._scores: Dict[str, float] = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, domain: str) -> float:
        """Return current confidence for a domain. Defaults to 0.6."""
        with self._lock:
            return self._scores.get(domain, _DEFAULT_CONFIDENCE)

    def update(self, domain: str, delta: float) -> float:
        """
        Apply delta to the domain score, clamp to [0, 1], persist, return new value.

        Parameters
        ----------
        domain : str
            Skill domain identifier (e.g. "translation").
        delta : float
            Signed adjustment. Positive = more confident, negative = less.

        Returns
        -------
        float
            New confidence value after adjustment.
        """
        with self._lock:
            current = self._scores.get(domain, _DEFAULT_CONFIDENCE)
            new_val = max(_BOUNDS[0], min(_BOUNDS[1], current + delta))
            self._scores[domain] = new_val
            self._save()
            return new_val

    def reset(self, domain: str) -> None:
        """Reset a domain back to the default starting confidence."""
        with self._lock:
            self._scores[domain] = _DEFAULT_CONFIDENCE
            self._save()

    def all_scores(self) -> Dict[str, float]:
        """Return a snapshot of all current confidence scores."""
        with self._lock:
            return dict(self._scores)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> Dict[str, float]:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return {k: float(v) for k, v in data.items()}
            except (json.JSONDecodeError, ValueError):
                pass
        return {}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._scores, f, indent=2)
        except OSError:
            pass  # Non-fatal: scores will reset next run
