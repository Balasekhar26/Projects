"""Tool Executor Runtime (Program 11).

Invokes tool logic, applying permissions gates, timeout limits, and retry backoffs.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from backend.core.execution.tool_models import ToolDefinition, ToolResult
from backend.core.execution.registry import ToolRegistry
from backend.core.execution.permissions import PermissionManager
from backend.core.execution.timeout import TimeoutManager

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes a single tool invocation, parsing permissions, constraints, and failures retries."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        permission_mgr: Optional[PermissionManager] = None,
    ) -> None:
        self.registry = registry or ToolRegistry.get_instance()
        self.permission_mgr = permission_mgr or PermissionManager.get_instance()

    def execute_tool(self, name: str, args: Dict[str, Any]) -> ToolResult:
        """Looks up tool, verifies authorization, executes block with retries and timeout bounds."""
        tool = self.registry.get_tool(name)
        if not tool:
            return ToolResult(
                tool_name=name,
                status="failed",
                error=f"Tool '{name}' not found in registry.",
            )

        # 1. Verify permissions
        if not self.permission_mgr.verify_permissions(tool):
            return ToolResult(
                tool_name=name,
                status="failed",
                error=f"Permission denied for tool '{name}'. Required: {tool.required_permissions}",
            )

        # 2. Execute block with retry logic
        attempts = tool.retries + 1
        last_error = None
        start_time = time.time()

        for attempt in range(attempts):
            try:
                logger.info("Executing tool %s (attempt %d/%d)", name, attempt + 1, attempts)
                # Run with timeout verification
                data = TimeoutManager.run_with_timeout(tool.func, tool.timeout, **args)
                execution_time = time.time() - start_time
                
                return ToolResult(
                    tool_name=name,
                    status="ok",
                    data=data,
                    execution_time=execution_time,
                )
            except Exception as exc:
                last_error = str(exc)
                logger.warning("Tool %s failed: %s", name, last_error)
                if attempt < attempts - 1:
                    # Exponential backoff delay
                    time.sleep(0.01 * (2 ** attempt))

        execution_time = time.time() - start_time
        return ToolResult(
            tool_name=name,
            status="failed",
            error=f"Tool failed after {attempts} attempts. Last error: {last_error}",
            execution_time=execution_time,
        )
