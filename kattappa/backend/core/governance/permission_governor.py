"""Permission and Safety Governor (Program 44.0).

Coordinates checks from CapabilityRegistry, PolicyEngine (paths/network/allowlists),
and SafetyMonitor (injection/malicious binaries checks) into a unified validation workflow,
and manages thread-local permission elevations/restrictions.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.capability_registry import CapabilityRegistry, ACTION_CAPABILITY_MAP
from backend.core.governance.policy_engine import PolicyEngine
from backend.core.governance.safety_monitor import SafetyMonitor


class SessionPermissionScope:
    """Thread-local context manager enabling temporary permission overrides."""

    _local = threading.local()

    def __init__(
        self,
        agent_name: str,
        allowed_capabilities: Set[str],
        denied_capabilities: Optional[Set[str]] = None,
    ) -> None:
        self.agent_name = str(agent_name).lower().strip()
        self.allowed = set(allowed_capabilities)
        self.denied = set(denied_capabilities or [])

    def __enter__(self) -> SessionPermissionScope:
        if not hasattr(self._local, "stack"):
            self._local.stack = []
        self._local.stack.append((self.agent_name, self.allowed, self.denied))
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if hasattr(self._local, "stack") and self._local.stack:
            self._local.stack.pop()

    @classmethod
    def get_override(cls, agent_name: str, capability: str) -> Optional[bool]:
        """Looks up active thread-local permission overrides for a given capability."""
        if not hasattr(cls._local, "stack") or not cls._local.stack:
            return None
        
        agent_clean = str(agent_name).lower().strip()
        # Traverse overrides stack backwards (most recent first)
        for agent, allowed, denied in reversed(cls._local.stack):
            if agent == agent_clean:
                if capability in denied:
                    return False
                if capability in allowed:
                    return True
        return None


class PermissionGovernor:
    """Orchestrates comprehensive safety and permission evaluations."""

    @classmethod
    def authorize_action_request(
        cls,
        agent_name: str,
        tool_name: str,
        args: Dict[str, Any],
        policy: PolicyEngine,
        safety: SafetyMonitor,
    ) -> Tuple[bool, str]:
        """Runs the action request through Capability checks, Policy rules, and Safety filters."""
        # 1. Look up matching capability requirements
        # e.g., mapping edit_file/file_write -> CAP_FILE_WRITE. Match case insensitively
        action_key = tool_name.upper().strip()
        capability = ACTION_CAPABILITY_MAP.get(action_key)
        
        # Fallback helper lookup if not exact match (e.g. file_read -> READ_FILE)
        if not capability:
            for k, cap in ACTION_CAPABILITY_MAP.items():
                if k in action_key or action_key in k:
                    capability = cap
                    break
        
        # Default safety fallback capability if still unknown
        if not capability:
            capability = "CAP_TERMINAL_EXECUTE"

        # 2. Check capability registry (including thread local scopes)
        if not CapabilityRegistry.is_capability_allowed(agent_name, capability):
            return False, "BLOCKED_BY_CAPABILITY_REGISTRY"

        # 3. Check Policy Engine allowlists, network toggles, and path restrictions
        if not policy.authorize_action(tool_name, args):
            return False, "BLOCKED_BY_POLICY"

        # 4. Check Safety command injection filters and forbidden binary checks
        if not safety.inspect_action(tool_name, args):
            return False, "BLOCKED_BY_SAFETY"

        # 5. Check user validation triggers
        if policy.requires_user_approval(tool_name):
            return False, "REQUIRES_APPROVAL"

        return True, "AUTHORIZED"
