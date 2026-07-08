"""Context Ranking Engine (Program 9).

Ranks retrieved context candidate items based on priority, type source, and timestamps.
"""
from __future__ import annotations

from typing import List
from backend.core.context.models import ContextItem, ContextPriority, ContextSource


class RankingEngine:
    """Ranks and sorts retrieved context items using deterministic scoring metrics."""

    @staticmethod
    def score_and_rank(items: List[ContextItem]) -> List[ContextItem]:
        """Calculates score and sorts items.

        MUST priority = +1.0
        SHOULD priority = +0.5
        POLICY source = +0.3
        WORKING source = +0.2
        EPISODIC source = +0.1
        """
        def calculate_score(item: ContextItem) -> float:
            score = 0.0
            
            # Priority weights
            if item.priority == ContextPriority.MUST:
                score += 1.0
            elif item.priority == ContextPriority.SHOULD:
                score += 0.5
            elif item.priority == ContextPriority.OPTIONAL:
                score += 0.1
                
            # Source weights
            if item.source == ContextSource.POLICY:
                score += 0.3
            elif item.source == ContextSource.WORKING:
                score += 0.2
            elif item.source == ContextSource.EPISODIC:
                score += 0.1
                
            return score

        # Sort in descending order of calculated score
        return sorted(items, key=calculate_score, reverse=True)
