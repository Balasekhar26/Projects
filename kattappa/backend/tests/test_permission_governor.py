"""Unit tests for Program 44.0: Permission and Safety Governor.

Verifies dynamic permission authorizations, policy path restraints, safety filters,
human approval triggers, and thread-local overrides.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from backend.core.governance import (
    PolicyEngine,
    SafetyMonitor,
    PermissionGovernor,
    SessionPermissionScope,
)


@pytest.fixture
def setup_governance():
    with tempfile.TemporaryDirectory() as tmp:
        # Policy Engine allowing only files inside temporary folder, and net blocked
        policy = PolicyEngine(
            allowed_tools={"read_file", "write_file", "shell_exec"},
            restricted_paths=[tmp],
            allow_network=False,
            require_approval_tools={"shell_exec"},
        )
        safety = SafetyMonitor()
        yield Path(tmp), policy, safety


# ── Permission Governor Tests ──────────────────────────────────────────────────

class TestPermissionGovernor:
    def test_authorize_action_success(self, setup_governance):
        tmp_dir, policy, safety = setup_governance
        
        target_file = tmp_dir / "test.txt"
        
        # 'coder' agent has CAP_FILE_READ and CAP_FILE_WRITE allowed
        allowed, detail = PermissionGovernor.authorize_action_request(
            agent_name="coder",
            tool_name="read_file",
            args={"path": str(target_file)},
            policy=policy,
            safety=safety,
        )
        assert allowed is True
        assert detail == "AUTHORIZED"

    def test_blocked_by_capability_registry(self, setup_governance):
        tmp_dir, policy, safety = setup_governance
        target_file = tmp_dir / "test.txt"
        
        # 'voice' agent is denied CAP_FILE_WRITE (for write_file)
        allowed, detail = PermissionGovernor.authorize_action_request(
            agent_name="voice",
            tool_name="write_file",
            args={"path": str(target_file)},
            policy=policy,
            safety=safety,
        )
        assert allowed is False
        assert detail == "BLOCKED_BY_CAPABILITY_REGISTRY"

    def test_blocked_by_policy_restricted_paths(self, setup_governance):
        tmp_dir, policy, safety = setup_governance
        
        # File path outside restricted paths bounds
        target_file = "/etc/passwd"
        
        allowed, detail = PermissionGovernor.authorize_action_request(
            agent_name="coder",
            tool_name="read_file",
            args={"path": target_file},
            policy=policy,
            safety=safety,
        )
        assert allowed is False
        assert detail == "BLOCKED_BY_POLICY"

    def test_blocked_by_safety_injection(self, setup_governance):
        tmp_dir, policy, safety = setup_governance
        
        # Command containing a forbidden format binary
        args = {"CommandLine": "rm -rf /test"}
        
        allowed, detail = PermissionGovernor.authorize_action_request(
            agent_name="coder",
            tool_name="shell_exec",
            args=args,
            policy=policy,
            safety=safety,
        )
        assert allowed is False
        assert detail == "BLOCKED_BY_SAFETY"

    def test_requires_user_approval(self, setup_governance):
        tmp_dir, policy, safety = setup_governance
        
        # Valid safe command, but shell_exec requires user approval in configuration
        args = {"CommandLine": "echo 'hello'"}
        
        allowed, detail = PermissionGovernor.authorize_action_request(
            agent_name="coder",
            tool_name="shell_exec",
            args=args,
            policy=policy,
            safety=safety,
        )
        assert allowed is False
        assert detail == "REQUIRES_APPROVAL"

    def test_session_permission_scope_elevation(self, setup_governance):
        tmp_dir, policy, safety = setup_governance
        target_file = tmp_dir / "test.txt"
        
        # By default, 'voice' agent cannot write files (CAP_FILE_WRITE is blocked)
        allowed, detail = PermissionGovernor.authorize_action_request(
            agent_name="voice",
            tool_name="write_file",
            args={"path": str(target_file)},
            policy=policy,
            safety=safety,
        )
        assert allowed is False
        assert detail == "BLOCKED_BY_CAPABILITY_REGISTRY"

        # Temporarily elevate the session allowed capabilities for the voice agent
        with SessionPermissionScope(agent_name="voice", allowed_capabilities={"CAP_FILE_WRITE"}):
            allowed_elevated, detail_elevated = PermissionGovernor.authorize_action_request(
                agent_name="voice",
                tool_name="write_file",
                args={"path": str(target_file)},
                policy=policy,
                safety=safety,
            )
            assert allowed_elevated is True
            assert detail_elevated == "AUTHORIZED"

        # Verification after exit -> scope falls back to normal limits (blocked)
        allowed_after, detail_after = PermissionGovernor.authorize_action_request(
            agent_name="voice",
            tool_name="write_file",
            args={"path": str(target_file)},
            policy=policy,
            safety=safety,
        )
        assert allowed_after is False
        assert detail_after == "BLOCKED_BY_CAPABILITY_REGISTRY"
