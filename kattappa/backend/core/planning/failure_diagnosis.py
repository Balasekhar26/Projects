"""Failure Diagnosis Engine (Program 32.0).

Analyzes task step failures, categorizes issues (preconditions, timeouts, permissions),
and suggests optimized recovery policies (retry, replan, user escalation).
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Tuple


class FailureType(str, Enum):
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    TIMEOUT = "TIMEOUT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"


class RecoveryAction(str, Enum):
    RETRY = "RETRY"
    REPLAN = "REPLAN"
    ESCALATE = "ESCALATE"


class FailureDiagnosisEngine:
    """Classifies task execution errors and returns standard recovery policies."""

    @classmethod
    def diagnose_failure(
        self,
        exception: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[FailureType, RecoveryAction, str]:
        """Analyzes exception types and returns structured recovery recommendations."""
        exc_name = type(exception).__name__
        msg = str(exception)
        
        # 1. Timeout validations
        if "TimeoutError" in exc_name or "timeout" in msg.lower():
            return (
                FailureType.TIMEOUT,
                RecoveryAction.RETRY,
                "Operation exceeded deadline bounds. Suggesting step retry.",
            )

        # 2. Permission checks
        if "PermissionError" in exc_name or "permission" in msg.lower():
            return (
                FailureType.PERMISSION_DENIED,
                RecoveryAction.ESCALATE,
                "Privilege boundaries crossed. Suggesting escalation to user.",
            )

        # 3. Precondition failures
        if "PreconditionError" in exc_name or "precondition" in msg.lower():
            return (
                FailureType.PRECONDITION_FAILED,
                RecoveryAction.REPLAN,
                "State variables do not match step preconditions. Suggesting replanning.",
            )

        # 4. Resource issues
        if "ConnectionError" in exc_name or "resource" in msg.lower() or "unavailable" in msg.lower():
            return (
                FailureType.RESOURCE_UNAVAILABLE,
                RecoveryAction.RETRY,
                "Target resource unavailable. Suggesting delayed retry.",
            )

        # 5. Default fallback runtime errors
        return (
            FailureType.EXECUTION_ERROR,
            RecoveryAction.REPLAN,
            f"Execution error ({exc_name}): {msg}. Suggesting general replan.",
        )
