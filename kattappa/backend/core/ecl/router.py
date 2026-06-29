from __future__ import annotations

import logging
from typing import Any, Dict

from backend.core.config import load_config
from backend.core.tool_reliability import ToolReliabilityTracker

logger = logging.getLogger(__name__)


class ECLRouter:
    """Intelligently routes tasks to the best local model and verified tools."""

    @classmethod
    def route_task(cls, task_title: str) -> Dict[str, Any]:
        """Routes task to preferred model role and checks recommended tool reliability."""
        text = task_title.lower()
        config = load_config()

        # 1. Model Routing
        coding_keywords = {"code", "python", "javascript", "compile", "bug", "refactor", "database", "sqlite"}
        reasoning_keywords = {"explain", "compare", "analyze", "why", "difference", "architect", "logic"}

        if any(word in text for word in coding_keywords):
            preferred_model_role = "coder"
        elif any(word in text for word in reasoning_keywords):
            preferred_model_role = "power" if config.hardware_profile in {"PERFORMANCE", "BEAST"} else "general"
        else:
            preferred_model_role = "general"

        # 2. Tool Routing & Reliability Filtering
        recommended_tool = None
        tool_confidence = 1.0

        if "file" in text or "write" in text or "read" in text:
            recommended_tool = "file_agent"
        elif "browser" in text or "search" in text or "web" in text:
            recommended_tool = "browser_agent"
        elif "terminal" in text or "bash" in text or "cmd" in text:
            recommended_tool = "terminal_agent"

        if recommended_tool:
            rel = ToolReliabilityTracker.get_reliability(recommended_tool)
            tool_confidence = rel.get("confidence", 1.0)
            if tool_confidence < 0.5:
                logger.warning(
                    "Recommended tool %r has low reliability rating (%f). Advise fallback.",
                    recommended_tool,
                    tool_confidence,
                )

        return {
            "model_role": preferred_model_role,
            "recommended_tool": recommended_tool,
            "tool_confidence": tool_confidence,
        }
