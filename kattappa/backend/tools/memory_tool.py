from __future__ import annotations
import time
from typing import Any, Dict
from backend.tools.base_tool import Tool, ToolResult
from backend.runtime.execution_context import ExecutionContext
from backend.core.memory import remember, recall

class MemoryTool(Tool):
    """Integrates directly with Kattappa's episodic and semantic memory subsystems."""
    name = "memory_tool"

    def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        start_time = time.time()
        operation = parameters.get("operation", "read")
        content = parameters.get("content", "")
        category = parameters.get("category", "episodic")

        try:
            if operation == "write":
                remember(content, category=category)
                latency = (time.time() - start_time) * 1000
                return ToolResult(
                    success=True,
                    confidence=0.99,
                    latency_ms=latency,
                    output={"status": "WRITTEN", "category": category},
                    error=None
                )

            elif operation == "read" or operation == "recall":
                query = parameters.get("query", "")
                result_text = recall(query)
                latency = (time.time() - start_time) * 1000
                return ToolResult(
                    success=True,
                    confidence=0.99,
                    latency_ms=latency,
                    output={"status": "RECALLED", "query": query, "content": result_text},
                    error=None
                )

        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return ToolResult(
                success=False,
                confidence=0.0,
                latency_ms=latency,
                output={},
                error=str(e)
            )

        latency = (time.time() - start_time) * 1000
        return ToolResult(
            success=False,
            confidence=0.0,
            latency_ms=latency,
            output={},
            error=f"Unsupported operation: {operation}"
        )
