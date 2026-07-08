"""Viewport Mapper (Program 19.1).

Maps relative local coordinates from viewport windows into screen absolute coordinates.
"""
from __future__ import annotations

import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class ViewportMapper:
    """Performs geometric mapping calculations between relative and absolute frames."""

    @classmethod
    def local_to_absolute(
        cls,
        local_x: int,
        local_y: int,
        window_bounds: Dict[str, int]
    ) -> Tuple[int, int]:
        """Maps coordinate offset relative to window top-left into absolute desktop coordinates.

        window_bounds: dict containing keys: "x", "y", "width", "height"
        """
        wx = window_bounds.get("x", 0)
        wy = window_bounds.get("y", 0)
        ww = window_bounds.get("width", 800)
        wh = window_bounds.get("height", 600)

        # Bounds checks & margins capping
        bounded_lx = max(0, min(local_x, ww))
        bounded_ly = max(0, min(local_y, wh))

        absolute_x = wx + bounded_lx
        absolute_y = wy + bounded_ly

        logger.debug(
            "ViewportMapper: Local (%d, %d) mapped inside window (%d, %d) to Absolute (%d, %d)",
            local_x, local_y, wx, wy, absolute_x, absolute_y
        )
        return absolute_x, absolute_y
