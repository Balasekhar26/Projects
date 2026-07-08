"""Capability-Based Tool Matcher (Program 11).

Dynamically resolves matching tools based on required capability tags.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from backend.core.execution.tool_models import ToolDefinition
from backend.core.execution.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolCapabilityMatcher:
    """Selects best tool matches using capability tags metadata queries."""

    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.registry = registry or ToolRegistry.get_instance()

    def find_matching_tools(self, required_capabilities: List[str]) -> List[ToolDefinition]:
        """Returns tools carrying all requested capabilities tags."""
        matches = []
        for tool in self.registry.list_tools():
            # Check if tool meets all tags
            has_all = True
            for cap in required_capabilities:
                if cap not in tool.capabilities:
                    has_all = False
                    break
            if has_all:
                matches.append(tool)
        return matches
