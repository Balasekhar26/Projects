"""Property and denial-path tests for safety-critical Action Runtime policy."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from backend.core.action import (
    Action,
    CapabilityManager,
    FileExecutor,
    FileVerifier,
    RecoveryPolicy,
    ShellExecutor,
)
from backend.core.action.recovery import MAX_RETRIES

pytestmark = [pytest.mark.unit, pytest.mark.safety]


@given(executor=st.text(), operation=st.text())
def test_capability_manager_denies_every_action_without_grants(
    executor: str,
    operation: str,
) -> None:
    if not executor.strip() or not operation.strip():
        return
    action = Action(executor=executor, operation=operation, parameters={})

    assert CapabilityManager.deny_all().is_allowed(action) is False


@given(content=st.text(max_size=2048))
@settings(max_examples=40, deadline=None)
def test_file_executor_writes_and_verifies_arbitrary_unicode(
    content: str,
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        base_path = Path(directory)
        action = Action(
            executor="file",
            operation="write",
            parameters={"path": "property.txt", "content": content},
        )

        result = FileExecutor(base_path).execute(action)

        assert result.success is True
        assert result.executed is True
        assert result.verified is True
        assert result.action_id == action.action_id
        assert result.retry_count <= MAX_RETRIES
        assert (base_path / "property.txt").read_bytes().decode("utf-8") == content


@given(content=st.binary(max_size=2048))
@settings(deadline=None)
def test_file_verifier_rejects_every_nonmatching_payload(content: bytes) -> None:
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "payload.bin"
        target.write_bytes(content)
        different = content + b"\x00"

        assert FileVerifier().verify(target, content) is True
        assert FileVerifier().verify(target, different) is False


@given(depth=st.integers(min_value=1, max_value=8))
@settings(deadline=None)
def test_file_executor_denies_path_traversal(depth: int) -> None:
    with tempfile.TemporaryDirectory() as directory:
        base_path = Path(directory)
        escaped_path = "/".join([".."] * depth + ["escaped.txt"])
        action = Action(
            executor="file",
            operation="write",
            parameters={"path": escaped_path, "content": "blocked"},
        )

        result = FileExecutor(base_path).execute(action)

        assert result.success is False
        assert result.executed is False
        assert result.error_code == "INVALID_PARAMETERS"


def test_file_executor_denies_missing_capability_before_disk_access(
    tmp_path: Path,
) -> None:
    target = tmp_path / "denied.txt"
    action = Action(
        executor="file",
        operation="write",
        parameters={"path": target.name, "content": "must not exist"},
    )
    executor = FileExecutor(
        tmp_path,
        capability_manager=CapabilityManager.deny_all(),
    )

    result = executor.execute(action)

    assert result.error_code == "CAPABILITY_DENIED"
    assert result.executed is False
    assert target.exists() is False


@given(retry_limit=st.integers().filter(lambda value: value < 0 or value > MAX_RETRIES))
def test_recovery_policy_rejects_retry_limits_above_safety_ceiling(
    retry_limit: int,
) -> None:
    with pytest.raises(ValueError):
        RecoveryPolicy(max_retries=retry_limit)


@given(
    retry_limit=st.integers(min_value=0, max_value=MAX_RETRIES),
    retry_count=st.integers(min_value=0, max_value=MAX_RETRIES + 2),
)
def test_recovery_policy_never_retries_past_configured_limit(
    retry_limit: int,
    retry_count: int,
) -> None:
    policy = RecoveryPolicy(max_retries=retry_limit)

    assert policy.should_retry("SHELL_TIMEOUT", retry_count) is (
        retry_count < retry_limit
    )
    assert policy.should_retry("CAPABILITY_DENIED", retry_count) is False


@pytest.mark.parametrize(
    "argv",
    [
        ["rm", "-rf", "/"],
        ["del", "/f", "important.txt"],
        ["format", "C:"],
        ["shutdown", "/s"],
        ["git", "reset", "--hard"],
        ["git", "clean", "-fd"],
    ],
)
def test_shell_executor_denies_destructive_commands(
    tmp_path: Path,
    argv: list[str],
) -> None:
    calls: list[list[str]] = []

    def runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    result = ShellExecutor(tmp_path, runner=runner).execute(
        Action(executor="shell", operation="execute", parameters={"argv": argv})
    )

    assert result.success is False
    assert result.executed is False
    assert result.error_code == "DESTRUCTIVE_COMMAND"
    assert calls == []


@given(value=st.one_of(st.none(), st.text(), st.integers(), st.lists(st.integers())))
@settings(deadline=None)
def test_shell_executor_rejects_malformed_argv(value: object) -> None:
    with tempfile.TemporaryDirectory() as directory:
        result = ShellExecutor(directory).execute(
            Action(
                executor="shell",
                operation="execute",
                parameters={"argv": value},
            )
        )

        assert result.success is False
        assert result.executed is False
        assert result.error_code == "INVALID_PARAMETERS"


def test_shell_executor_denies_missing_capability_without_calling_runner(
    tmp_path: Path,
) -> None:
    called = False

    def runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        return subprocess.CompletedProcess(args, 0, "", "")

    executor = ShellExecutor(
        tmp_path,
        runner=runner,
        capability_manager=CapabilityManager.deny_all(),
    )
    result = executor.execute(
        Action(
            executor="shell",
            operation="execute",
            parameters={"argv": ["python", "--version"]},
        )
    )

    assert result.error_code == "CAPABILITY_DENIED"
    assert result.executed is False
    assert called is False


def test_shell_executor_never_reports_unverified_success(tmp_path: Path) -> None:
    class RejectingVerifier:
        method = "forced_rejection"

        def verify(self, completed: subprocess.CompletedProcess[str]) -> bool:
            return False

    def runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, "ok", "")

    result = ShellExecutor(
        tmp_path,
        runner=runner,
        verifier=RejectingVerifier(),
    ).execute(
        Action(
            executor="shell",
            operation="execute",
            parameters={"argv": ["python", "--version"]},
        )
    )

    assert result.executed is True
    assert result.verified is False
    assert result.success is False
    assert result.error_code == "VERIFICATION_FAILED"


def test_shell_executor_caps_transient_retries_at_three(tmp_path: Path) -> None:
    calls = 0

    def runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise subprocess.TimeoutExpired(args, 0.01)

    result = ShellExecutor(
        tmp_path,
        runner=runner,
        recovery_policy=RecoveryPolicy(max_retries=MAX_RETRIES),
    ).execute(
        Action(
            executor="shell",
            operation="execute",
            parameters={"argv": ["python", "--version"]},
        )
    )

    assert calls == MAX_RETRIES + 1
    assert result.retry_count == MAX_RETRIES
    assert result.success is False
    assert result.error_code == "SHELL_TIMEOUT"
