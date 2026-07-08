"""Recovery Policies Engine (Program 12.4).
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, List, Set

from backend.core.planning.failure_classifier import FailureCategory

logger = logging.getLogger(__name__)


class RecoveryAction(str, Enum):
    RETRY = "RETRY"
    SUBSTITUTE_TOOL = "SUBSTITUTE_TOOL"
    REBUILD_SUBTREE = "REBUILD_SUBTREE"
    ABORT = "ABORT"
    ESCALATE = "ESCALATE"


class RecoveryPolicyEngine:
    """Evaluates categorized failures against limits, tabu lists, and escalation policy gates."""

    def __init__(self, max_attempts_per_node: int = 3) -> None:
        self.max_attempts_per_node = max_attempts_per_node
        self.attempts: Dict[str, int] = {}  # node_id -> retry count
        self.tabu_list: Set[str] = set()    # tabu tool/rule suggestions

    def get_recovery_action(self, node_id: str, category: FailureCategory) -> RecoveryAction:
        """Determines the appropriate recovery step based on failure category and attempt history."""
        # Safety limit: Policy violations abort immediately
        if category == FailureCategory.POLICY_VIOLATION:
            return RecoveryAction.ABORT

        # Permission errors require human escalation
        if category == FailureCategory.PERMISSION_DENIED:
            return RecoveryAction.ESCALATE

        # Budget exhaustion requires escalation
        if category == FailureCategory.INSUFFICIENT_BUDGET:
            return RecoveryAction.ESCALATE

        # Increment attempts counter
        current_attempts = self.attempts.get(node_id, 0) + 1
        self.attempts[node_id] = current_attempts

        # If we exceeded the recovery budget, escalate to user/operator
        if current_attempts > self.max_attempts_per_node:
            logger.warning("Recovery budget exhausted for node '%s'. Escalating...", node_id)
            return RecoveryAction.ESCALATE

        # Route action based on category
        if category in {FailureCategory.NETWORK_TIMEOUT, FailureCategory.API_RATE_LIMIT}:
            return RecoveryAction.RETRY

        if category in {FailureCategory.DEPENDENCY_FAILURE, FailureCategory.MODEL_FAILURE, FailureCategory.RESOURCE_EXHAUSTION}:
            return RecoveryAction.REBUILD_SUBTREE

        return RecoveryAction.SUBSTITUTE_TOOL

    def mark_tabu(self, resource_or_rule: str) -> None:
        """Adds a failed tool or rule to the tabu set to avoid oscillations."""
        self.tabu_list.add(resource_or_rule)

    def is_tabu(self, resource_or_rule: str) -> bool:
        return resource_or_rule in self.tabu_list

    def reset_node_attempts(self, node_id: str) -> None:
        if node_id in self.attempts:
            del self.attempts[node_id]
