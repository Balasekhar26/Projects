"""Unit tests for Program 51.0: Agent Runtime.

Verifies live Agent instantiation, blackboard/event bus syncs, sandbox triggers, and subtasks requests.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
from pathlib import Path
import pytest

from backend.core.agent_registry import DEFAULT_REGISTRY
from backend.core.agent_runtime import Agent
from backend.core.blackboard import BLACKBOARD
from backend.core.event_bus import EventBus, Event, EventName
from backend.core.goal_memory import GoalMemory
from backend.core.goal_manager import GoalManager


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Sets a temporary folder for files and databases to isolate tests."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_agent_rt_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", temp_dir)

    GoalMemory._schema_ensured = False
    GoalMemory.reset()
    EventBus.reset()
    BLACKBOARD.clear()

    yield Path(temp_dir)

    shutil.rmtree(temp_dir, ignore_errors=True)
    EventBus.reset()
    BLACKBOARD.clear()


def test_agent_initialization_from_definition():
    builder_def = DEFAULT_REGISTRY.get_or_raise("Builder")
    agent = Agent(builder_def, execution_budget=500.0)

    assert agent.name == "Builder"
    assert "code_generator" in agent.capabilities
    assert agent.authority_level == 55
    assert agent.execution_budget == 500.0
    assert agent.confidence == 1.0
    assert agent.agent_id.startswith("agt_")


def test_agent_publish_to_blackboard_emits_event():
    builder_def = DEFAULT_REGISTRY.get_or_raise("Builder")
    agent = Agent(builder_def)

    event_received: list[Event] = []
    event_lock = threading.Event()

    def on_belief_updated(e: Event):
        event_received.append(e)
        event_lock.set()

    EventBus.subscribe(EventName.BELIEF_UPDATED, on_belief_updated)

    post = agent.publish_to_blackboard(
        topic="insight",
        payload={"result": "code compiles successfully"},
        confidence=0.9,
    )

    # Verify blackboard write
    assert post.publisher == "Builder"
    assert post.topic == "insight"
    assert post.confidence == 0.9

    # Wait for async delivery
    delivered = event_lock.wait(timeout=5.0)
    assert delivered, "Event was not delivered in time"

    # Verify event delivery
    assert len(event_received) == 1
    assert event_received[0].payload["post_id"] == post.post_id
    assert event_received[0].payload["topic"] == "insight"
    assert event_received[0].source == "Builder"


def test_agent_request_goal():
    planner_def = DEFAULT_REGISTRY.get_or_raise("Planner")
    agent = Agent(planner_def)

    events: list[Event] = []
    event_lock = threading.Event()

    def on_goal_created(e: Event):
        events.append(e)
        event_lock.set()

    EventBus.subscribe(EventName.GOAL_CREATED, on_goal_created)

    goal = agent.request_goal(
        title="Setup project dependencies",
        description="Run pip install",
    )

    assert goal["owner_agent"] == "Planner"
    assert goal["title"] == "Setup project dependencies"

    # Wait for async delivery
    delivered = event_lock.wait(timeout=5.0)
    assert delivered, "GoalCreated event not delivered in time"

    # Verify event bus triggers
    assert len(events) == 1
    assert events[0].payload["goal_id"] == goal["goal_id"]
    assert events[0].payload["owner_agent"] == "Planner"


def test_agent_invoke_sandbox_action_success():
    builder_def = DEFAULT_REGISTRY.get_or_raise("Builder")
    agent = Agent(builder_def)

    started_events: list[Event] = []
    finished_events: list[Event] = []
    start_lock = threading.Event()
    finish_lock = threading.Event()

    def on_start(e: Event):
        started_events.append(e)
        start_lock.set()

    def on_finish(e: Event):
        finished_events.append(e)
        finish_lock.set()

    EventBus.subscribe(EventName.EXECUTION_STARTED, on_start)
    EventBus.subscribe(EventName.EXECUTION_FINISHED, on_finish)

    # Run simple echo command
    res = agent.invoke_sandbox_action(cmd=["cmd", "/c", "echo test-run"])

    assert res["returncode"] == 0
    assert "test-run" in res["stdout"]

    # Wait for async delivery of start and finish events
    assert start_lock.wait(timeout=5.0), "ExecutionStarted event not delivered"
    assert finish_lock.wait(timeout=5.0), "ExecutionFinished event not delivered"

    # Verify start and completion events
    assert len(started_events) == 1
    assert started_events[0].payload["command"] == ["cmd", "/c", "echo test-run"]
    assert started_events[0].source == "Builder"

    assert len(finished_events) == 1
    assert finished_events[0].payload["returncode"] == 0
