"""Tool Execution Workflow Dispatcher (Program 11).

Dispatches and logs sequential sequences of tool invocations.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from backend.core.execution.tool_models import ToolResult
from backend.core.execution.executor import ToolExecutor

logger = logging.getLogger(__name__)


class ToolDispatcher:
    """Dispatches sequences of tool calls, passing outputs and handling early aborts on failures."""

    def __init__(self, executor: ToolExecutor) -> None:
        self.executor = executor

    def dispatch_chain(
        self,
        calls: List[tuple[str, Dict[str, Any]]],
    ) -> List[ToolResult]:
        """Executes a list of tool calls sequentially."""
        results = []
        for name, args in calls:
            logger.info("Dispatching tool call: %s with args: %s", name, args)
            res = self.executor.execute_tool(name, args)
            results.append(res)
            
            # Abort chain if a step fails
            if res.status == "failed":
                logger.warning("Dispatcher chain aborted due to tool failure: %s", name)
                break
                
        return results
