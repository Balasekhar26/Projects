"""Unit tests for Program 54.0: Skill Runtime.

Verifies executable Skill instantiation, validation, execution parameter formatting, and trust promotions.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
from pathlib import Path
import pytest

from backend.core.event_bus import EventBus, Event, EventName
from backend.core.skill_library import SkillLibrary
from backend.core.skill_runtime import Skill


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Sets a temporary folder for files and databases to isolate tests."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_skill_rt_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", temp_dir)

    EventBus.reset()
    SkillLibrary.reset()

    yield Path(temp_dir)

    shutil.rmtree(temp_dir, ignore_errors=True)
    EventBus.reset()
    SkillLibrary.reset()


def test_skill_instantiation_and_auto_registration():
    skill = Skill(
        name="Create Folder",
        description="Creates a dir",
        inputs=["path"],
        steps=["cmd /c mkdir {path}"],
        outputs=["status"],
    )

    assert skill.name == "Create Folder"
    assert skill.inputs == ["path"]

    # Verify auto-registered in library
    tpl = SkillLibrary.get("Create Folder")
    assert tpl is not None
    assert tpl["description"] == "Creates a dir"
    assert tpl["trust"] == "draft"


def test_skill_execution_missing_inputs_raises_value_error():
    skill = Skill(
        name="Write File",
        inputs=["filename", "content"],
        steps=["echo {content} > {filename}"],
    )

    with pytest.raises(ValueError, match="Missing required execution inputs"):
        skill.execute({"filename": "test.txt"})  # missing content


def test_skill_execution_success_and_trust_promotion():
    skill = Skill(
        name="Echo Text",
        inputs=["text"],
        steps=["cmd /c echo {text}"],
        outputs=["result"],
    )

    events: list[Event] = []
    event_lock = threading.Event()

    def on_finished(e: Event):
        events.append(e)
        event_lock.set()

    EventBus.subscribe(EventName.EXECUTION_FINISHED, on_finished)

    # 1st execution
    res = skill.execute({"text": "hello-world"})
    assert res["status"] == "success"
    assert res["outputs"]["result"] == "hello-world"

    # Wait for event
    assert event_lock.wait(timeout=5.0), "ExecutionFinished event not received"
    assert len(events) == 1
    assert events[0].payload["skill_name"] == "Echo Text"
    assert events[0].payload["success"] is True

    # Run 2 more times to trigger trust promotion (requires 3 successes)
    skill.execute({"text": "hello-world"})
    skill.execute({"text": "hello-world"})

    tpl = SkillLibrary.get("Echo Text")
    assert tpl["success_count"] == 3
    assert tpl["trust"] == "trusted"
    assert tpl["success_rate"] == 1.0


def test_skill_execution_failure():
    skill = Skill(
        name="Failing Skill",
        inputs=["val"],
        steps=["cmd /c exit {val}"],
    )

    events: list[Event] = []
    event_lock = threading.Event()

    def on_failed(e: Event):
        events.append(e)
        event_lock.set()

    EventBus.subscribe(EventName.EXECUTION_FAILED, on_failed)

    res = skill.execute({"val": "1"})

    assert res["status"] == "failed"
    assert res["steps_run"] == 1

    # Wait for failure event
    assert event_lock.wait(timeout=5.0), "ExecutionFailed event not received"
    assert len(events) == 1
    assert events[0].payload["success"] is False

    tpl = SkillLibrary.get("Failing Skill")
    assert tpl["failure_count"] == 1
    assert tpl["success_count"] == 0
    assert tpl["trust"] == "draft"
