"""Policy-Based Authorization Engine (Program 11.8).

Evaluates granular user execution policies (ALLOW, DENY, REQUIRE_APPROVAL).
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.core.execution.tool_models import ToolDefinition
from backend.core.execution.context import ExecutionContext

logger = logging.getLogger(__name__)


class PolicyEffect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class PolicyEngine:
    """Evaluates rules policies governing tool invocations permissions."""

    _instance: Optional[PolicyEngine] = None

    def __init__(self) -> None:
        # Default policy definitions
        self.deny_rules: List[str] = ["system_shutdown", "root_escalation"]
        self.approval_rules: List[str] = ["secrets_deletion", "delete_keys"]

    @classmethod
    def get_instance(cls) -> PolicyEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def evaluate(self, tool: ToolDefinition, context: ExecutionContext) -> PolicyEffect:
        """Determines authorization outcome for the tool execution request."""
        # 1. Deny rules pre-flight
        if tool.name in self.deny_rules:
            logger.warning("Policy DENIED execution for tool: %s", tool.name)
            return PolicyEffect.DENY

        # 2. Check user role validation (e.g. restrict guests from writes)
        user_role = context.metadata.get("user_role", "guest")
        if "write" in tool.required_permissions and user_role == "guest":
            logger.warning("Policy DENIED write execution for guest user: %s", context.user_id)
            return PolicyEffect.DENY

        # 3. Manual confirmation approval rules
        if tool.name in self.approval_rules or "require_approval" in tool.required_permissions:
            logger.info("Policy REQUIRE_APPROVAL for tool: %s", tool.name)
            return PolicyEffect.REQUIRE_APPROVAL

        return PolicyEffect.ALLOW
