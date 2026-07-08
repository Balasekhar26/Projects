"""Curriculum Generator (Program 26.0).

Sorts training samples from simple to complex so fine-tuning proceeds in staged
difficulty order — a standard curriculum learning strategy.

Complexity scoring:
    simple  : 1 action, 0 failures, 0 recoveries
    medium  : 2–5 actions or any recoveries
    complex : 6+ actions, or failures > 0, or high cost / long duration
"""
from __future__ import annotations

from typing import Any, Dict, List


def _complexity_score(record: Dict[str, Any]) -> float:
    """Assigns a numeric complexity value to a single extraction record."""
    metrics = record.get("metrics", {})
    actions = record.get("actions", [])

    score = 0.0
    score += len(actions) * 1.0
    score += float(metrics.get("failures", 0)) * 3.0
    score += float(metrics.get("recoveries", 0)) * 2.0
    score += float(metrics.get("duration", 0.0)) * 0.1
    score += float(metrics.get("cost", 0.0)) * 5.0
    return score


class CurriculumGenerator:
    """Orders dataset samples by ascending complexity for staged fine-tuning."""

    @classmethod
    def sort(cls, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Returns records sorted from simplest to most complex."""
        return sorted(records, key=_complexity_score)

    @classmethod
    def label_difficulty(cls, record: Dict[str, Any]) -> str:
        """Returns 'simple', 'medium', or 'complex' label for a record."""
        score = _complexity_score(record)
        if score <= 3.0:
            return "simple"
        elif score <= 12.0:
            return "medium"
        return "complex"

    @classmethod
    def annotate(cls, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Returns records with an added 'difficulty' field, sorted by complexity."""
        annotated = []
        for rec in cls.sort(records):
            copy = dict(rec)
            copy["difficulty"] = cls.label_difficulty(rec)
            annotated.append(copy)
        return annotated
