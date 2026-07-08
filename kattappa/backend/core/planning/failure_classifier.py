"""Failure Classification Taxonomy (Program 12.4).
"""
from __future__ import annotations

import socket
from enum import Enum
from typing import Any, Optional

from backend.core.execution.typed_errors import (
    ValidationError,
    TimeoutError as ExecTimeoutError,
    PermissionDenied as ExecPermissionDenied,
)



class FailureCategory(str, Enum):
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    API_RATE_LIMIT = "API_RATE_LIMIT"
    INSUFFICIENT_BUDGET = "INSUFFICIENT_BUDGET"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    ENVIRONMENT_CHANGE = "ENVIRONMENT_CHANGE"
    MODEL_FAILURE = "MODEL_FAILURE"
    UNKNOWN = "UNKNOWN"


class FailureClassifier:
    """Classifies raw Python execution exceptions into planning failure categories."""

    @staticmethod
    def classify(error: Exception) -> FailureCategory:
        """Determines semantic failure type of a given exception."""
        err_msg = str(error).lower()

        if isinstance(error, (ExecTimeoutError, socket.timeout)) or "timeout" in err_msg:
            return FailureCategory.NETWORK_TIMEOUT
        
        if isinstance(error, ExecPermissionDenied) or "permission" in err_msg or "denied" in err_msg:
            return FailureCategory.PERMISSION_DENIED

        
        if isinstance(error, ValidationError):
            if "budget" in err_msg:
                return FailureCategory.INSUFFICIENT_BUDGET
            return FailureCategory.POLICY_VIOLATION

        if "rate limit" in err_msg or "429" in err_msg:
            return FailureCategory.API_RATE_LIMIT

        if "exhaust" in err_msg or "memory" in err_msg or "disk" in err_msg:
            return FailureCategory.RESOURCE_EXHAUSTION


        if "dependency" in err_msg:
            return FailureCategory.DEPENDENCY_FAILURE

        return FailureCategory.UNKNOWN
