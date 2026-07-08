"""Sandbox Manager (Program 20.0).

Central coordinator routing commands across sandbox classes, volume policies, and limits.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from backend.core.sandbox.filesystem_policy import FilesystemPolicy
from backend.core.sandbox.network_policy import NetworkPolicy
from backend.core.sandbox.resource_limiter import ResourceLimiter
from backend.core.sandbox.sandbox_audit import SandboxAudit

logger = logging.getLogger(__name__)


class SandboxManager:
    """Orchestrates container lifecycle, maps workspace directories, and limits CPU/RAM."""

    @classmethod
    def determine_class_and_mutating(cls, cmd: List[str]) -> tuple[str, bool]:
        """Classifies command vector to select sandbox class and read-write mode."""
        cmd_str = " ".join(str(c) for c in cmd).lower()
        
        # 1. Class Selection
        if "pytest" in cmd_str or "unittest" in cmd_str:
            sandbox_class = "PYTHON"
        elif "curl" in cmd_str or "wget" in cmd_str or "pip" in cmd_str:
            sandbox_class = "RESEARCH"
        elif "npm" in cmd_str or "build" in cmd_str or "compile" in cmd_str:
            sandbox_class = "BUILD"
        elif "pdf" in cmd_str or "docx" in cmd_str or "convert" in cmd_str:
            sandbox_class = "FILE"
        else:
            sandbox_class = "PYTHON"

        # 2. Mutating Checks
        mutating_indicators = ["write", "delete", "rm", "create", "mkdir", "patch", "install"]
        is_mutating = any(ind in cmd_str for ind in mutating_indicators)

        return sandbox_class, is_mutating

    @classmethod
    def run_in_sandbox(
        cls,
        cmd: List[str],
        timeout: float = 15.0,
        allow_network: Optional[bool] = None,
        cwd: Optional[str] = None,
        safe_env: Optional[Dict[str, str]] = None
    ) -> subprocess.CompletedProcess:
        """Executes command inside Docker container according to resolved policies.

        Throws exception on Docker daemon failure to trigger OS fallback.
        """
        sandbox_class, is_mutating = cls.determine_class_and_mutating(cmd)
        
        # Resolve Workspace Dir
        try:
            from backend.core.config import load_config
            config = load_config()
            ws_dir = str(config.workspace_dir)
        except Exception:
            ws_dir = os.getcwd()

        # Compile Docker CLI parameters
        container_flags = [
            "docker", "run", "--rm",
            "-w", "/workspace"
        ]

        # 1. Mount Configuration
        container_flags.extend(FilesystemPolicy.get_mount_flags(sandbox_class, is_mutating, ws_dir))

        # 2. Network Isolation
        if allow_network is False:
            container_flags.extend(["--network", "none"])
        elif allow_network is True:
            container_flags.extend(["--network", "bridge"])
        else:
            container_flags.extend(NetworkPolicy.get_network_flags(sandbox_class))

        # 3. CPU/Memory Caps
        container_flags.extend(ResourceLimiter.get_docker_flags(sandbox_class))

        # Translate absolute workspace paths in arguments
        resolved_cmd = []
        for arg in cmd:
            if isinstance(arg, str):
                if arg.startswith(ws_dir):
                    rel_path = os.path.relpath(arg, ws_dir)
                    resolved_cmd.append(os.path.join("/workspace", rel_path))
                elif arg == sys.executable:
                    resolved_cmd.append("python")
                elif arg.endswith("/pytest") and "ai_system_env" in arg:
                    resolved_cmd.append("pytest")
                else:
                    resolved_cmd.append(arg)
            else:
                resolved_cmd.append(arg)

        # Append default image tag and command
        image = "python:3.11-slim"
        container_cmd = container_flags + [image] + resolved_cmd

        # Track execution metrics
        start_time = time.perf_counter()
        
        # Execute container subprocess
        res = subprocess.run(
            container_cmd,
            env=safe_env,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # Audit and record run details
        limits_summary = ResourceLimiter.PROFILES.get(sandbox_class, {})
        SandboxAudit.record_run(sandbox_class, cmd, res.returncode, duration_ms, limits_summary)

        # Throw exception if container daemon failed to pull/launch (exit code 125 or daemon errors)
        if (res.returncode == 125 or 
            "Unable to find image" in res.stderr or 
            "Error response from daemon" in res.stderr or 
            "error during connect" in res.stderr):
            raise RuntimeError(f"Docker Daemon run exception: {res.stderr}")

        return res
