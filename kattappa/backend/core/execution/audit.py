"""Tool Execution Audit Logger (Program 11).

Logs tool outputs, arguments, latency details, and failures.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from backend.core.execution.tool_models import ToolResult

logger = logging.getLogger(__name__)


class AuditLogger:
    """Stores a history of tool executions for downstream reflection and analysis."""

    _instance: Optional[AuditLogger] = None

    def __init__(self) -> None:
        self.logs: List[Dict[str, Any]] = []

    @classmethod
    def get_instance(cls) -> AuditLogger:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def log_result(self, result: ToolResult, arguments: Dict[str, Any]) -> None:
        """Appends tool outcome record to audit memory list."""
        self.logs.append({
            "tool_name": result.tool_name,
            "status": result.status,
            "arguments": arguments,
            "data": result.data,
            "error": result.error,
            "execution_time": result.execution_time,
        })
        logger.info(
            "Audited tool run for %s. Status: %s. Latency: %.3fs",
            result.tool_name, result.status, result.execution_time
        )

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self.logs)

    def clear(self) -> None:
        self.logs.clear()
