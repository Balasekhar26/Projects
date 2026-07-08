"""Scroll Search (Program 19.1).

Triggers vertical viewport scrolling when target items reside off-screen.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional

import pyautogui

from backend.core.perception.screen_graph import ScreenGraph

logger = logging.getLogger(__name__)


class ScrollSearch:
    """Iteratively scroll-pages the screen view to search for off-screen UI elements."""

    @classmethod
    def search_for_element(
        cls,
        target_text: str,
        capture_and_ocr_fn: Callable[[], ScreenGraph],
        max_scrolls: int = 3,
        scroll_amount: int = -300
    ) -> Dict[str, Any]:
        """Scrolls down looking for target_text.

        capture_and_ocr_fn: Callable returning active ScreenGraph
        """
        logger.info("ScrollSearch: Starting vertical search page sweeps for '%s'", target_text)
        target_lower = target_text.lower()

        # 1. First Pass: check if already visible
        graph = capture_and_ocr_fn()
        for node in graph.text_nodes:
            if target_lower in node["text"].lower():
                return {
                    "success": True,
                    "graph": graph,
                    "node": node,
                    "scrolls_count": 0
                }

        # 2. Iterative Scroll Loop
        for step in range(1, max_scrolls + 1):
            logger.info("ScrollSearch: Step %d/%d. Scrolling %d px", step, max_scrolls, scroll_amount)
            
            # Perform scroll
            pyautogui.scroll(scroll_amount)
            time.sleep(0.5)  # Wait for render settling
            
            # Re-capture
            graph = capture_and_ocr_fn()
            for node in graph.text_nodes:
                if target_lower in node["text"].lower():
                    logger.info("ScrollSearch: Found '%s' after %d scroll sweeps.", target_text, step)
                    return {
                        "success": True,
                        "graph": graph,
                        "node": node,
                        "scrolls_count": step
                    }

        logger.warning("ScrollSearch: Failed to find target '%s' within scroll limits.", target_text)
        return {
            "success": False,
            "graph": graph,
            "node": None,
            "scrolls_count": max_scrolls
        }
