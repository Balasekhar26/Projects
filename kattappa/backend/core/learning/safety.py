"""Learning Safety Policy Filter Engine (Program 7).

Prevents automatic updates targeting sensitive credentials or authorization flags.
"""
from __future__ import annotations

from typing import Set
from backend.core.reflection.models import LearningCandidate

PROTECTED_VARIABLES: Set[str] = {
    "auth",
    "credentials",
    "permissions",
    "security_key",
    "access_token",
    "verify_permissions_preflight",
}


class SafetyPolicyEngine:
    """Enforces safety rules to quarantine dangerous parameter recommendations."""

    @staticmethod
    def is_safe_to_auto_apply(candidate: LearningCandidate) -> bool:
        """Determines if a candidate can bypass manual approval queues.

        Rejects candidates that attempt to adjust protected variables or have low confidence.
        """
        # 1. Low confidence updates require human check
        if candidate.confidence < 0.8:
            return False

        # 2. Check for protected parameters in proposed updates
        update_keys = candidate.proposed_update.keys()
        for key in update_keys:
            if key in PROTECTED_VARIABLES:
                return False

        return True
