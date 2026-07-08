"""Tool Permissions Manager (Program 11).

Defines authorization policies and gates for executing system tools.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from backend.core.execution.tool_models import ToolDefinition

logger = logging.getLogger(__name__)


class PermissionManager:
    """Verifies that running agents carry the required permission privileges."""

    _instance: Optional[PermissionManager] = None

    def __init__(self) -> None:
        # Default authorized capabilities list
        self.authorized_permissions = ["read", "write", "execute"]

    @classmethod
    def get_instance(cls) -> PermissionManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def verify_permissions(self, tool: ToolDefinition) -> bool:
        """Verifies if the registry permissions contain all required tool permissions."""
        for p in tool.required_permissions:
            if p == "require_approval":
                continue
            if p not in self.authorized_permissions:
                logger.warning(
                    "Permission check failed for tool %s: missing privilege %s",
                    tool.name, p
                )
                return False
        return True

    def grant_permission(self, permission: str) -> None:
        if permission not in self.authorized_permissions:
            self.authorized_permissions.append(permission)

    def revoke_permission(self, permission: str) -> None:
        if permission in self.authorized_permissions:
            self.authorized_permissions.remove(permission)
