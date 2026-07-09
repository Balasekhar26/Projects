"""Unit tests for Program 48.0B: Execution Sandbox Runtime.

Verifies unified tool execution, permission gates validation, secret scrubbing,
audit logging, and transactional workflows.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
import pytest

from backend.core.governance import (
    PolicyEngine,
    SafetyMonitor,
    AuditLedger,
    PermissionGovernor,
)
from backend.core.sandbox import ExecutionSandbox
from backend.core.secret_broker import SecretBroker


@pytest.fixture
def setup_unified_runtime():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        
        # Policy Engine restricted to temp folder and allow specific tools
        policy = PolicyEngine(
            allowed_tools={"shell_exec", "python_exec", "read_file"},
            restricted_paths=[tmp],
            allow_network=True,
            require_approval_tools=set(),
        )
        safety = SafetyMonitor()
        
        # Isolated Audit ledger
        ledger_path = tmp_path / "audit.json"
        ledger = AuditLedger(ledger_file=ledger_path)
        
        yield tmp_path, policy, safety, ledger


# ── Execution Sandbox Runtime Tests ───────────────────────────────────────────

class TestExecutionSandboxRuntime:
    def test_execute_shell_and_audit_log(self, setup_unified_runtime):
        tmp_path, policy, safety, ledger = setup_unified_runtime
        
        # 1. Execute a valid command
        # On Windows: cmd /c "echo success"
        # On Unix: sh -c "echo success"
        res = ExecutionSandbox.execute_shell(
            command="echo success",
            agent_name="coder",
            timeout=5.0,
            cwd=str(tmp_path),
            policy=policy,
            safety=safety,
            ledger=ledger,
        )

        assert res["returncode"] == 0
        assert "success" in res["stdout"].strip().lower()
        
        # Verify both request approval and outcome completion are saved to ledger
        logs = ledger.load_audit_entries()
        assert len(logs) == 2
        assert logs[0]["decision"] == "APPROVED"
        assert logs[1]["decision"] == "COMPLETED"

    def test_execute_blocked_by_governance(self, setup_unified_runtime):
        tmp_path, policy, safety, ledger = setup_unified_runtime
        
        # Tool 'write_file' is not in PolicyEngine allowed tools list
        res = ExecutionSandbox.execute_tool(
            tool_name="write_file",
            args={"path": str(tmp_path / "test.txt")},
            agent_name="coder",
            cwd=str(tmp_path),
            policy=policy,
            safety=safety,
            ledger=ledger,
        )

        assert res["returncode"] == -1
        assert "blocked" in res["stderr"].lower()
        
        # Verify blocked attempt logged to audit ledger
        logs = ledger.load_audit_entries()
        assert len(logs) == 1
        assert logs[0]["decision"] == "BLOCKED"
        assert "write_file" in logs[0]["tool"]

    def test_secret_scrubbing(self, setup_unified_runtime):
        tmp_path, policy, safety, ledger = setup_unified_runtime
        
        # Register a mock secret in environmental variables
        os.environ["API_KEY_SECRET"] = "super-secret-token"
        
        # Use python execution to print all environment variables
        code = "import os; print(os.environ.get('API_KEY_SECRET', 'SCRUBBED'))"
        res = ExecutionSandbox.execute_python(
            code=code,
            agent_name="coder",
            timeout=5.0,
            cwd=str(tmp_path),
            policy=policy,
            safety=safety,
            ledger=ledger,
        )

        assert res["returncode"] == 0
        assert "scrubbed" in res["stdout"].strip().lower()
        assert "super-secret-token" not in res["stdout"]

        # Cleanup mock env
        os.environ.pop("API_KEY_SECRET", None)

    def test_execute_workflow_transaction_rollback(self, setup_unified_runtime):
        tmp_path, policy, safety, ledger = setup_unified_runtime
        
        # Initial file state
        base_file = tmp_path / "base.txt"
        base_file.write_text("initial")

        # Workflow steps:
        # Step 1: Writes 'stage1' to a file (valid success step)
        # Step 2: Executes a failing python command (will fail and trigger rollback)
        steps = [
            {
                "tool": "shell_exec",
                "args": {"CommandLine": f"echo stage1 > {tmp_path}/stage1.txt"},
                "timeout": 5.0,
            },
            {
                "tool": "python_exec",
                "args": {"code": "import sys; sys.exit(1)"},
                "timeout": 5.0,
            }
        ]

        res = ExecutionSandbox.execute_workflow(
            steps=steps,
            agent_name="coder",
            cwd=str(tmp_path),
            policy=policy,
            safety=safety,
            ledger=ledger,
        )

        assert res["returncode"] != 0
        assert res["rolled_back"] is True
        
        # All changes made during the workflow must be rolled back!
        assert not (tmp_path / "stage1.txt").exists()
        assert base_file.read_text() == "initial"
