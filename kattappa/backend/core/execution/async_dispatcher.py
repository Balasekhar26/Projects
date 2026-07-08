"""Asynchronous Parallel Tool Dispatcher (Program 11.5).

Runs multiple tool invocations concurrently using asyncio thread pools.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any, Dict, List

from backend.core.execution.tool_models import ToolResult
from backend.core.execution.executor import ToolExecutor

logger = logging.getLogger(__name__)


class AsyncToolDispatcher:
    """Dispatches tool call workflows concurrently, supporting async gathering."""

    def __init__(self, executor: ToolExecutor) -> None:
        self.executor = executor
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=5)

    async def async_dispatch_parallel(
        self,
        calls: List[tuple[str, Dict[str, Any]]],
    ) -> List[ToolResult]:
        """Runs multiple calls concurrently in worker threads, gathering results."""
        loop = asyncio.get_running_loop()
        
        async def run_one(name: str, args: Dict[str, Any]) -> ToolResult:
            logger.info("Async dispatching tool call: %s", name)
            # Run blocking tool call inside thread pool
            return await loop.run_in_executor(
                self._thread_pool,
                self.executor.execute_tool,
                name,
                args,
            )

        tasks = [run_one(name, args) for name, args in calls]
        return list(await asyncio.gather(*tasks))
