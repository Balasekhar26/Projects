from __future__ import annotations
import urllib.request
import time
from typing import Any, Dict
from backend.tools.base_tool import Tool, ToolResult
from backend.runtime.execution_context import ExecutionContext

class WebTool(Tool):
    """Fetches text and resources from web links."""
    name = "web_tool"

    def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        start_time = time.time()
        url = parameters.get("url", "")

        if not url:
            latency = (time.time() - start_time) * 1000
            return ToolResult(
                success=False,
                confidence=0.0,
                latency_ms=latency,
                output={},
                error="URL parameter is required."
            )

        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'KattappaAgent/1.0'}
            )
            with urllib.request.urlopen(req, timeout=10.0) as response:
                content = response.read().decode('utf-8')
            
            latency = (time.time() - start_time) * 1000
            return ToolResult(
                success=True,
                confidence=0.95,
                latency_ms=latency,
                output={"url": url, "content": content[:1000]},
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
