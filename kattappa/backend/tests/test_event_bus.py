"""Tests for backend/core/event_bus.py"""
from __future__ import annotations

import threading
import time
import pytest

from backend.core.event_bus import EventBus, Event, EventName


@pytest.fixture(autouse=True)
def clean_bus():
    EventBus.reset()
    yield
    EventBus.reset()


# ---------------------------------------------------------------------------
# Basic subscribe / publish
# ---------------------------------------------------------------------------

def test_subscribe_and_receive():
    received: list[Event] = []
    EventBus.subscribe(EventName.GOAL_CREATED, received.append)
    EventBus.publish_sync(EventName.GOAL_CREATED, {"goal_id": "g1"}, source="test")
    assert len(received) == 1
    assert received[0].name == EventName.GOAL_CREATED
    assert received[0].payload["goal_id"] == "g1"
    assert received[0].source == "test"


def test_publish_returns_event():
    event = EventBus.publish_sync(EventName.MEMORY_INGESTED, {"text": "hello"}, source="hce")
    assert isinstance(event, Event)
    assert event.name == EventName.MEMORY_INGESTED
    assert len(event.id) == 16


def test_multiple_subscribers_same_event():
    a: list[Event] = []
    b: list[Event] = []
    EventBus.subscribe(EventName.PLANNER_FINISHED, a.append)
    EventBus.subscribe(EventName.PLANNER_FINISHED, b.append)
    EventBus.publish_sync(EventName.PLANNER_FINISHED, {"blueprint_id": "bp1"}, source="planner")
    assert len(a) == 1
    assert len(b) == 1


def test_different_events_dont_cross():
    goal_events: list[Event] = []
    memory_events: list[Event] = []
    EventBus.subscribe(EventName.GOAL_CREATED, goal_events.append)
    EventBus.subscribe(EventName.MEMORY_INGESTED, memory_events.append)
    EventBus.publish_sync(EventName.GOAL_CREATED, {}, source="test")
    EventBus.publish_sync(EventName.MEMORY_INGESTED, {}, source="test")
    assert len(goal_events) == 1
    assert len(memory_events) == 1


def test_no_subscribers_publish_is_safe():
    # Should not raise
    event = EventBus.publish_sync(EventName.TELEMETRY_RECORDED, {"metric": "ok"}, source="tel")
    assert event.name == EventName.TELEMETRY_RECORDED


# ---------------------------------------------------------------------------
# Handler isolation
# ---------------------------------------------------------------------------

def test_bad_handler_does_not_kill_good_handler():
    """A handler that raises must not prevent other handlers from running."""
    good: list[Event] = []

    def bad_handler(e: Event) -> None:
        raise RuntimeError("Intentional test error")

    EventBus.subscribe(EventName.EXECUTION_STARTED, bad_handler)
    EventBus.subscribe(EventName.EXECUTION_STARTED, good.append)
    EventBus.publish_sync(EventName.EXECUTION_STARTED, {}, source="executor")

    assert len(good) == 1  # good handler still received the event


def test_error_counter_increments():
    def bad(e: Event) -> None:
        raise ValueError("oops")

    EventBus.subscribe(EventName.EXECUTION_FAILED, bad)
    EventBus.publish_sync(EventName.EXECUTION_FAILED, {}, source="executor")
    stats = EventBus.stats()
    assert stats["total_errors"] >= 1


# ---------------------------------------------------------------------------
# History / ring buffer
# ---------------------------------------------------------------------------

def test_history_per_topic():
    EventBus.publish_sync(EventName.GOAL_CREATED, {"i": 1}, source="test")
    EventBus.publish_sync(EventName.GOAL_CREATED, {"i": 2}, source="test")
    EventBus.publish_sync(EventName.BELIEF_UPDATED, {"key": "x"}, source="test")

    goal_hist = EventBus.history(EventName.GOAL_CREATED)
    belief_hist = EventBus.history(EventName.BELIEF_UPDATED)
    assert len(goal_hist) == 2
    assert len(belief_hist) == 1


