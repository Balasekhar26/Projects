"""Unit tests for Program 52.0: Multi-Agent Orchestrator.

Verifies dynamic routing, agent spawning, consensus debates, and reputation loops.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
from pathlib import Path
import pytest

from backend.core.agent_society import AgentSociety
from backend.core.blackboard import BLACKBOARD
from backend.core.event_bus import EventBus, Event, EventName
from backend.core.goal_memory import GoalMemory
from backend.core.goal_manager import GoalManager
from backend.core.orchestrator import MultiAgentOrchestrator


@pytest.fixture(autouse=True)
def mock_env(monkeypatch, tmp_path):
    """Sets a temporary folder for files and databases to isolate tests."""
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: tmp_path)
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", str(tmp_path))

    GoalMemory._schema_ensured = False
    GoalMemory.reset()
    EventBus.reset()
    BLACKBOARD.clear()

    # Seed initial reputations into the isolated temp dir (guarantees clean baseline)
    AgentSociety.load_reputations()

    yield tmp_path

    EventBus.reset()
    BLACKBOARD.clear()


def test_orchestrate_high_confidence_no_debate():
    # HIGH confidence prompt with no keywords from other agents
    prompt = "code implement script compile generate refactor"
    
    events: list[Event] = []
    event_lock = threading.Event()

    def on_goal_completed(e: Event):
        events.append(e)
        event_lock.set()

    EventBus.subscribe(EventName.GOAL_COMPLETED, on_goal_completed)

    res = MultiAgentOrchestrator.orchestrate_goal(prompt, mode="BALANCED")

    assert res["status"] == "success"
    assert res["needs_debate"] is False
    assert "Builder" in res["agents"]

    # Verify Blackboard post
    posts = BLACKBOARD.get_history(topic="intent_assessment")
    assert len(posts) == 1
    assert posts[0].payload["prompt"] == prompt

    # Verify event delivery
    assert event_lock.wait(timeout=5.0), "GoalCompleted event not received"
    assert len(events) == 1
    assert events[0].payload["goal_id"] == res["goal_id"]

    # Verify reputation was boosted (Engineer successes should be seeded value + 1)
    reps = AgentSociety.load_reputations()
    assert reps["Engineer"]["successes"] == 22  # seeded=21, incremented once


def test_orchestrate_security_sensitive_triggers_debate_approval():
    # Coding prompt containing credentials triggers security sensitivity and a debate
    prompt = "code implement script compile generate refactor credentials"
    
    res = MultiAgentOrchestrator.orchestrate_goal(prompt, mode="BALANCED")

    # In default seeded reputations, debate should succeed (returns APPROVED)
    assert res["status"] == "success"
    assert res["needs_debate"] is True
    assert res["debate"]["consensus"] == "APPROVED"
    assert "Builder" in res["agents"]

    # Verify reputation update: each test gets a FRESH isolated tmp_path, so
    # Engineer starts at the seeded value (21) and gets exactly one success increment.
    reps = AgentSociety.load_reputations()
    assert reps["Engineer"]["successes"] >= 22  # seeded=21, incremented at least once


def test_orchestrate_failed_debate_degrades_reputations():
    # Coding prompt containing 'fail' and 'debate' triggers a debate and causes consensus to be REJECTED
    prompt = "code implement fail debate"
    
    res = MultiAgentOrchestrator.orchestrate_goal(prompt, mode="BALANCED")

    assert res["status"] == "failed"
    assert res["needs_debate"] is True
    assert res["debate"]["consensus"] == "REJECTED"

    # Verify reputation was degraded: failures should increment from seed (4) to at least 5
    reps = AgentSociety.load_reputations()
    assert reps["Engineer"]["failures"] >= 5  # seeded=4, degraded at least once
