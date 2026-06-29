"""Standardized Structured Tool Errors Taxonomy (Program 11.5).
"""
from __future__ import annotations

from enum import Enum


class ToolErrorCode(str, Enum):
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    VALIDATION = "VALIDATION"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    UNKNOWN = "UNKNOWN"


class ToolExecutionError(Exception):
    """Exception carrying structured error taxonomy details."""

    def __init__(self, code: ToolErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
