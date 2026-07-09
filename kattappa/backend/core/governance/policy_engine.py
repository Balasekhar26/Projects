"""Policy Engine (Program 28.0).

Enforces structural safety checks, tool permissions, and path boundaries
to decouple model reasoning from system execution privileges.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class PolicyViolationError(PermissionError):
    """Raised when an operation violates active governance policy boundaries."""


class PolicyEngine:
    """Evaluates proposed actions against strict allowlists, denylists, and path bounds."""

    def __init__(
        self,
        allowed_tools: Optional[Set[str]] = None,
        restricted_paths: Optional[List[str]] = None,
        allow_network: bool = False,
        require_approval_tools: Optional[Set[str]] = None,
    ) -> None:
        """Args:

            allowed_tools:          List of executable tool names. If None, all tools allowed.
            restricted_paths:       Paths which directory operations cannot traverse outside.
            allow_network:          Flag to toggle external network request tools.
            require_approval_tools: High-risk tools that force user intervention prompts.
        """
        self.allowed_tools = allowed_tools
        self.restricted_paths = [Path(p).resolve() for p in (restricted_paths or [])]
        self.allow_network = allow_network
        self.require_approval_tools = require_approval_tools or set()

    @classmethod
    def from_config_dict(cls, cfg: Dict[str, Any]) -> PolicyEngine:
        """Loads and parses policy engine constraints from a configuration dictionary."""
        tools = cfg.get("allowed_tools")
        allowed = set(tools) if tools is not None else None

        req_app = cfg.get("require_approval_tools")
        require_approval = set(req_app) if req_app is not None else set()

        return cls(
            allowed_tools=allowed,
            restricted_paths=cfg.get("restricted_paths"),
            allow_network=cfg.get("allow_network", False),
            require_approval_tools=require_approval,
        )

    def is_path_allowed(self, target_path: str | Path) -> bool:
        """Verifies that target_path resides within one of the allowed restricted paths."""
        if not self.restricted_paths:
            return True

        try:
            target = Path(target_path).resolve()
        except Exception:
            return False  # safe fallback on malformed paths

        for restricted in self.restricted_paths:
            # Check if target is a subdirectory of or matches the restricted boundary path
            if target == restricted or restricted in target.parents:
                return True

        return False

    def authorize_action(self, tool_name: str, args: Dict[str, Any]) -> bool:
        """Checks proposed tool execution bounds.

        Returns True if authorized, False if blocked by policies.
        """
        # 1. Allowlist tool name validation
        if self.allowed_tools is not None and tool_name not in self.allowed_tools:
            return False

        # 2. Network access validation
        if not self.allow_network and tool_name in ("web_fetch", "download_url", "http_request"):
            return False

        # 3. Path boundary checks for file operations
        if tool_name in ("file_read", "file_write", "read_file", "write_file", "delete_file"):
            path_val = args.get("path") or args.get("filepath") or args.get("TargetFile")
            if path_val and not self.is_path_allowed(path_val):
                return False

        return True

    def requires_user_approval(self, tool_name: str) -> bool:
        """Returns True if the tool name belongs to high-risk validation classes."""
        return tool_name in self.require_approval_tools
