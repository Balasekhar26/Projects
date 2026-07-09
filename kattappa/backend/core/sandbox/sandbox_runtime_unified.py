"""Execution Sandbox Runtime (Program 48.0B).

Coordinates tool authorization gates, environmental secret scrubbing, local
sandboxed executions (with timeouts/rollbacks), and audit trail records.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.governance import (
    PolicyEngine,
    SafetyMonitor,
    PermissionGovernor,
    AuditLedger,
)
from backend.core.sandbox.local_sandbox import LocalExecutionSandbox
from backend.core.secret_broker import SecretBroker


class ExecutionSandbox:
    """Unified runtime coordinating sandbox executions, policies, secrets, and logs."""

    @classmethod
    def execute_tool(
        cls,
        tool_name: str,
        args: Dict[str, Any],
        agent_name: str,
        timeout: float = 15.0,
        cwd: Optional[str] = None,
        enable_rollback: bool = True,
        policy: Optional[PolicyEngine] = None,
        safety: Optional[SafetyMonitor] = None,
        ledger: Optional[AuditLedger] = None,
    ) -> Dict[str, Any]:
        """Runs tool checking authorization permissions, logs actions, and executes in sandbox."""
        # 1. Resolve default governance components
        target_cwd = cwd or os.getcwd()
        active_policy = policy or PolicyEngine(
            allowed_tools={
                "read_file",
                "write_file",
                "delete_file",
                "shell_exec",
                "python_exec",
            },
            restricted_paths=[target_cwd],
            allow_network=True,
            require_approval_tools=set(),
        )
        active_safety = safety or SafetyMonitor()
        active_ledger = ledger or AuditLedger()

        # 2. Check authorization rules
        allowed, detail = PermissionGovernor.authorize_action_request(
            agent_name=agent_name,
            tool_name=tool_name,
            args=args,
            policy=active_policy,
            safety=active_safety,
        )

        # 3. Log request to Audit Ledger
        active_ledger.log_audit_entry(
            agent=agent_name,
            tool=tool_name,
            arguments=args,
            decision="APPROVED" if allowed else "BLOCKED",
            reason=detail,
        )

        if not allowed:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Execution blocked by governor: {detail}",
                "rolled_back": False,
            }

        # 4. Resolve sandboxed command line vector
        if tool_name == "shell_exec":
            cmd_line = args.get("CommandLine") or args.get("command") or ""
            if sys.platform == "win32":
                cmd = ["cmd", "/c", cmd_line]
            else:
                cmd = ["sh", "-c", cmd_line]
        elif tool_name == "python_exec":
            code = args.get("code") or ""
            cmd = [sys.executable, "-c", code]
        else:
            # Safe generic command fallback mapping
            cmd_line = args.get("CommandLine") or args.get("command") or ""
            cmd = [cmd_line] if cmd_line else [tool_name]

        # 5. Scrub environment variables
        base_env = os.environ.copy()
        safe_env = SecretBroker.scrub_env(base_env)

        # 6. Execute inside local sandbox (handling timeouts and file backups)
        # Note: LocalExecutionSandbox requires passing cmd vector list, env is inherited but we patch safe_env
        original_env = os.environ.copy()
        os.environ.clear()
        os.environ.update(safe_env)
        try:
            res = LocalExecutionSandbox.execute_sandboxed_command(
                cmd=cmd,
                timeout=timeout,
                cwd=target_cwd,
                enable_rollback=enable_rollback,
            )
        finally:
            os.environ.clear()
            os.environ.update(original_env)

        # 7. Record final results to ledger
        active_ledger.log_audit_entry(
            agent=agent_name,
            tool=tool_name,
            arguments=args,
            decision="COMPLETED" if res["returncode"] == 0 else "FAILED",
            reason=f"Exit code: {res['returncode']}. Rolled back: {res['rolled_back']}",
        )

        return res

    @classmethod
    def execute_shell(
        cls,
        command: str,
        agent_name: str,
        timeout: float = 15.0,
        cwd: Optional[str] = None,
        policy: Optional[PolicyEngine] = None,
        safety: Optional[SafetyMonitor] = None,
        ledger: Optional[AuditLedger] = None,
    ) -> Dict[str, Any]:
        """Wrapper executing generic shell command lines inside sandbox runtime."""
        return cls.execute_tool(
            tool_name="shell_exec",
            args={"CommandLine": command},
            agent_name=agent_name,
            timeout=timeout,
            cwd=cwd,
            enable_rollback=True,
            policy=policy,
            safety=safety,
            ledger=ledger,
        )

    @classmethod
    def execute_python(
        cls,
        code: str,
        agent_name: str,
        timeout: float = 15.0,
        cwd: Optional[str] = None,
        policy: Optional[PolicyEngine] = None,
        safety: Optional[SafetyMonitor] = None,
        ledger: Optional[AuditLedger] = None,
    ) -> Dict[str, Any]:
        """Wrapper executing Python script payloads inside sandbox runtime."""
        return cls.execute_tool(
            tool_name="python_exec",
            args={"code": code},
            agent_name=agent_name,
            timeout=timeout,
            cwd=cwd,
            enable_rollback=True,
            policy=policy,
            safety=safety,
            ledger=ledger,
        )

    @classmethod
    def execute_workflow(
        cls,
        steps: List[Dict[str, Any]],
        agent_name: str,
        cwd: Optional[str] = None,
        policy: Optional[PolicyEngine] = None,
        safety: Optional[SafetyMonitor] = None,
        ledger: Optional[AuditLedger] = None,
    ) -> Dict[str, Any]:
        """Executes a list of steps sequentially, rolling back target workspace folder on failure."""
        target_cwd = cwd or os.getcwd()
        snap_dir = None
        rolled_back = False

        # Create transactional snapshot backup of the directory before workflow execution
        if Path(target_cwd).exists():
            try:
                snap_dir = LocalExecutionSandbox.create_snapshot(target_cwd)
            except Exception:
                pass

        try:
            workflow_success = True
            last_res = {"returncode": 0, "stdout": "", "stderr": "", "rolled_back": False}

            for idx, step in enumerate(steps):
                tool = step.get("tool") or "shell_exec"
                args = step.get("args") or {}
                timeout = step.get("timeout") or 15.0

                res = cls.execute_tool(
                    tool_name=tool,
                    args=args,
                    agent_name=agent_name,
                    timeout=timeout,
                    cwd=target_cwd,
                    enable_rollback=False,  # Managed at the workflow level instead
                    policy=policy,
                    safety=safety,
                    ledger=ledger,
                )
                last_res = res
                if res["returncode"] != 0:
                    workflow_success = False
                    break

            if not workflow_success:
                if snap_dir and Path(snap_dir).exists():
                    LocalExecutionSandbox.restore_snapshot(snap_dir, target_cwd)
                    rolled_back = True
                last_res["rolled_back"] = rolled_back
                return last_res

            return last_res

        finally:
            if snap_dir:
                try:
                    import shutil
                    shutil.rmtree(Path(snap_dir).parent)
                except Exception:
                    pass
        return last_res
