"""Capability-gated, argv-only shell action execution."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any, Protocol

from backend.core.action.capabilities import Capability, CapabilityManager
from backend.core.action.interfaces import ShellVerifierProtocol
from backend.core.action.models import Action, ActionResult
from backend.core.action.recovery import RecoveryPolicy
from backend.core.action.resources import (
    ProcessResourceSampler,
    ResourceMetrics,
    ResourceSamplerProtocol,
)
from backend.core.action.verifier import ShellVerifier

DEFAULT_ALLOWED_EXECUTABLES = frozenset(
    {"dir", "git", "ls", "node", "npm", "pwd", "python", "python3", "pytest", "ruff"}
)
DESTRUCTIVE_TOKENS = frozenset(
    {
        "del",
        "diskpart",
        "format",
        "mkfs",
        "reboot",
        "remove-item",
        "rm",
        "rmdir",
        "shutdown",
        "stop-computer",
    }
)


class ShellRunnerProtocol(Protocol):
    """Injectable subprocess runner used by the shell executor."""

    def __call__(
        self,
        args: list[str],
        *,
        shell: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
        cwd: Path,
        check: bool,
    ) -> CompletedProcess[str]:
        """Run one process without shell interpretation."""

        ...


class ShellExecutor:
    """Execute allowlisted commands without invoking an operating-system shell."""

    executor_name = "shell"

    def __init__(
        self,
        working_directory: str | Path,
        *,
        capability_manager: CapabilityManager | None = None,
        verifier: ShellVerifierProtocol | None = None,
        recovery_policy: RecoveryPolicy | None = None,
        resource_sampler: ResourceSamplerProtocol | None = None,
        runner: ShellRunnerProtocol = subprocess.run,
        allowed_executables: frozenset[str] = DEFAULT_ALLOWED_EXECUTABLES,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._working_directory = Path(working_directory).resolve(strict=True)
        if not self._working_directory.is_dir():
            raise NotADirectoryError(str(self._working_directory))
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._capability_manager = capability_manager or CapabilityManager.allowing(
            Capability.SHELL_EXECUTE
        )
        self._verifier = verifier or ShellVerifier()
        self._recovery_policy = recovery_policy or RecoveryPolicy(max_retries=2)
        self._resource_sampler = resource_sampler or ProcessResourceSampler()
        self._runner = runner
        self._allowed_executables = frozenset(
            executable.casefold() for executable in allowed_executables
        )
        self._timeout_seconds = timeout_seconds

    def execute(self, action: Action) -> ActionResult:
        """Validate, execute, and independently verify a shell action."""

        started_ns = time.perf_counter_ns()
        preflight_error = self._preflight(action)
        if preflight_error is not None:
            code, message = preflight_error
            return self._result(
                action,
                started_ns,
                success=False,
                verified=False,
                executed=False,
                retry_count=0,
                error_code=code,
                error_message=message,
            )

        argv = self._validated_argv(action.parameters.get("argv"))
        if isinstance(argv, tuple):
            code, message = argv
            return self._result(
                action,
                started_ns,
                success=False,
                verified=False,
                executed=False,
                retry_count=0,
                error_code=code,
                error_message=message,
            )

        retry_count = 0
        while True:
            try:
                completed = self._runner(
                    argv,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_seconds,
                    cwd=self._working_directory,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                if self._recovery_policy.should_retry("SHELL_TIMEOUT", retry_count):
                    retry_count += 1
                    continue
                return self._result(
                    action,
                    started_ns,
                    success=False,
                    verified=False,
                    executed=False,
                    retry_count=retry_count,
                    error_code="SHELL_TIMEOUT",
                    error_message=str(exc),
                )
            except OSError as exc:
                if self._recovery_policy.should_retry("SHELL_IO_ERROR", retry_count):
                    retry_count += 1
                    continue
                return self._result(
                    action,
                    started_ns,
                    success=False,
                    verified=False,
                    executed=False,
                    retry_count=retry_count,
                    error_code="SHELL_IO_ERROR",
                    error_message=str(exc),
                )

            verified = self._verifier.verify(completed)
            if not verified:
                return self._result(
                    action,
                    started_ns,
                    success=False,
                    verified=False,
                    executed=True,
                    retry_count=retry_count,
                    error_code="VERIFICATION_FAILED",
                    error_message=completed.stderr or "shell outcome was not verified",
                )
            return self._result(
                action,
                started_ns,
                success=True,
                verified=True,
                executed=True,
                retry_count=retry_count,
                error_code=None,
                error_message=None,
            )

    def _preflight(self, action: Action) -> tuple[str, str] | None:
        if action.executor != self.executor_name:
            return (
                "EXECUTOR_MISMATCH",
                f"expected executor '{self.executor_name}', got '{action.executor}'",
            )
        if action.operation != "execute":
            return (
                "UNSUPPORTED_OPERATION",
                f"shell executor does not support '{action.operation}'",
            )
        if not self._capability_manager.is_allowed(action):
            return "CAPABILITY_DENIED", "shell execution capability is not granted"
        if action.requires_confirmation:
            return (
                "CONFIRMATION_REQUIRED",
                "shell execution requires explicit confirmation",
            )
        return None

    def _validated_argv(self, value: Any) -> list[str] | tuple[str, str]:
        if not isinstance(value, list) or not value:
            return "INVALID_PARAMETERS", "parameters.argv must be a non-empty list"
        if len(value) > 128 or any(
            not isinstance(argument, str) or not argument or len(argument) > 4096
            for argument in value
        ):
            return "INVALID_PARAMETERS", "parameters.argv contains invalid arguments"

        argv = list(value)
        executable_path = Path(argv[0])
        executable = executable_path.name.casefold()
        if executable.endswith(".exe"):
            executable = executable[:-4]
        if executable_path.name != argv[0]:
            return "COMMAND_NOT_ALLOWED", "executable is not allowlisted"
        if self._is_destructive(argv):
            return "DESTRUCTIVE_COMMAND", "destructive shell command is blocked"
        if executable not in self._allowed_executables:
            return "COMMAND_NOT_ALLOWED", "executable is not allowlisted"
        return argv

    @staticmethod
    def _is_destructive(argv: list[str]) -> bool:
        normalized = [argument.strip().casefold() for argument in argv]
        if any(token in DESTRUCTIVE_TOKENS for token in normalized):
            return True
        if normalized[0].removesuffix(".exe") == "git":
            if "clean" in normalized or "--hard" in normalized:
                return True
        return False

    def _result(
        self,
        action: Action,
        started_ns: int,
        *,
        success: bool,
        verified: bool,
        executed: bool,
        retry_count: int,
        error_code: str | None,
        error_message: str | None,
    ) -> ActionResult:
        metrics = self._sample_resources()
        return ActionResult(
            success=success,
            verified=verified,
            executed=executed,
            executor=self.executor_name,
            latency_ms=(time.perf_counter_ns() - started_ns) / 1_000_000,
            retry_count=retry_count,
            error_code=error_code,
            error_message=error_message,
            action_id=action.action_id,
            cpu_percent=metrics.cpu_percent,
            memory_mb=metrics.memory_mb,
            confidence=1.0 if success else 0.0,
            verification_method=self._verifier.method if executed else None,
        )

    def _sample_resources(self) -> ResourceMetrics:
        try:
            return self._resource_sampler.sample()
        except (OSError, RuntimeError):
            return ResourceMetrics(cpu_percent=0.0, memory_mb=0.0)
