"""Confidence Scoring Engine (Program 7).

Evaluates candidate occurrences count to determine evidence-based confidence levels.
"""
from __future__ import annotations


class ConfidenceEngine:
    """Calculates evidence-based confidence scores for proposed updates."""

    @staticmethod
    def calculate_score(occurrence_count: int) -> float:
        """Computes empirical score curve based on observations count.

        Count 1 -> 0.25
        Count 5 -> ~0.76
        Count 20 -> ~0.99
        """
        if occurrence_count <= 0:
            return 0.0
        # Formula: 1.0 - (0.75 ** occurrence_count)
        score = 1.0 - (0.75 ** occurrence_count)
        return round(score, 3)
