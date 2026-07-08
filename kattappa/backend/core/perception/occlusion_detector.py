"""Occlusion Detector (Program 19.1).

Scans screen graph overlays to detect if target coordinates are blocked by modal dialogs.
"""
from __future__ import annotations

import logging
from typing import Dict

from backend.core.perception.screen_graph import ScreenGraph

logger = logging.getLogger(__name__)


class OcclusionDetector:
    """Evaluates spatial collision matches between click paths and overlay boxes."""

    @classmethod
    def is_occluded(cls, x: int, y: int, screen_graph: ScreenGraph) -> Dict[str, Any]:
        """Asserts whether coordinates (x, y) are blocked/occluded by a modal container.

        If a modal dialog is active, it blocks interactions with elements in the background.
        """
        # Find if any active popup/modal header container is open
        modal_container = None
        for container in screen_graph.containers:
            # simple key pattern matching columns or alerts
            if "alert" in container["container_id"] or "modal" in container["container_id"] or "col_300" in container["container_id"]:
                # Check container text for validation
                modal_container = container
                break

        # Check if we have nodes containing "cancel" or "close" representing open popups
        has_blocking_popup = any("cancel" in n["text"].lower() or "confirm" in n["text"].lower() for n in screen_graph.text_nodes)

        # If a popup container exists, check if coordinate lies outside of it
        if has_blocking_popup and modal_container:
            mx = modal_container["x"]
            my = modal_container["y"]
            mw = modal_container["w"]
            mh = modal_container["h"]

            # If click coordinate is outside the bounds of the modal box, it is occluded!
            inside = (mx <= x <= mx + mw) and (my <= y <= my + mh)
            if not inside:
                logger.warning(
                    "OcclusionDetector: Click coordinate (%d, %d) is blocked/occluded by modal container at (%d, %d, %d, %d)",
                    x, y, mx, my, mw, mh
                )
                return {
                    "occluded": True,
                    "reason": "Target is hidden behind a blocking modal dialog overlay."
                }

        return {"occluded": False, "reason": "No active occlusion detected."}
