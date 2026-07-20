"""Typed, verification-driven action execution primitives."""

from backend.core.action.capabilities import Capability, CapabilityManager
from backend.core.action.file_executor import FileExecutor
from backend.core.action.models import Action, ActionResult
from backend.core.action.recovery import RecoveryPolicy
from backend.core.action.registry import ExecutorRegistry
from backend.core.action.shell_executor import ShellExecutor
from backend.core.action.verifier import FileVerifier, ShellVerifier

__all__ = [
    "Action",
    "ActionResult",
    "Capability",
    "CapabilityManager",
    "ExecutorRegistry",
    "FileExecutor",
    "FileVerifier",
    "RecoveryPolicy",
    "ShellExecutor",
    "ShellVerifier",
]
