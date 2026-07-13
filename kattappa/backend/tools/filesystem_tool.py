from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Any, Dict
from backend.tools.base_tool import Tool, ToolResult
from backend.runtime.execution_context import ExecutionContext

class FilesystemTool(Tool):
    """Provides physical read, write, and list operations on the filesystem."""
    name = "filesystem_tool"

    def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        start_time = time.time()
        operation = parameters.get("operation", "list")
        path_str = parameters.get("path", "")
        
        if not path_str:
            latency = (time.time() - start_time) * 1000
            return ToolResult(
                success=False,
                confidence=0.0,
                latency_ms=latency,
                output={},
                error="Path parameter is required."
            )

        target_path = Path(path_str)

        try:
            if operation == "create_file" or operation == "write_file":
                content = parameters.get("content", "")
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, "w") as f:
                    f.write(content)
                
                latency = (time.time() - start_time) * 1000
                return ToolResult(
                    success=True,
                    confidence=0.99,
                    latency_ms=latency,
                    output={"path": str(target_path), "bytes_written": len(content)},
                    error=None,
                    artifact_ids=[str(target_path)]
                )

            elif operation == "list":
                if not target_path.exists():
                    raise FileNotFoundError(f"Directory {target_path} does not exist.")
                if not target_path.is_dir():
                    raise NotADirectoryError(f"Path {target_path} is not a directory.")

                files = os.listdir(target_path)
                latency = (time.time() - start_time) * 1000
                return ToolResult(
                    success=True,
                    confidence=0.99,
                    latency_ms=latency,
                    output={"path": str(target_path), "files": files},
                    error=None
                )

            elif operation == "read_file":
                if not target_path.exists():
                    raise FileNotFoundError(f"File {target_path} does not exist.")
                with open(target_path, "r") as f:
                    content = f.read()

                latency = (time.time() - start_time) * 1000
                return ToolResult(
                    success=True,
                    confidence=0.99,
                    latency_ms=latency,
                    output={"path": str(target_path), "content": content},
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
