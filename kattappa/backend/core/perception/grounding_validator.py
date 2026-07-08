"""Grounding Validator (Program 19.1).

Validates spatial alignment of click coordinates against target element bounds.
"""
from __future__ import annotations

import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class GroundingValidator:
    """Verifies that dispatched actions physically land inside targeted bounding boxes."""

    @classmethod
    def validate_grounding_click(
        cls,
        click_coord: Tuple[int, int],
        target_bbox: Tuple[int, int, int, int]
    ) -> Dict[str, Any]:
        """Asserts whether click landing points lie inside the element's coordinate limits."""
        cx, cy = click_coord
        tx, ty, tw, th = target_bbox

        inside = (tx <= cx <= tx + tw) and (ty <= cy <= ty + th)

        if inside:
            logger.info("GroundingValidator: Click (%d, %d) validated inside bbox (%d, %d, %d, %d)", cx, cy, tx, ty, tw, th)
            return {
                "success": True,
                "message": "Click target landed within bounds."
            }

        logger.warning("GroundingValidator: Click (%d, %d) landed OUTSIDE target bbox (%d, %d, %d, %d)", cx, cy, tx, ty, tw, th)
        return {
            "success": False,
            "message": f"Click landing point ({cx}, {cy}) missed target bounds ({tx}, {ty}, {tw}, {th})."
        }
