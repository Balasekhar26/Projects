"""Unit tests for Program 45.0: Execution Sandbox.

Verifies local command execution, process cleanup, and folder rollback triggers.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
import sys

from backend.core.sandbox import LocalExecutionSandbox


class TestLocalSandbox:
    def test_execute_command_success(self):
        # Run a simple echo command
        if sys.platform == "win32":
            cmd = ["cmd", "/c", "echo", "hello"]
        else:
            cmd = ["echo", "hello"]

        res = LocalExecutionSandbox.execute_sandboxed_command(
            cmd=cmd,
            timeout=5.0,
            enable_rollback=False,
        )

        assert res["returncode"] == 0
        assert "hello" in res["stdout"].strip().lower()
        assert res["rolled_back"] is False

    def test_execute_command_rollback_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            
            # Create a file beforehand
            base_file = tmp_path / "base.txt"
            base_file.write_text("initial state")

            # Command that creates a new file and then exits with failure (non-zero code)
            # On Windows: cmd /c "echo bad > error.txt & exit 1"
            # On Unix: sh -c "echo bad > error.txt; exit 1"
            if sys.platform == "win32":
                cmd = ["cmd", "/c", f"echo bad > {tmp_path}/error.txt & exit 1"]
            else:
                cmd = ["sh", "-c", f"echo bad > {tmp_path}/error.txt; exit 1"]

            res = LocalExecutionSandbox.execute_sandboxed_command(
                cmd=cmd,
                timeout=5.0,
                cwd=str(tmp_path),
                enable_rollback=True,
            )

            assert res["returncode"] != 0
            assert res["rolled_back"] is True

            # The new file 'error.txt' should be deleted (rolled back!)
            assert not (tmp_path / "error.txt").exists()
            # The original file 'base.txt' must be intact
            assert base_file.read_text() == "initial state"

    def test_execute_command_timeout_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            
            # Use sys.argv to pass the path to prevent quote escaping issues
            cmd = [
                sys.executable,
                "-c",
                "import time, sys; open(sys.argv[1], 'w').write('temp'); time.sleep(10)",
                str(tmp_path / "temp.txt"),
            ]

            res = LocalExecutionSandbox.execute_sandboxed_command(
                cmd=cmd,
                timeout=1.0,
                cwd=str(tmp_path),
                enable_rollback=True,
            )

            assert res["returncode"] == -1
            assert "timed out" in res["stderr"].lower()
            assert res["rolled_back"] is True
            # Verification: files created during timed out execution are rolled back!
            assert not (tmp_path / "temp.txt").exists()
