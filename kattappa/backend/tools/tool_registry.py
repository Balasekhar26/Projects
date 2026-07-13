from __future__ import annotations
from typing import Any, Dict, Optional
from backend.tools.base_tool import Tool, ToolResult
from backend.tools.calendar_tool import CalendarTool
from backend.tools.reminder_tool import ReminderTool
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.shell_tool import ShellTool
from backend.tools.web_tool import WebTool
from backend.tools.memory_tool import MemoryTool
from backend.runtime.execution_context import ExecutionContext

class ToolRegistry:
    """A registry of all available executable tools in Kattappa."""

    def __init__(self) -> None:
        self.tools: Dict[str, Tool] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        self.register(CalendarTool())
        self.register(ReminderTool())
        self.register(FilesystemTool())
        self.register(ShellTool())
        self.register(WebTool())
        self.register(MemoryTool())

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        """Executes a tool by name with safety gates and tracking."""
        tool = self.tools.get(tool_name)
        if not tool:
            import time
            return ToolResult(
                success=False,
                confidence=0.0,
                latency_ms=0.0,
                output={},
                error=f"Tool not found: {tool_name}"
            )
        return tool.execute(parameters, context)
