"""End-to-end integration coverage for a file intent."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.action import (
    Action,
    Capability,
    CapabilityManager,
    ExecutorRegistry,
    FileExecutor,
    FileVerifier,
)

pytestmark = pytest.mark.integration


def test_intent_to_independently_verified_file_action(tmp_path: Path) -> None:
    intent = {
        "executor": "file",
        "operation": "write",
        "path": "hello.txt",
        "content": "Hello World",
    }
    action = Action(
        executor=intent["executor"],
        operation=intent["operation"],
        parameters={"path": intent["path"], "content": intent["content"]},
        requires_confirmation=False,
    )
    verifier = FileVerifier()
    registry = ExecutorRegistry()
    registry.register(
        "file",
        FileExecutor(
            tmp_path,
            verifier=verifier,
            capability_manager=CapabilityManager.allowing(Capability.FILE_WRITE),
        ),
    )

    result = registry.resolve(action.executor).execute(action)

    target = tmp_path / "hello.txt"
    assert verifier.verify(target, b"Hello World") is True
    assert result.action_id == action.action_id
    assert result.executed is True
    assert result.verified is True
    assert result.success is True
    assert result.retry_count == 0
    assert result.verification_method == verifier.method
