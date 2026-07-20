"""Boundary tests designed to kill safety-critical Action Runtime mutations."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from backend.core.action import (
    Action,
    ActionResult,
    Capability,
    CapabilityManager,
    ExecutorRegistry,
    FileExecutor,
    FileVerifier,
    RecoveryPolicy,
    ShellExecutor,
)
from backend.core.action.registry import ExecutorNotFoundError

pytestmark = [pytest.mark.unit, pytest.mark.safety]


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"executor": " "}, ValueError),
        ({"operation": " "}, ValueError),
        ({"action_id": " "}, ValueError),
        ({"priority": True}, TypeError),
        ({"created_at": datetime.now()}, ValueError),
    ],
)
def test_action_rejects_invalid_identity_fields(
    overrides: dict[str, object],
    error: type[Exception],
) -> None:
    values: dict[str, object] = {
        "executor": "file",
        "operation": "write",
        "parameters": {},
    }
    values.update(overrides)
    with pytest.raises(error):
        Action(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"success": True, "verified": False, "executed": True},
        {"latency_ms": -0.1},
        {"retry_count": -1},
        {"timestamp": datetime.now()},
    ],
)
def test_action_result_rejects_false_success_and_invalid_metrics(
    overrides: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "success": False,
        "verified": False,
        "executed": False,
        "executor": "file",
        "latency_ms": 0.0,
        "retry_count": 0,
        "error_code": "TEST",
        "error_message": "test",
    }
    values.update(overrides)
    with pytest.raises(ValueError):
        ActionResult(**values)  # type: ignore[arg-type]


def test_registry_supports_replacement_listing_and_removal(tmp_path: Path) -> None:
    registry = ExecutorRegistry()
    first = FileExecutor(tmp_path)
    second = FileExecutor(tmp_path)
    registry.register("file", first)
    registry.register("FILE", second, replace=True)

    assert registry.registered_names() == ("file",)
    assert registry.resolve("file") is second
    registry.unregister("file")
    with pytest.raises(ExecutorNotFoundError):
        registry.unregister("file")
    with pytest.raises(ValueError):
        registry.resolve(" ")
    with pytest.raises(TypeError):
        registry.register("invalid", object())  # type: ignore[arg-type]


def test_file_executor_rejects_non_directory_base(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("data", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        FileExecutor(target)


@pytest.mark.parametrize(
    ("action", "error_code"),
    [
        (
            Action(executor="shell", operation="write", parameters={}),
            "EXECUTOR_MISMATCH",
        ),
        (
            Action(executor="file", operation="delete", parameters={}),
            "UNSUPPORTED_OPERATION",
        ),
        (
            Action(
                executor="file",
                operation="write",
                parameters={"path": "", "content": "x"},
            ),
            "INVALID_PARAMETERS",
        ),
        (
            Action(
                executor="file",
                operation="write",
                parameters={"path": "x", "content": 3},
            ),
            "INVALID_PARAMETERS",
        ),
        (
            Action(
                executor="file",
                operation="write",
                parameters={"path": ".", "content": "x"},
            ),
            "INVALID_PARAMETERS",
        ),
    ],
)
def test_file_executor_denies_invalid_requests(
    tmp_path: Path,
    action: Action,
    error_code: str,
) -> None:
    result = FileExecutor(tmp_path).execute(action)
    assert result.error_code == error_code
    assert result.success is False
    assert result.executed is False


def test_file_executor_retries_transient_io_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.core.action.file_executor as file_executor_module

    original_replace = os.replace
    calls = 0

    def flaky_replace(source: str | Path, destination: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("temporarily locked")
        original_replace(source, destination)

    monkeypatch.setattr(file_executor_module.os, "replace", flaky_replace)
    result = FileExecutor(
        tmp_path,
        recovery_policy=RecoveryPolicy(max_retries=1),
    ).execute(
        Action(
            executor="file",
            operation="write",
            parameters={"path": "retry.txt", "content": "recovered"},
        )
    )

    assert calls == 2
    assert result.success is True
    assert result.retry_count == 1
    assert (tmp_path / "retry.txt").read_text(encoding="utf-8") == "recovered"


def test_file_verification_failure_removes_new_file(tmp_path: Path) -> None:
    class RejectingVerifier:
        method = "reject"

        def verify(self, path: Path, expected_content: bytes) -> bool:
            return False

    target = tmp_path / "new.txt"
    result = FileExecutor(tmp_path, verifier=RejectingVerifier()).execute(
        Action(
            executor="file",
            operation="write",
            parameters={"path": target.name, "content": "unverified"},
        )
    )

    assert result.error_code == "VERIFICATION_FAILED"
    assert result.recovery_attempted is True
    assert target.exists() is False
    assert FileVerifier().verify(target, b"unverified") is False


def test_file_executor_survives_resource_sampler_failure(tmp_path: Path) -> None:
    class BrokenSampler:
        def sample(self) -> object:
            raise OSError("metrics unavailable")

    result = FileExecutor(tmp_path, resource_sampler=BrokenSampler()).execute(  # type: ignore[arg-type]
        Action(
            executor="file",
            operation="write",
            parameters={"path": "metrics.txt", "content": "ok"},
        )
    )

    assert result.success is True
    assert result.memory_mb == 0.0


def test_recovery_policy_rejects_non_integer_and_negative_counts() -> None:
    with pytest.raises(TypeError):
        RecoveryPolicy(max_retries=True)
    with pytest.raises(ValueError):
        RecoveryPolicy().should_retry("SHELL_TIMEOUT", -1)


def test_shell_executor_rejects_invalid_construction(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.touch()
    with pytest.raises(NotADirectoryError):
        ShellExecutor(file_path)
    with pytest.raises(ValueError):
        ShellExecutor(tmp_path, timeout_seconds=0)


@pytest.mark.parametrize(
    ("action", "error_code"),
    [
        (
            Action(executor="file", operation="execute", parameters={}),
            "EXECUTOR_MISMATCH",
        ),
        (
            Action(executor="shell", operation="write", parameters={}),
            "UNSUPPORTED_OPERATION",
        ),
        (
            Action(
                executor="shell",
                operation="execute",
                parameters={"argv": ["python", "--version"]},
                requires_confirmation=True,
            ),
            "CONFIRMATION_REQUIRED",
        ),
        (
            Action(
                executor="shell", operation="execute", parameters={"argv": ["unknown"]}
            ),
            "COMMAND_NOT_ALLOWED",
        ),
        (
            Action(
                executor="shell",
                operation="execute",
                parameters={"argv": ["/bin/python"]},
            ),
            "COMMAND_NOT_ALLOWED",
        ),
    ],
)
def test_shell_executor_denies_preflight_and_allowlist_failures(
    tmp_path: Path,
    action: Action,
    error_code: str,
) -> None:
    result = ShellExecutor(tmp_path).execute(action)
    assert result.error_code == error_code
    assert result.executed is False


def test_shell_executor_success_uses_argv_without_shell(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, "Python", "")

    action = Action(
        executor="shell",
        operation="execute",
        parameters={"argv": ["python.exe", "--version"]},
    )
    result = ShellExecutor(tmp_path, runner=runner).execute(action)

    assert result.success is True
    assert result.verified is True
    assert result.action_id == action.action_id
    assert captured["shell"] is False
    assert captured["check"] is False


def test_shell_executor_retries_io_errors_to_configured_limit(tmp_path: Path) -> None:
    calls = 0

    def runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise FileNotFoundError(args[0])

    result = ShellExecutor(
        tmp_path,
        runner=runner,
        recovery_policy=RecoveryPolicy(max_retries=1),
    ).execute(
        Action(
            executor="shell",
            operation="execute",
            parameters={"argv": ["python", "--version"]},
        )
    )

    assert calls == 2
    assert result.error_code == "SHELL_IO_ERROR"
    assert result.retry_count == 1


def test_shell_executor_survives_resource_sampler_failure(tmp_path: Path) -> None:
    class BrokenSampler:
        def sample(self) -> object:
            raise RuntimeError("metrics unavailable")

    def runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, "ok", "")

    result = ShellExecutor(
        tmp_path,
        runner=runner,
        resource_sampler=BrokenSampler(),  # type: ignore[arg-type]
    ).execute(
        Action(
            executor="shell",
            operation="execute",
            parameters={"argv": ["python", "--version"]},
        )
    )

    assert result.success is True
    assert result.cpu_percent == 0.0


def test_capability_manager_can_map_custom_operations() -> None:
    action = Action(executor="custom", operation="publish", parameters={})
    manager = CapabilityManager(
        (Capability.FILE_WRITE,),
        action_capabilities={("custom", "publish"): Capability.FILE_WRITE},
    )
    assert manager.required_capability(action) is Capability.FILE_WRITE
    assert manager.is_allowed(action) is True
