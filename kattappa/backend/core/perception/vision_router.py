"""Vision Router (Program 18.0).

Determines whether a task requires visual grounding or routes to vision-language models.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class VisionRouter:
    """Classifies task objectives and routes them to visual vs. text processing blocks."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def classify_and_route(task_description: str, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Classify a task request and suggest routing metrics.

        Returns route dict:
            {
                "requires_vision": bool,
                "recommended_agent": str,
                "reason": str
            }
        """
        desc = task_description.lower()
        
        # 1. Check payload flags or image paths
        has_image = task_payload.get("image_path") or task_payload.get("image_bytes")
        has_screenshot_request = "screenshot" in desc or "capture screen" in desc

        # 2. Grounding references
        has_grounding = any(word in desc for word in ["click on", "find coordinate", "ground button", "locate text"])

        # 3. Classify and route
        if has_image:
            if "browser" in desc or "webpage" in desc:
                return {
                    "requires_vision": True,
                    "recommended_agent": "Browser",
                    "reason": "Task payload contains image and target references browser view."
                }
            return {
                "requires_vision": True,
                "recommended_agent": "ToolExecutor",
                "reason": "Task payload contains local image to analyze."
            }

        if has_screenshot_request or has_grounding:
            if "browser" in desc:
                return {
                    "requires_vision": True,
                    "recommended_agent": "Browser",
                    "reason": "Task requires browser-based screen grounding."
                }
            return {
                "requires_vision": True,
                "recommended_agent": "ToolExecutor",
                "reason": "Task requires native desktop element grounding."
            }

        # Default text-only path
        return {
            "requires_vision": False,
            "recommended_agent": "Planner",
            "reason": "Standard text-only task payload detected."
        }
