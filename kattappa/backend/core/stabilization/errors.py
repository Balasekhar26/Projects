"""Standardized Custom Cognitive Error Taxonomy (Program 8.5).

Defines base KattappaError and module-specific classified exceptions.
"""
from __future__ import annotations

from typing import Optional


class KattappaError(Exception):
    """Base exception for all system modules within Kattappa AI OS."""

    def __init__(
        self,
        message: str,
        error_code: str = "SYS_ERR",
        severity: str = "ERROR",  # WARNING, ERROR, CRITICAL
        recoverable: bool = True,
        trace_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.severity = severity
        self.recoverable = recoverable
        self.trace_id = trace_id


class PlannerError(KattappaError):
    def __init__(
        self,
        message: str,
        error_code: str = "PLAN_ERR",
        severity: str = "ERROR",
        recoverable: bool = True,
        trace_id: Optional[str] = None,
    ) -> None:
        super().__init__(message, error_code, severity, recoverable, trace_id)


class ExecutionError(KattappaError):
    def __init__(
        self,
        message: str,
        error_code: str = "EXEC_ERR",
        severity: str = "ERROR",
        recoverable: bool = True,
        trace_id: Optional[str] = None,
    ) -> None:
        super().__init__(message, error_code, severity, recoverable, trace_id)


class ReflectionError(KattappaError):
    def __init__(
        self,
        message: str,
        error_code: str = "REFL_ERR",
        severity: str = "ERROR",
        recoverable: bool = True,
        trace_id: Optional[str] = None,
    ) -> None:
        super().__init__(message, error_code, severity, recoverable, trace_id)


class LearningError(KattappaError):
    def __init__(
        self,
        message: str,
        error_code: str = "LRN_ERR",
        severity: str = "ERROR",
        recoverable: bool = True,
        trace_id: Optional[str] = None,
    ) -> None:
        super().__init__(message, error_code, severity, recoverable, trace_id)


class MemoryError(KattappaError):
    def __init__(
        self,
        message: str,
        error_code: str = "MEM_ERR",
        severity: str = "CRITICAL",
        recoverable: bool = False,
        trace_id: Optional[str] = None,
    ) -> None:
        super().__init__(message, error_code, severity, recoverable, trace_id)


class SecurityError(KattappaError):
    def __init__(
        self,
        message: str,
        error_code: str = "SEC_ERR",
        severity: str = "CRITICAL",
        recoverable: bool = False,
        trace_id: Optional[str] = None,
    ) -> None:
        super().__init__(message, error_code, severity, recoverable, trace_id)
