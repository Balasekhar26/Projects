"""Unit tests for Program 20.0: Containerized Sandbox Runtime.

Validates filesystem policies, network isolations, resource quotas, sandbox management execution,
and OS-level fallback safeguards.
"""
from __future__ import annotations

import subprocess
import pytest
from unittest.mock import MagicMock, patch

from backend.core.sandbox.filesystem_policy import FilesystemPolicy
from backend.core.sandbox.network_policy import NetworkPolicy
from backend.core.sandbox.resource_limiter import ResourceLimiter
from backend.core.sandbox.sandbox_manager import SandboxManager
from backend.core.sandbox.sandbox_audit import SandboxAudit
from backend.core.sandbox_runtime import SandboxRuntime


# ── 1. Filesystem Mount Policy Tests ──────────────────────────────────────────

class TestFilesystemPolicy:
    def test_browser_class_readonly(self):
        flags = FilesystemPolicy.get_mount_flags("BROWSER", is_mutating=True, host_ws_dir="/ws")
        # Browser must be strictly read-only even if trying to mutate
        assert "-v" in flags
        assert "/ws:/workspace:ro" in flags

    def test_python_mutating_readwrite(self):
        flags = FilesystemPolicy.get_mount_flags("PYTHON", is_mutating=True, host_ws_dir="/ws")
        assert "/ws:/workspace:rw" in flags

    def test_python_non_mutating_readonly(self):
        flags = FilesystemPolicy.get_mount_flags("PYTHON", is_mutating=False, host_ws_dir="/ws")
        assert "/ws:/workspace:ro" in flags


# ── 2. Network Isolation Policy Tests ─────────────────────────────────────────

class TestNetworkPolicy:
    def test_python_offline_isolation(self):
        flags = NetworkPolicy.get_network_flags("PYTHON")
        assert flags == ["--network", "none"]

    def test_browser_online_bridge(self):
        flags = NetworkPolicy.get_network_flags("BROWSER")
        assert flags == ["--network", "bridge"]


# ── 3. Resource Quotas Tests ──────────────────────────────────────────────────

class TestResourceLimiter:
    def test_python_profile_limits(self):
        flags = ResourceLimiter.get_docker_flags("PYTHON")
        assert "--memory=512m" in flags
        assert "--cpu-shares=512" in flags
        assert "--pids-limit=64" in flags

    def test_build_profile_limits(self):
        flags = ResourceLimiter.get_docker_flags("BUILD")
        assert "--memory=2048m" in flags
        assert "--cpu-shares=1024" in flags


# ── 4. Sandbox Manager Logic Tests ────────────────────────────────────────────

class TestSandboxManager:
    def test_determine_class_and_mutating(self):
        # pytest -> PYTHON class, non-mutating
        cls_p, mut_p = SandboxManager.determine_class_and_mutating(["pytest", "backend/tests"])
        assert cls_p == "PYTHON"
        assert mut_p is False

        # npm install -> BUILD class, mutating
        cls_b, mut_b = SandboxManager.determine_class_and_mutating(["npm", "install", "react"])
        assert cls_b == "BUILD"
        assert mut_b is True

    @patch("subprocess.run")
    def test_manager_container_run_success(self, mock_run):
        # Setup mock CompletedProcess
        mock_completed = MagicMock()
        mock_completed.returncode = 0
        mock_completed.stdout = "Success output"
        mock_completed.stderr = ""
        mock_run.return_value = mock_completed

        cmd = ["pytest", "test_file.py"]
        res = SandboxManager.run_in_sandbox(cmd, safe_env={})

        assert res.returncode == 0
        assert res.stdout == "Success output"
        assert mock_run.called
        # Verify docker flags
        args = mock_run.call_args[0][0]
        assert "docker" in args
        assert "run" in args
        assert "python:3.11-slim" in args


# ── 5. Runtime Delegation & OS Fallback Tests ─────────────────────────────────

class TestSandboxRuntimeDelegation:
    @patch("backend.core.sandbox_runtime.SandboxRuntime._detect_container_engine", return_value="docker")
    @patch("backend.core.sandbox.sandbox_manager.SandboxManager.run_in_sandbox")
    def test_runtime_delegates_to_manager(self, mock_sandbox_run, mock_detect):
        mock_completed = MagicMock()
        mock_completed.returncode = 0
        mock_sandbox_run.return_value = mock_completed

        res = SandboxRuntime.run_command(["python", "-c", "print(1)"])
        assert res.returncode == 0
        mock_sandbox_run.assert_called_once()

    @patch("backend.core.sandbox_runtime.SandboxRuntime._detect_container_engine", return_value="docker")
    @patch("backend.core.sandbox.sandbox_manager.SandboxManager.run_in_sandbox", side_effect=RuntimeError("Docker dead"))
    @patch("backend.core.sandbox_runtime.SandboxRuntime._run_os_sandbox")
    def test_runtime_falls_back_to_os_on_exception(self, mock_os_run, mock_sandbox_run, mock_detect):
        mock_completed = MagicMock()
        mock_completed.returncode = 0
        mock_os_run.return_value = mock_completed

        res = SandboxRuntime.run_command(["python", "-c", "print(1)"])
        assert res.returncode == 0
        mock_sandbox_run.assert_called_once()
        mock_os_run.assert_called_once()
