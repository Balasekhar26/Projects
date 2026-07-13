from __future__ import annotations

import sys
import subprocess
import json
import time
import tempfile
import os
import uuid
from pathlib import Path
from typing import Any, Dict
import psutil


def allocate_sandbox_and_run(skill: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """Runs a registered skill inside an isolated Python subprocess sandbox with resource limits."""
    entrypoint = skill["entrypoint"]
    timeout = skill.get("timeout_seconds", 30)
    max_memory_mb = skill.get("max_memory_mb")
    allow_network = skill.get("allow_network", False)
    allowed_paths = skill.get("allowed_paths", [])

    # Locate entrypoint file
    entrypoint_path = Path(entrypoint)
    if not entrypoint_path.exists():
        # Fallback to absolute workspace location if relative does not exist
        from backend.core.config import load_config
        config = load_config()
        entrypoint_path = Path(config.workspace_dir) / entrypoint

    if not entrypoint_path.exists():
        return {
            "status": "error",
            "error_message": f"Entrypoint script '{entrypoint}' not found.",
        }

    # Build the bootstrapper script dynamically
    # It injects interceptors into the target interpreter context
    bootstrap_code = f"""import builtins
import sys
import os
import socket
import json

# 1. Network restriction
if not {allow_network}:
    def blocked_socket(*args, **kwargs):
        raise PermissionError("Network access is disabled within this sandbox.")
    socket.socket = blocked_socket
    socket.getaddrinfo = blocked_socket

# 2. Filesystem restrictions
ALLOWED_PATHS = {json.dumps(allowed_paths)}
def check_path_allowed(path):
    if not ALLOWED_PATHS:
        return  # If none specified, allow
    try:
        abs_path = os.path.abspath(path)
        is_windows = os.name == 'nt'
        for allowed in ALLOWED_PATHS:
            allowed_abs = os.path.abspath(allowed)
            if is_windows:
                if abs_path.lower().startswith(allowed_abs.lower()):
                    return
            else:
                if abs_path.startswith(allowed_abs):
                    return
        raise PermissionError(f"Access to path '{{path}}' is blocked outside sandbox boundaries.")
    except Exception as e:
        raise PermissionError(f"Access to path '{{path}}' is denied: {{str(e)}}")

original_open = builtins.open
def sandboxed_open(file, *args, **kwargs):
    check_path_allowed(file)
    return original_open(file, *args, **kwargs)
builtins.open = sandboxed_open

# Intercept other dangerous file modules
try:
    import shutil
    original_copy = shutil.copy
    def sandboxed_copy(src, dst, *args, **kwargs):
        check_path_allowed(src)
        check_path_allowed(dst)
        return original_copy(src, dst, *args, **kwargs)
    shutil.copy = sandboxed_copy
except ImportError:
    pass

# Update sys.argv to simulate direct execution
# argv[0] = entrypoint path, argv[1] = JSON args (matching probe convention)
sys.argv = [{json.dumps(str(entrypoint_path.resolve()))}, sys.argv[2]]
with original_open({json.dumps(str(entrypoint_path.resolve()))}, 'r', encoding='utf-8') as f:
    code = f.read()
exec(code, {{"__name__": "__main__", "__file__": {json.dumps(str(entrypoint_path.resolve()))}}})
"""

    # Write wrapper to temporary directory
    temp_dir = tempfile.gettempdir()
    temp_wrapper_path = os.path.join(temp_dir, f"sandbox_wrapper_{uuid.uuid4().hex}.py")
    
    with open(temp_wrapper_path, "w", encoding="utf-8") as f:
        f.write(bootstrap_code)

    try:
        # Start child process in restricted environment
        # Strip env variables except minimal PATH
        clean_env = {"PATH": os.environ.get("PATH", "")}
        process = subprocess.Popen(
            [sys.executable, temp_wrapper_path, str(entrypoint_path.resolve()), json.dumps(args)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=clean_env,
        )

        start_time = time.time()
        p = psutil.Process(process.pid)
        memory_limit_exceeded = False

        while process.poll() is None:
            # 1. Timeout Check
            if time.time() - start_time > timeout:
                process.kill()
                return {
                    "status": "error",
                    "error_message": f"Sandbox execution timed out after {timeout} seconds.",
                }

            # 2. Memory Limit Check
            if max_memory_mb:
                try:
                    total_mem = p.memory_info().rss
                    # Sum memory of any spawned child processes
                    for child in p.children(recursive=True):
                        total_mem += child.memory_info().rss
                    
                    if total_mem > max_memory_mb * 1024 * 1024:
                        memory_limit_exceeded = True
                        process.kill()
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            time.sleep(0.05)

        stdout, stderr = process.communicate()

        if memory_limit_exceeded:
            return {
                "status": "error",
                "error_message": f"Sandbox execution terminated: memory limit exceeded ({max_memory_mb} MB limit).",
                "stdout": stdout,
                "stderr": stderr,
            }

        if process.returncode != 0:
            return {
                "status": "error",
                "error_message": f"Sandbox execution exited with code {process.returncode}.",
                "stdout": stdout,
                "stderr": stderr,
            }

        # Parse return payload from stdout
        try:
            output_data = json.loads(stdout.strip())
            return {
                "status": "success",
                "result": output_data,
                "stdout": stdout,
            }
        except Exception:
            return {
                "status": "success",
                "result": stdout.strip(),
                "stdout": stdout,
            }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Sandbox failed to execute: {str(e)}",
        }
    finally:
        # Clean up wrapper
        try:
            if os.path.exists(temp_wrapper_path):
                os.remove(temp_wrapper_path)
        except Exception:
            pass
