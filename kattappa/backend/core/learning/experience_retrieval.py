"""Experience Retrieval Indexer (Program 21.0).

Searches and ranks past execution trajectories matching semantic attributes of current goals.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Set

from backend.core.learning.experience_store import ExperienceStore
from backend.core.learning.trajectory_builder import Trajectory

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _extract_tokens(text: str) -> Set[str]:
    """Helper converting text string to token sets."""
    if not text:
        return set()
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 2}


class ExperienceRetrieval:
    """Finds closely aligned historical trajectories to guide planning decisions."""

    @classmethod
    def find_similar_experiences(
        cls,
        target_goal_description: str,
        store: ExperienceStore,
        min_score: float = 0.1,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Matches goal keywords against historical runs to return similarity records.

        Returns matching trajectories ordered by score desc:
            [{"trajectory": Trajectory, "score": float}, ...]
        """
        target_tokens = _extract_tokens(target_goal_description)
        if not target_tokens or not store.trajectories:
            return []

        scored_records = []
        for t in store.trajectories:
            # Combine elements of trajectory to match tokens
            hist_tokens = _extract_tokens(t.goal_id)
            for node in t.nodes_executed:
                hist_tokens.update(_extract_tokens(node))

            # Jaccard similarity or simple intersection
            union = target_tokens.union(hist_tokens)
            intersection = target_tokens.intersection(hist_tokens)
            
            score = len(intersection) / len(union) if union else 0.0

            if score >= min_score:
                scored_records.append({
                    "trajectory": t,
                    "score": round(score, 3)
                })

        # Sort by similarity score descending, success descending
        scored_records.sort(key=lambda item: (-item["score"], -int(item["trajectory"].success)))
        
        results = scored_records[:limit]
        logger.info(
            "ExperienceRetrieval: Matched %d similar experiences for target goal '%s'",
            len(results), target_goal_description
        )
        return results
