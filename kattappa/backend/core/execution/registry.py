"""Dynamic Tool Registry Manager (Program 11).

Tracks and indexes active tool definitions.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional
from backend.core.execution.tool_models import ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central store supporting tool registrations, updates, and lookups."""

    _instance: Optional[ToolRegistry] = None

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_tool(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s (v%s)", tool.name, tool.version)

    def deregister_tool(self, name: str) -> None:
        if name in self._tools:
            del self._tools[name]
            logger.info("Deregistered tool: %s", name)

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def clear(self) -> None:
        self._tools.clear()
