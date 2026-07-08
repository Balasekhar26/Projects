"""UI Grounder (Program 18.0).

Resolves text-based query intents (e.g., "click submit") to absolute bounding box coordinates.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from backend.core.perception.screen_graph import ScreenGraph

logger = logging.getLogger(__name__)


class UIGrounder:
    """Matches semantic queries against UI layout elements and coordinates."""

    def __init__(self, screen_graph: ScreenGraph) -> None:
        self.screen_graph = screen_graph

    def ground_target(self, query: str) -> Dict[str, Any]:
        """Grounds a semantic query string onto the best matching screen element.

        Returns match result dict:
            {
                "success": bool,
                "element_id": str or None,
                "text": str or None,
                "bbox": (left, top, width, height) or None,
                "center": (x, y) or None,
                "confidence": float
            }
        """
        # Normalize query (lowercase, strip visual action prefixes like "click", "select")
        clean_query = self._normalize_query(query)
        if not clean_query:
            return self._empty_result()

        best_node = None
        best_score = 0.0

        for node in self.screen_graph.text_nodes:
            score = self._compute_match_score(clean_query, node["text"].lower())
            if score > best_score:
                best_score = score
                best_node = node

        # Confidence cutoff (e.g. 0.3)
        if best_node and best_score >= 0.3:
            bbox = (best_node["x"], best_node["y"], best_node["w"], best_node["h"])
            center = (best_node["x"] + best_node["w"] // 2, best_node["y"] + best_node["h"] // 2)
            
            logger.info(
                "UIGrounder: Grounded query '%s' to '%s' (conf: %.2f) at center %s",
                query, best_node["text"], best_score, center
            )
            return {
                "success": True,
                "element_id": best_node["id"],
                "text": best_node["text"],
                "bbox": bbox,
                "center": center,
                "confidence": round(best_score, 2)
            }

        return self._empty_result()

    def _normalize_query(self, query: str) -> str:
        """Strips action verbs to identify core semantic content."""
        q = query.lower().strip()
        # Regex patterns to strip "click", "select", "press", "go to", etc.
        patterns = [
            r"^click\s+(?:on\s+)?",
            r"^select\s+",
            r"^press\s+",
            r"^go\s+to\s+",
            r"^type\s+(?:in|into)?\s+",
            r"\s+button$",
            r"\s+link$",
            r"\s+field$"
        ]
        for pat in patterns:
            q = re.sub(pat, "", q)
        return q.strip()

    def _compute_match_score(self, query: str, node_text: str) -> float:
        """Returns match rating [0.0 - 1.0] representing overlap/similarity."""
        # 1. Exact match
        if query == node_text:
            return 1.0
        
        # 2. Sub-string match
        if query in node_text:
            # penalize length difference to favor tighter bounds
            return 0.9 * (len(query) / len(node_text))

        # 3. Word set overlap match
        q_words = set(query.split())
        n_words = set(node_text.split())
        if q_words.intersection(n_words):
            intersect = len(q_words.intersection(n_words))
            union = len(q_words.union(n_words))
            return 0.7 * (intersect / union)

        # 4. Fuzzy distance fallback (simple character set similarity)
        char_intersection = len(set(query) & set(node_text))
        char_union = len(set(query) | set(node_text))
        if char_union > 0:
            return 0.3 * (char_intersection / char_union)

        return 0.0

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "success": False,
            "element_id": None,
            "text": None,
            "bbox": None,
            "center": None,
            "confidence": 0.0
        }
