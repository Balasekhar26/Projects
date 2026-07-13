from __future__ import annotations
import subprocess
import time
from typing import Any, Dict
from backend.tools.base_tool import Tool, ToolResult
from backend.runtime.execution_context import ExecutionContext

class ShellTool(Tool):
    """Executes sandboxed commands on the local shell environment."""
    name = "shell_tool"

    def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        start_time = time.time()
        command = parameters.get("command", "")

        if not command:
            latency = (time.time() - start_time) * 1000
            return ToolResult(
                success=False,
                confidence=0.0,
                latency_ms=latency,
                output={},
                error="Command parameter is required."
            )

        try:
            res = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=15.0
            )
            
            success = res.returncode == 0
            latency = (time.time() - start_time) * 1000
            
            return ToolResult(
                success=success,
                confidence=0.99,
                latency_ms=latency,
                output={
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "exit_code": res.returncode
                },
                error=res.stderr if not success else None
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
