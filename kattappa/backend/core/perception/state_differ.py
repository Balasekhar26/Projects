"""State Differ (Program 18.1).

Compares before and after screen graphs to extract visual, structural, and text deltas.
"""
from __future__ import annotations

from typing import Any, Dict, List

from backend.core.perception.screen_graph import ScreenGraph


class StateDiffer:
    """Calculates node additions, removals, and movement shifts between two layout snapshots."""

    @classmethod
    def diff_graphs(cls, before: Optional[ScreenGraph], after: Optional[ScreenGraph]) -> Dict[str, Any]:
        """Compares before/after graphs and builds difference matrices.

        Returns delta dictionary:
            {
                "added_texts": list[str],
                "removed_texts": list[str],
                "moved_elements": list[dict],
                "modal_opened": bool
            }
        """
        added_texts: List[str] = []
        removed_texts: List[str] = []
        moved_elements: List[Dict[str, Any]] = []
        modal_opened = False

        before_nodes = before.text_nodes if before else []
        after_nodes = after.text_nodes if after else []

        before_texts_map = {node["text"].lower(): node for node in before_nodes}
        after_texts_map = {node["text"].lower(): node for node in after_nodes}

        # 1. Added Texts
        for text, node in after_texts_map.items():
            if text not in before_texts_map:
                added_texts.append(node["text"])
            else:
                # Node exists in both; check coordinates shift (movement)
                prev = before_texts_map[text]
                dx = node["x"] - prev["x"]
                dy = node["y"] - prev["y"]
                if abs(dx) > 10 or abs(dy) > 10:  # Threshold of 10px shift
                    moved_elements.append({
                        "text": node["text"],
                        "from": (prev["x"], prev["y"]),
                        "to": (node["x"], node["y"]),
                        "shift": (dx, dy)
                    })

        # 2. Removed Texts
        for text, node in before_texts_map.items():
            if text not in after_texts_map:
                removed_texts.append(node["text"])

        # 3. Dialog Box Modal Detection
        # Check if an alert/modal node appeared in the after-state
        popup_keywords = ["confirm", "warning", "permission", "alert", "error popup", "cancel"]
        before_has_popup = any(any(kw in n["text"].lower() for kw in popup_keywords) for n in before_nodes)
        after_has_popup = any(any(kw in n["text"].lower() for kw in popup_keywords) for n in after_nodes)
        if after_has_popup and not before_has_popup:
            modal_opened = True

        return {
            "added_texts": added_texts,
            "removed_texts": removed_texts,
            "moved_elements": moved_elements,
            "modal_opened": modal_opened
        }
