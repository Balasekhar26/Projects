"""Local Execution Sandbox (Program 45.0).

Provides local file isolation via copy-on-write snapshots, enforces execution
limits (timeouts), cleans process trees recursively on Windows and Unix,
and rolls back modified folder states on failures.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LocalExecutionSandbox:
    """Manages isolated execution spaces, local snapshots, process groups, and rollbacks."""

    @classmethod
    def create_snapshot(cls, src_dir: str | Path) -> str:
        """Copies target workspace directory to a temporary backup path, ignoring system/meta dirs."""
        src_path = Path(src_dir).resolve()
        # Use project-local sandbox root from central runtime_paths authority
        from backend.core.runtime_paths import get_sandbox_root
        sandbox_root = get_sandbox_root()
        snap_dir = sandbox_root / f"kattappa_sandbox_snap_{uuid.uuid4().hex[:8]}"
        snap_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = str(snap_dir)
        
        ignore_func = shutil.ignore_patterns(
            "ai_system_env", ".git", ".pytest_cache", "__pycache__", ".vscode", ".agents"
        )
        shutil.copytree(src_path, Path(temp_dir) / "backup", ignore=ignore_func, dirs_exist_ok=True)
        return str(Path(temp_dir) / "backup")

    @classmethod
    def restore_snapshot(cls, snapshot_dir: str | Path, dest_dir: str | Path) -> None:
        """Restores target folder contents back to snapshot state, keeping system/meta dirs intact."""
        dest_path = Path(dest_dir).resolve()
        snap_path = Path(snapshot_dir).resolve()

        protected = {"ai_system_env", ".git", ".pytest_cache", "__pycache__", ".vscode", ".agents"}
        if dest_path.exists():
            for item in dest_path.iterdir():
                if item.name in protected:
                    continue
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception:
                    pass
        dest_path.mkdir(parents=True, exist_ok=True)

        # Restore from snap backup folder
        shutil.copytree(snap_path, dest_path, dirs_exist_ok=True)

    @classmethod
    def cleanup_process_tree(cls, pid: int) -> None:
        """Kills the target process and all child processes recursively."""
        if sys.platform == "win32":
            # Force kill process tree by PID on Windows
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            # Terminate group process on Unix
            try:
                import signal
                os.killpg(pid, signal.SIGKILL)
            except Exception:
                try:
                    os.kill(pid, 9)
                except Exception:
                    pass

    @classmethod
    def execute_sandboxed_command(
        cls,
        cmd: List[str],
        timeout: float = 10.0,
        cwd: Optional[str] = None,
        enable_rollback: bool = True,
    ) -> Dict[str, Any]:
        """Executes command inside isolated process, checking timeouts and triggering rollbacks."""
        target_cwd = cwd or os.getcwd()
        snap_dir = None
        rolled_back = False

        # 1. Create copy-on-write snapshot if mutating and rollback is requested
        if enable_rollback and Path(target_cwd).exists():
            try:
                snap_dir = cls.create_snapshot(target_cwd)
            except Exception as e:
                logger.warning(f"Failed to create sandbox snapshot: {e}")

        # 2. Compile execution group parameters
        popen_args: Dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "cwd": target_cwd,
        }

        # Enable process group isolation
        if sys.platform == "win32":
            popen_args["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_args["start_new_session"] = True

        start_time = time.perf_counter()
        proc = None
        try:
            proc = subprocess.Popen(cmd, **popen_args)
            stdout, stderr = proc.communicate(timeout=timeout)
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            returncode = proc.returncode

        except subprocess.TimeoutExpired:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            if proc:
                cls.cleanup_process_tree(proc.pid)
                # Wait briefly for processes to terminate
                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    pass

            returncode = -1
            stdout = ""
            stderr = "Command timed out."

        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass
            returncode = -1
            stdout = ""
            stderr = str(e)

        # 3. Evaluate results and trigger rollback on failures
        if returncode != 0 and snap_dir and Path(snap_dir).exists():
            try:
                cls.restore_snapshot(snap_dir, target_cwd)
                rolled_back = True
            except Exception as e:
                logger.error(f"Failed to restore sandbox snapshot: {e}")

        # 4. Cleanup snapshot backup folder
        if snap_dir:
            try:
                # Cleanup temp directory parent
                shutil.rmtree(Path(snap_dir).parent)
            except Exception:
                pass

        return {
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": duration_ms,
            "rolled_back": rolled_back,
        }
