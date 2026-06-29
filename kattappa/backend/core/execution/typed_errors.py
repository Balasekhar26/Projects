"""Typed Tool Exception Hierarchy (Program 11.8).

Standardizes runtime exceptions classification and metadata for downstream planners.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from backend.core.execution.structured_errors import ToolErrorCode


class ToolError(Exception):
    """Base tool execution exception class."""
    def __init__(self, code: ToolErrorCode, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class ValidationError(ToolError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(ToolErrorCode.VALIDATION, message, details)


class TimeoutError(ToolError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(ToolErrorCode.TIMEOUT, message, details)


class PermissionDenied(ToolError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(ToolErrorCode.PERMISSION_DENIED, message, details)


class CircuitOpen(ToolError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(ToolErrorCode.CIRCUIT_OPEN, message, details)


class RateLimited(ToolError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(ToolErrorCode.RATE_LIMIT, message, details)


class RetryExhausted(ToolError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(ToolErrorCode.UNKNOWN, message, details)
