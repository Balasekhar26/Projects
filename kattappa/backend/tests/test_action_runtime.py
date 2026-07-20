"""Tests for the canonical verification-driven action runtime."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.action import Action, ExecutorRegistry, FileExecutor
from backend.core.action.registry import (
    ExecutorAlreadyRegisteredError,
    ExecutorNotFoundError,
)

pytestmark = pytest.mark.unit


def test_file_write_demonstrates_complete_action_path(tmp_path: Path) -> None:
    registry = ExecutorRegistry()
    registry.register("file", FileExecutor(tmp_path))
    action = Action(
        executor="file",
        operation="write",
        parameters={"path": "hello.txt", "content": "Hello World"},
        priority=0,
        requires_confirmation=False,
    )

    result = registry.resolve(action.executor).execute(action)

    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "Hello World"
    assert result.executed is True
    assert result.verified is True
    assert result.success is True
    assert result.executor == "file"
    assert result.error_code is None
    assert result.latency_ms < 100


def test_file_write_stops_at_confirmation_boundary(tmp_path: Path) -> None:
    executor = FileExecutor(tmp_path)
    action = Action(
        executor="file",
        operation="write",
        parameters={"path": "hello.txt", "content": "Hello World"},
        requires_confirmation=True,
    )

    result = executor.execute(action)

    assert result.success is False
    assert result.executed is False
    assert result.error_code == "CONFIRMATION_REQUIRED"
    assert not (tmp_path / "hello.txt").exists()


@pytest.mark.parametrize("path", ["../outside.txt", "nested/missing.txt"])
def test_file_write_rejects_unsafe_or_missing_parent_paths(
    tmp_path: Path,
    path: str,
) -> None:
    result = FileExecutor(tmp_path).execute(
        Action(
            executor="file",
            operation="write",
            parameters={"path": path, "content": "blocked"},
        )
    )

    assert result.success is False
    assert result.executed is False
    assert result.error_code == "INVALID_PARAMETERS"


def test_verification_failure_restores_existing_file(tmp_path: Path) -> None:
    class RejectingVerifier:
        method = "test_rejection"

        def verify(self, path: Path, expected_content: bytes) -> bool:
            return False

    target = tmp_path / "hello.txt"
    target.write_text("Original", encoding="utf-8")
    executor = FileExecutor(tmp_path, verifier=RejectingVerifier())

    result = executor.execute(
        Action(
            executor="file",
            operation="write",
            parameters={"path": "hello.txt", "content": "Replacement"},
        )
    )

    assert result.success is False
    assert result.executed is True
    assert result.recovery_attempted is True
    assert result.error_code == "VERIFICATION_FAILED"
    assert target.read_text(encoding="utf-8") == "Original"


def test_registry_rejects_duplicates_and_unknown_names(tmp_path: Path) -> None:
    registry = ExecutorRegistry()
    registry.register("FILE", FileExecutor(tmp_path))

    with pytest.raises(ExecutorAlreadyRegisteredError):
        registry.register("file", FileExecutor(tmp_path))
    with pytest.raises(ExecutorNotFoundError):
        registry.resolve("shell")
