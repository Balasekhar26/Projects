import os
import platform
import subprocess
import sys
from typing import List

from backend.core.secret_broker import SecretBroker

class SandboxRuntime:
    _container_engine = None

    @classmethod
    def _detect_container_engine(cls) -> str:
        if cls._container_engine is not None:
            return cls._container_engine
            
        # In test environments, allow manual mock overrides
        if os.getenv("KATTAPPA_ENV") == "test" and os.getenv("MOCK_CONTAINER_ENGINE"):
            cls._container_engine = os.getenv("MOCK_CONTAINER_ENGINE")
            return cls._container_engine

        # Try docker
        try:
            res = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0:
                cls._container_engine = "docker"
                return "docker"
        except Exception:
            pass
            
        # Try podman
        try:
            res = subprocess.run(["podman", "info"], capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0:
                cls._container_engine = "podman"
                return "podman"
        except Exception:
            pass
            
        cls._container_engine = "none"
        return "none"

    @classmethod
    def _run_os_sandbox(cls, cmd: List[str], timeout: float, allow_network: bool, cwd: str, safe_env: dict) -> subprocess.CompletedProcess:
        sandbox_cmd = cmd
        if platform.system().lower() == "darwin":
            if not allow_network:
                sandbox_profile = "(version 1)\n(allow default)\n(deny network*)"
                sandbox_cmd = ["sandbox-exec", "-p", sandbox_profile] + cmd
        elif platform.system().lower() == "linux":
            if not allow_network:
                try:
                    test_res = subprocess.run(["unshare", "--version"], capture_output=True)
                    if test_res.returncode == 0:
                        sandbox_cmd = ["unshare", "-n"] + cmd
                except Exception:
                    pass
                    
        return subprocess.run(
            sandbox_cmd,
            env=safe_env,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

    @classmethod
    def run_command(cls, cmd: List[str], timeout: float = 15.0, allow_network: bool = False, cwd: str = None) -> subprocess.CompletedProcess:
        """
        Executes a command under network-isolated sandbox environment.
        Scrubs secrets from the environment variables prior to launch.
        Uses container isolation (Docker/Podman) if available, with OS fallback.
        """
        # 1. Scrub environment variables
        base_env = os.environ.copy()
        safe_env = SecretBroker.scrub_env(base_env)
        
        # Add basic runtime configuration
        safe_env["KATTAPPA_ENV"] = os.getenv("KATTAPPA_ENV", "production")
        if "PATH" not in safe_env:
            safe_env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin"
        if "PYTHONPATH" not in safe_env:
            safe_env["PYTHONPATH"] = "."

        # Check if container engine is available
        engine = cls._detect_container_engine()
        if engine in ("docker", "podman"):
            try:
                from backend.core.config import load_config
                config = load_config()
                ws_dir = str(config.workspace_dir)
            except Exception:
                ws_dir = os.getcwd()
                
            # Docker run configuration
            container_cmd = [
                engine, "run", "--rm",
                "-v", f"{ws_dir}:/workspace",
                "-w", "/workspace"
            ]
            if not allow_network:
                container_cmd += ["--network", "none"]
                
            # Translate args
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
                    
            # Use python:3.11-slim as a fallback default base image
            container_cmd += ["python:3.11-slim"] + resolved_cmd
            
            try:
                # Spawn container
                res = subprocess.run(
                    container_cmd,
                    env=safe_env,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                
                # Check for container CLI/daemon startup failure
                # 125 is standard docker run failure. Check stderr for daemon/pull failures.
                if (res.returncode == 125 or 
                    "Unable to find image" in res.stderr or 
                    "Error response from daemon" in res.stderr or 
                    "error during connect" in res.stderr):
                    # Fallback to OS sandboxing
                    return cls._run_os_sandbox(cmd, timeout, allow_network, cwd, safe_env)
                    
                return res
            except Exception:
                # Fallback to OS sandboxing
                return cls._run_os_sandbox(cmd, timeout, allow_network, cwd, safe_env)
                
        # Default: run OS-level sandboxed subprocess
        return cls._run_os_sandbox(cmd, timeout, allow_network, cwd, safe_env)
