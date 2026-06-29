"""Tool Executor Runtime (Program 11.8).

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
from backend.core.execution.context import ExecutionContext
from backend.core.execution.retry_policy import RetryPolicy, ExponentialBackoffPolicy
from backend.core.execution.typed_errors import PermissionDenied, TimeoutError, RetryExhausted

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes a single tool invocation, parsing permissions, constraints, and failures retries."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        permission_mgr: Optional[PermissionManager] = None,
        default_retry_policy: Optional[RetryPolicy] = None,
    ) -> None:
        self.registry = registry or ToolRegistry.get_instance()
        self.permission_mgr = permission_mgr or PermissionManager.get_instance()
        self.default_retry_policy = default_retry_policy or ExponentialBackoffPolicy(jitter=False)

    def execute_tool(
        self,
        name: str,
        args: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ToolResult:
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

        # 2. Check deadline pre-flight
        if context and context.deadline and time.time() > context.deadline:
            return ToolResult(
                tool_name=name,
                status="failed",
                error="Deadline exceeded before execution started.",
            )

        # 3. Execute block with retry policy strategy
        attempts = tool.retries + 1
        last_error = None
        start_time = time.time()

        for attempt in range(attempts):
            # Check cooperative cancellation
            if context and context.cancellation_token and context.cancellation_token.is_cancelled():
                return ToolResult(
                    tool_name=name,
                    status="failed",
                    error="Task execution aborted by cancellation token.",
                )

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
                    # Fetch delay from retry policy
                    delay = self.default_retry_policy.get_delay(attempt)
                    time.sleep(delay)

        execution_time = time.time() - start_time
        return ToolResult(
            tool_name=name,
            status="failed",
            error=f"Tool failed after {attempts} attempts. Last error: {last_error}",
            execution_time=execution_time,
        )
