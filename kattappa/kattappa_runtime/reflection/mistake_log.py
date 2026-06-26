"""
Mistake Log — append-only JSONL log of failed/partial reflection cycles.

This feeds Step 25 (Self-Improvement Engine).
Each line is a JSON-serialized Reflection dict whose is_mistake=True.
"""

from __future__ import annotations

import json
import os
from typing import List

from kattappa_runtime.reflection.schema import Reflection

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "mistakes.jsonl")


class MistakeLog:
    """Append-only persistent log of mistakes for self-improvement analysis."""

    def __init__(self, path: str = _DEFAULT_PATH):
        self._path = path

    def record(self, reflection: Reflection) -> None:
        """Append a reflection to the mistake log (only if is_mistake=True)."""
        if not reflection.is_mistake:
            return
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(reflection.to_dict(), ensure_ascii=False) + "\n")

    def load_all(self) -> List[Reflection]:
        """Load every mistake from the log file."""
        if not os.path.exists(self._path):
            return []
        results = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(Reflection.from_dict(json.loads(line)))
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue
        return results

    def count(self) -> int:
        """Number of logged mistakes."""
        return len(self.load_all())
