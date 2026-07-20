"""Confined and verification-driven filesystem action execution."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from threading import RLock

from backend.core.action.capabilities import Capability, CapabilityManager
from backend.core.action.interfaces import FileVerifierProtocol
from backend.core.action.models import Action, ActionResult
from backend.core.action.recovery import RecoveryPolicy
from backend.core.action.resources import (
    ProcessResourceSampler,
    ResourceMetrics,
    ResourceSamplerProtocol,
)
from backend.core.action.verifier import FileVerifier


class FileExecutor:
    """Execute atomic file writes within one injected base directory."""

    executor_name = "file"

    def __init__(
        self,
        base_directory: str | Path,
        verifier: FileVerifierProtocol | None = None,
        capability_manager: CapabilityManager | None = None,
        recovery_policy: RecoveryPolicy | None = None,
        resource_sampler: ResourceSamplerProtocol | None = None,
    ) -> None:
        self._base_directory = Path(base_directory).resolve(strict=True)
        if not self._base_directory.is_dir():
            raise NotADirectoryError(str(self._base_directory))
        self._verifier = verifier or FileVerifier()
        self._capability_manager = capability_manager or CapabilityManager.allowing(
            Capability.FILE_WRITE
        )
        self._recovery_policy = recovery_policy or RecoveryPolicy(max_retries=0)
        self._resource_sampler = resource_sampler or ProcessResourceSampler()
        self._lock = RLock()

    def execute(self, action: Action) -> ActionResult:
        """Atomically write and verify a file, returning all failures as data."""

        started_ns = time.perf_counter_ns()
        if action.executor != self.executor_name:
            return self._failure(
                started_ns,
                action_id=action.action_id,
                executed=False,
                code="EXECUTOR_MISMATCH",
                message=f"expected executor '{self.executor_name}', got '{action.executor}'",
            )
        if action.operation != "write":
            return self._failure(
                started_ns,
                action_id=action.action_id,
                executed=False,
                code="UNSUPPORTED_OPERATION",
                message=f"file executor does not support '{action.operation}'",
            )
        if not self._capability_manager.is_allowed(action):
            return self._failure(
                started_ns,
                action_id=action.action_id,
                executed=False,
                code="CAPABILITY_DENIED",
                message="file write capability is not granted",
            )
        if action.requires_confirmation:
            return self._failure(
                started_ns,
                action_id=action.action_id,
                executed=False,
                code="CONFIRMATION_REQUIRED",
                message="file write requires explicit confirmation",
            )

        try:
            target, content = self._validated_request(action)
        except (TypeError, ValueError) as exc:
            return self._failure(
                started_ns,
                action_id=action.action_id,
                executed=False,
                code="INVALID_PARAMETERS",
                message=str(exc),
            )

        with self._lock:
            retry_count = 0
            while True:
                result = self._write_and_verify(
                    target,
                    content,
                    started_ns,
                    action.action_id,
                    retry_count,
                )
                if not result.error_code or not self._recovery_policy.should_retry(
                    result.error_code,
                    retry_count,
                ):
                    return result
                retry_count += 1

    def _validated_request(self, action: Action) -> tuple[Path, bytes]:
        path_value = action.parameters.get("path")
        content_value = action.parameters.get("content")
        if not isinstance(path_value, str) or not path_value.strip():
            raise TypeError("parameters.path must be a non-empty string")
        if not isinstance(content_value, str):
            raise TypeError("parameters.content must be a string")

        requested_path = Path(path_value)
        target = (
            requested_path
            if requested_path.is_absolute()
            else self._base_directory / requested_path
        ).resolve(strict=False)
        try:
            target.relative_to(self._base_directory)
        except ValueError as exc:
            raise ValueError(
                "parameters.path escapes the configured base directory"
            ) from exc
        if target == self._base_directory:
            raise ValueError("parameters.path must identify a file")
        if not target.parent.is_dir():
            raise ValueError("parameters.path parent directory does not exist")
        return target, content_value.encode("utf-8")

    def _write_and_verify(
        self,
        target: Path,
        content: bytes,
        started_ns: int,
        action_id: str,
        retry_count: int,
    ) -> ActionResult:
        previous_content: bytes | None = None
        existed = target.exists()
        temporary_path: Path | None = None

        try:
            if existed:
                if not target.is_file():
                    raise IsADirectoryError(str(target))
                previous_content = target.read_bytes()

            file_descriptor, temporary_name = tempfile.mkstemp(
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(file_descriptor, "wb") as temporary_file:
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, target)
            temporary_path = None

            if self._verifier.verify(target, content):
                metrics = self._sample_resources()
                return ActionResult(
                    success=True,
                    verified=True,
                    executed=True,
                    executor=self.executor_name,
                    latency_ms=self._latency_ms(started_ns),
                    retry_count=retry_count,
                    error_code=None,
                    error_message=None,
                    action_id=action_id,
                    cpu_percent=metrics.cpu_percent,
                    memory_mb=metrics.memory_mb,
                    confidence=1.0,
                    verification_method=self._verifier.method,
                )

            self._restore(target, existed, previous_content)
            return self._failure(
                started_ns,
                action_id=action_id,
                executed=True,
                code="VERIFICATION_FAILED",
                message="written file did not match the requested content",
                recovery_attempted=True,
                retry_count=retry_count,
            )
        except OSError as exc:
            return self._failure(
                started_ns,
                action_id=action_id,
                executed=False,
                code="FILE_IO_ERROR",
                message=str(exc),
                retry_count=retry_count,
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _restore(target: Path, existed: bool, previous_content: bytes | None) -> None:
        if existed and previous_content is not None:
            target.write_bytes(previous_content)
        else:
            target.unlink(missing_ok=True)

    def _failure(
        self,
        started_ns: int,
        *,
        action_id: str,
        executed: bool,
        code: str,
        message: str,
        recovery_attempted: bool = False,
        retry_count: int = 0,
    ) -> ActionResult:
        metrics = self._sample_resources()
        return ActionResult(
            success=False,
            verified=False,
            executed=executed,
            executor=self.executor_name,
            latency_ms=self._latency_ms(started_ns),
            retry_count=retry_count,
            error_code=code,
            error_message=message,
            action_id=action_id,
            cpu_percent=metrics.cpu_percent,
            memory_mb=metrics.memory_mb,
            confidence=0.0,
            recovery_attempted=recovery_attempted,
            verification_method=self._verifier.method if executed else None,
        )

    def _sample_resources(self) -> ResourceMetrics:
        try:
            return self._resource_sampler.sample()
        except (OSError, RuntimeError):
            return ResourceMetrics(cpu_percent=0.0, memory_mb=0.0)

    @staticmethod
    def _latency_ms(started_ns: int) -> float:
        return (time.perf_counter_ns() - started_ns) / 1_000_000
