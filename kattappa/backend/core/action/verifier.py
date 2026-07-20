"""Verification strategies for action executor outcomes."""

from __future__ import annotations

import hmac
from pathlib import Path
from subprocess import CompletedProcess


class FileVerifier:
    """Verify file writes using an exact, timing-safe byte comparison."""

    method = "exact_byte_comparison"

    def verify(self, path: Path, expected_content: bytes) -> bool:
        """Return true only when the path is a file with the expected bytes."""

        try:
            actual_content = path.read_bytes()
        except (OSError, ValueError):
            return False
        return path.is_file() and hmac.compare_digest(actual_content, expected_content)


class ShellVerifier:
    """Verify shell success independently from the executor control flow."""

    method = "process_exit_code"

    def verify(self, completed: CompletedProcess[str]) -> bool:
        """Return true only for a zero process exit code."""

        return completed.returncode == 0
