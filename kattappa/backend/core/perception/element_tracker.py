"""Element Tracker (Program 19.1).

Tracks and reacquires shifted UI components across window resize or page scroll adjustments.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from backend.core.perception.screen_graph import ScreenGraph

logger = logging.getLogger(__name__)


class ElementTracker:
    """Acquires target locations from active layout snapshots using semantic checks."""

    @classmethod
    def reacquire_element(
        cls,
        target_text: str,
        last_known_bbox: Optional[Tuple[int, int, int, int]],
        current_graph: ScreenGraph
    ) -> Dict[str, Any]:
        """Locates the target text element inside the new layout screen graph.

        Returns search result:
            {
                "success": bool,
                "bbox": (x, y, w, h) or None,
                "center": (cx, cy) or None,
                "shifted": bool
            }
        """
        if not target_text or not current_graph.text_nodes:
            return {"success": False, "bbox": None, "center": None, "shifted": False}

        target_lower = target_text.lower()
        matched_node = None

        # 1. Look for text match first
        for node in current_graph.text_nodes:
            if target_lower == node["text"].lower() or target_lower in node["text"].lower():
                matched_node = node
                break

        if matched_node:
            new_bbox = (matched_node["x"], matched_node["y"], matched_node["w"], matched_node["h"])
            new_center = (matched_node["x"] + matched_node["w"] // 2, matched_node["y"] + matched_node["h"] // 2)
            
            shifted = False
            if last_known_bbox:
                # Compare distance between old coordinate and new coordinate
                old_x, old_y, _, _ = last_known_bbox
                if abs(matched_node["x"] - old_x) > 5 or abs(matched_node["y"] - old_y) > 5:
                    shifted = True

            logger.info("ElementTracker: Reacquired target '%s' (shifted=%s) at center %s", target_text, shifted, new_center)
            return {
                "success": True,
                "bbox": new_bbox,
                "center": new_center,
                "shifted": shifted
            }

        # 2. Proximity fallback: if target text is missing but we have last known bbox, find closest element
        if last_known_bbox:
            old_x, old_y, _, _ = last_known_bbox
            closest_node = None
            min_dist = 999999.0

            for node in current_graph.text_nodes:
                dist = ((node["x"] - old_x) ** 2 + (node["y"] - old_y) ** 2) ** 0.5
                if dist < min_dist and dist < 150:  # within 150 pixels radius
                    min_dist = dist
                    closest_node = node

            if closest_node:
                new_bbox = (closest_node["x"], closest_node["y"], closest_node["w"], closest_node["h"])
                new_center = (closest_node["x"] + closest_node["w"] // 2, closest_node["y"] + closest_node["h"] // 2)
                logger.info("ElementTracker: Text lost. Proximity fallback matched '%s' at center %s", closest_node["text"], new_center)
                return {
                    "success": True,
                    "bbox": new_bbox,
                    "center": new_center,
                    "shifted": True
                }

        return {"success": False, "bbox": None, "center": None, "shifted": False}