def test_global_history():
    EventBus.publish_sync(EventName.PLANNER_STARTED, {}, source="test")
    EventBus.publish_sync(EventName.SIMULATION_STARTED, {}, source="test")
    all_hist = EventBus.history(limit=100)
    names = [e.name for e in all_hist]
    assert EventName.PLANNER_STARTED in names
    assert EventName.SIMULATION_STARTED in names


def test_history_limit():
    for i in range(10):
        EventBus.publish_sync(EventName.TELEMETRY_RECORDED, {"i": i}, source="test")
    hist = EventBus.history(EventName.TELEMETRY_RECORDED, limit=3)
    assert len(hist) == 3
    # newest last
    assert hist[-1].payload["i"] == 9


def test_history_dicts_serializable():
    EventBus.publish_sync(EventName.WORLD_MODEL_UPDATED, {"entity": "proj"}, source="wm")
    dicts = EventBus.history_dicts(EventName.WORLD_MODEL_UPDATED)
    assert isinstance(dicts[0], dict)
    assert "id" in dicts[0]
    assert "published_at" in dicts[0]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def test_stats_increments():
    EventBus.publish_sync(EventName.REFLECTION_COMPLETED, {}, source="reflection")
    EventBus.publish_sync(EventName.REFLECTION_COMPLETED, {}, source="reflection")
    stats = EventBus.stats()
    assert stats["total_published"] == 2


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------

def test_unsubscribe():
    received: list[Event] = []
    EventBus.subscribe(EventName.GOAL_FAILED, received.append)
    EventBus.publish_sync(EventName.GOAL_FAILED, {}, source="test")
    assert len(received) == 1

    removed = EventBus.unsubscribe(EventName.GOAL_FAILED, received.append)
    assert removed
    EventBus.publish_sync(EventName.GOAL_FAILED, {}, source="test")
    assert len(received) == 1  # no new event after unsubscribe


def test_unsubscribe_nonexistent_returns_false():
    result = EventBus.unsubscribe(EventName.GOAL_CREATED, lambda e: None)
    assert result is False


# ---------------------------------------------------------------------------
# Async publish (non-blocking)
# ---------------------------------------------------------------------------

def test_async_publish_eventually_delivers():
    received: list[Event] = []
    lock = threading.Event()

    def handler(e: Event) -> None:
        received.append(e)
        lock.set()

    EventBus.subscribe(EventName.COGNITIVE_STATE_CHANGED, handler)
    EventBus.publish(EventName.COGNITIVE_STATE_CHANGED, {"state": "PLAN"}, source="csm")

    delivered = lock.wait(timeout=2.0)
    assert delivered, "Handler was not called within timeout"
    assert len(received) == 1


# ---------------------------------------------------------------------------
# Ledger persistence
# ---------------------------------------------------------------------------

def test_ledger_records_events():
    EventBus.publish_sync(EventName.CAPABILITY_ASSESSED, {"cap": "code_execution"}, source="reasoning")
    time.sleep(0.05)  # allow ledger write
    records = EventBus.ledger_query(EventName.CAPABILITY_ASSESSED, limit=5)
    assert len(records) >= 1
    assert records[0]["name"] == EventName.CAPABILITY_ASSESSED
    assert records[0]["source"] == "reasoning"


def test_ledger_stores_only_keys_not_values():
    """PII protection: ledger stores payload keys, not values."""
    EventBus.publish_sync(
        EventName.MEMORY_INGESTED,
        {"user_text": "this is private", "session_id": "s1"},
        source="broker",
    )
    time.sleep(0.05)
    records = EventBus.ledger_query(EventName.MEMORY_INGESTED, limit=5)
    if records:
        keys_field = records[0]["payload_keys"]
        assert "session_id" in keys_field
        assert "this is private" not in keys_field


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

def test_event_to_dict():
    e = Event("TestEvent", {"a": 1}, source="src")
    d = e.to_dict()
    assert d["name"] == "TestEvent"
    assert d["payload"]["a"] == 1
    assert d["source"] == "src"
    assert "published_at" in d
    assert len(d["id"]) == 16
