"""Quality Filter (Program 26.0).

Removes low-confidence, empty, or contradictory extraction records before
they enter the fine-tuning corpus.
"""
from __future__ import annotations

from typing import Any, Dict, List


class QualityFilter:
    """Filters extracted records to ensure only high-quality samples enter the dataset."""

    DEFAULT_MIN_SCORE = 0.5

    @classmethod
    def filter(
        cls,
        records: List[Dict[str, Any]],
        min_score: float = DEFAULT_MIN_SCORE,
        allow_failed: bool = False,
        require_actions: bool = True,
    ) -> List[Dict[str, Any]]:
        """Applies quality gates to a list of extraction records.

        Args:
            records:         Raw extracted records from TraceExtractor.
            min_score:       Minimum combined_score to pass (default 0.5).
            allow_failed:    If True, keep "failure" result records (useful for
                             preference/alignment datasets). Default False.
            require_actions: If True, discard records with empty actions list.

        Returns:
            Filtered list of records that passed all gates.
        """
        passed: List[Dict[str, Any]] = []

        for rec in records:
            metrics = rec.get("metrics", {})
            score = float(metrics.get("combined_score", 0.0))
            result = rec.get("result", "failure")
            actions = rec.get("actions", [])

            # Gate 1: score threshold
            if score < min_score:
                continue

            # Gate 2: failed results (only admitted when explicitly requested)
            if result == "failure" and not allow_failed:
                continue

            # Gate 3: non-empty action sequences
            if require_actions and not actions:
                continue

            passed.append(rec)

        return passed
