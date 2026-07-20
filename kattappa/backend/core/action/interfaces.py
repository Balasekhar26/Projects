"""Dependency-inversion contracts for action execution and verification."""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from typing import Protocol

from backend.core.action.models import Action, ActionResult


class ActionExecutorProtocol(Protocol):
    """Contract implemented by executor plugins registered at runtime."""

    def execute(self, action: Action) -> ActionResult:
        """Execute and verify one action."""

        ...


class FileVerifierProtocol(Protocol):
    """Contract for verifying an exact file payload after execution."""

    method: str

    def verify(self, path: Path, expected_content: bytes) -> bool:
        """Return whether the file contains the expected bytes."""

        ...


class ShellVerifierProtocol(Protocol):
    """Contract for independently verifying a completed shell process."""

    method: str

    def verify(self, completed: CompletedProcess[str]) -> bool:
        """Return whether the process outcome meets success criteria."""

        ...
