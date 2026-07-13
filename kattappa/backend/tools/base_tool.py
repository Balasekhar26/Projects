from __future__ import annotations
from typing import Any, Dict, List, Optional
from backend.runtime.execution_context import ExecutionContext

class ToolResult:
    """Standard execution result returned by all tools."""

    def __init__(
        self,
        success: bool,
        confidence: float,
        latency_ms: float,
        output: Dict[str, Any],
        error: Optional[str] = None,
        artifact_ids: Optional[List[str]] = None
    ) -> None:
        self.success = success
        self.confidence = confidence
        self.latency_ms = latency_ms
        self.output = output
        self.error = error
        self.artifact_ids = artifact_ids or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "output": self.output,
            "error": self.error,
            "artifact_ids": self.artifact_ids
        }


class Tool:
    """Base class for all executable tools in the Kattappa ecosystem."""
    name: str

    def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        raise NotImplementedError("Tools must implement the execute method.")
