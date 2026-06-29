"""EventBus — Kattappa OS v2 Unified Event System.

Provides fully decoupled publish/subscribe communication between all cognitive
subsystems. Publishers never import subscribers; subscribers never import publishers.

Design constraints:
- Thread-safe: publishers and subscribers may live on different threads.
- Handler isolation: one misbehaving handler never kills others on the same event.
- Non-blocking publishers: handlers run in a daemon thread pool, never on the
  caller's thread.
- Ring buffer: last MAX_HISTORY events per topic kept for debug/replay.
- Ledger bridge: every published event writes a slim record to the execution
  ledger (SQLite) so the audit trail is complete.
- Zero external dependencies: pure stdlib only.

Registered event names (canonical; open to extension):
    GoalCreated, GoalUpdated, GoalCompleted, GoalFailed
    MemoryIngested, MemoryDecayed, MemoryPinned, BeliefUpdated
    PlannerStarted, PlannerFinished, PlannerBlocked
    SimulationStarted, SimulationFinished
    ExecutionStarted, ExecutionFinished, ExecutionFailed
    ReflectionCompleted, ReflectionProposal
    BlackboardOpened, BlackboardDestroyed
    WorldModelUpdated, CapabilityAssessed
    CognitiveStateChanged
    TelemetryRecorded
"""

from __future__ import annotations

import collections
import sqlite3
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from backend.core.config import runtime_data_root
from backend.core.logger import log_event


# ---------------------------------------------------------------------------
# Canonical event names (open registry — subsystems may publish any string)
# ---------------------------------------------------------------------------

class EventName:
    GOAL_CREATED             = "GoalCreated"
    GOAL_UPDATED             = "GoalUpdated"
    GOAL_COMPLETED           = "GoalCompleted"
    GOAL_FAILED              = "GoalFailed"
    MEMORY_INGESTED          = "MemoryIngested"
    MEMORY_DECAYED           = "MemoryDecayed"
    MEMORY_PINNED            = "MemoryPinned"
    BELIEF_UPDATED           = "BeliefUpdated"
    PLANNER_STARTED          = "PlannerStarted"
    PLANNER_FINISHED         = "PlannerFinished"
    PLANNER_BLOCKED          = "PlannerBlocked"
    SIMULATION_STARTED       = "SimulationStarted"
    SIMULATION_FINISHED      = "SimulationFinished"
    EXECUTION_STARTED        = "ExecutionStarted"
    EXECUTION_FINISHED       = "ExecutionFinished"
    EXECUTION_FAILED         = "ExecutionFailed"
    REFLECTION_COMPLETED     = "ReflectionCompleted"
    REFLECTION_PROPOSAL      = "ReflectionProposal"
    BLACKBOARD_OPENED        = "BlackboardOpened"
    BLACKBOARD_DESTROYED     = "BlackboardDestroyed"
    WORLD_MODEL_UPDATED      = "WorldModelUpdated"
    CAPABILITY_ASSESSED      = "CapabilityAssessed"
    COGNITIVE_STATE_CHANGED  = "CognitiveStateChanged"
    TELEMETRY_RECORDED       = "TelemetryRecorded"


# ---------------------------------------------------------------------------
# Event payload
# ---------------------------------------------------------------------------

class Event:
    """Immutable event payload published on the bus."""

    __slots__ = ("id", "name", "payload", "published_at", "source")

    def __init__(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
        source: str = "unknown",
    ) -> None:
        self.id = uuid.uuid4().hex[:16]
        self.name = name
        self.payload: dict[str, Any] = dict(payload or {})
        self.published_at = time.time()
        self.source = source

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "payload": self.payload,
            "published_at": self.published_at,
            "source": self.source,
        }

    def __repr__(self) -> str:
        return f"<Event {self.name} id={self.id} src={self.source}>"


# ---------------------------------------------------------------------------
# Handler type
# ---------------------------------------------------------------------------

Handler = Callable[[Event], None]


# ---------------------------------------------------------------------------
# Ledger bridge (lightweight SQLite write, separate from goal_memory.db)
# ---------------------------------------------------------------------------

_LEDGER_LOCK = threading.Lock()
_ledger_conn: sqlite3.Connection | None = None


def _ledger_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "event_ledger.db"


def _get_ledger() -> sqlite3.Connection:
    global _ledger_conn
    if _ledger_conn is not None:
        return _ledger_conn
    p = _ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_ledger (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            source      TEXT NOT NULL,
            published_at REAL NOT NULL,
            payload_keys TEXT NOT NULL
        )
    """)
    conn.commit()
    _ledger_conn = conn
    return conn


def _write_ledger(event: Event) -> None:
    """Persist a slim ledger record (keys only, not values, to avoid PII bloat)."""
    try:
        with _LEDGER_LOCK:
            conn = _get_ledger()
            keys = ",".join(sorted(event.payload.keys()))
            conn.execute(
                "INSERT OR IGNORE INTO event_ledger (id, name, source, published_at, payload_keys) "
                "VALUES (?, ?, ?, ?, ?)",
                (event.id, event.name, event.source, event.published_at, keys),
            )
            conn.commit()
    except Exception as exc:
        log_event(f"EventBus ledger write failed: {exc}")


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

MAX_HISTORY = 1000
_MAX_WORKERS = 4


class EventBus:
    """Thread-safe, non-blocking publish/subscribe event bus.

    Usage::

        # Subscribe
        EventBus.subscribe("GoalCreated", my_handler)

        # Publish (non-blocking — handler runs in thread pool)
        EventBus.publish("GoalCreated", {"goal_id": "g1"}, source="GoalManager")

        # History
        events = EventBus.history("GoalCreated", limit=10)
    """

    _lock: threading.RLock = threading.RLock()
    _subscribers: dict[str, list[Handler]] = collections.defaultdict(list)
    _history: dict[str, collections.deque[Event]] = collections.defaultdict(
        lambda: collections.deque(maxlen=MAX_HISTORY)
    )
    _global_history: collections.deque[Event] = collections.deque(maxlen=MAX_HISTORY)
    _pool: ThreadPoolExecutor = ThreadPoolExecutor(
        max_workers=_MAX_WORKERS, thread_name_prefix="event_bus"
    )
    _total_published: int = 0
    _total_delivered: int = 0
    _total_errors: int = 0

    # -- subscribe ----------------------------------------------------------

    @classmethod
    def subscribe(cls, event_name: str, handler: Handler) -> None:
        """Register *handler* to be called whenever *event_name* is published.

        A handler must accept a single positional argument (an Event).
        The same handler may be registered multiple times; each registration
        results in one additional call per publish.
        """
        with cls._lock:
            cls._subscribers[event_name].append(handler)

    @classmethod
    def unsubscribe(cls, event_name: str, handler: Handler) -> bool:
        """Remove the first matching handler registration. Returns True if removed."""
        with cls._lock:
            subs = cls._subscribers.get(event_name, [])
            try:
                subs.remove(handler)
                return True
            except ValueError:
                return False

    @classmethod
    def subscriber_count(cls, event_name: str) -> int:
        with cls._lock:
            return len(cls._subscribers.get(event_name, []))

    # -- publish ------------------------------------------------------------

    @classmethod
    def publish(
        cls,
        event_name: str,
        payload: dict[str, Any] | None = None,
        *,
        source: str = "unknown",
    ) -> Event:
        """Publish an event. Handlers run asynchronously in a thread pool.

        This method returns immediately after submitting handlers to the pool.
        It never raises even if all handlers fail.
        """
        event = Event(name=event_name, payload=payload, source=source)

        with cls._lock:
            cls._total_published += 1
            cls._history[event_name].append(event)
            cls._global_history.append(event)
            handlers = list(cls._subscribers.get(event_name, []))

        # Write ledger (in pool to keep publish non-blocking)
        cls._pool.submit(_write_ledger, event)

        # Dispatch to each handler in isolation
        for handler in handlers:
            cls._pool.submit(cls._safe_call, handler, event)

        return event

    @classmethod
    def publish_sync(
        cls,
        event_name: str,
        payload: dict[str, Any] | None = None,
        *,
        source: str = "unknown",
    ) -> Event:
        """Publish an event and wait for all handlers to complete.

        Useful in tests and situations where ordering guarantees are needed.
        """
        event = Event(name=event_name, payload=payload, source=source)

        with cls._lock:
            cls._total_published += 1
            cls._history[event_name].append(event)
            cls._global_history.append(event)
            handlers = list(cls._subscribers.get(event_name, []))

        _write_ledger(event)
        futures = [cls._pool.submit(cls._safe_call, h, event) for h in handlers]
        for f in futures:
            f.result()  # wait for completion

        return event

    @classmethod
    def _safe_call(cls, handler: Handler, event: Event) -> None:
        try:
            handler(event)
            with cls._lock:
                cls._total_delivered += 1
        except Exception:
            with cls._lock:
                cls._total_errors += 1
            log_event(
                f"EventBus handler error on {event.name}: "
                + traceback.format_exc().splitlines()[-1]
            )

    # -- history ------------------------------------------------------------

    @classmethod
    def history(cls, event_name: str | None = None, limit: int = 50) -> list[Event]:
        """Return recent events, newest last."""
        with cls._lock:
            if event_name is None:
                items = list(cls._global_history)
            else:
                items = list(cls._history.get(event_name, []))
        return items[-limit:]

    @classmethod
    def history_dicts(cls, event_name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return [e.to_dict() for e in cls.history(event_name, limit)]

    # -- stats --------------------------------------------------------------

    @classmethod
    def stats(cls) -> dict[str, Any]:
        with cls._lock:
            return {
                "total_published": cls._total_published,
                "total_delivered": cls._total_delivered,
                "total_errors": cls._total_errors,
                "registered_topics": len(cls._subscribers),
                "history_size": len(cls._global_history),
            }

    # -- reset (tests only) ------------------------------------------------

    @classmethod
    def reset(cls) -> None:
        """Clear all subscribers and history. For test isolation only."""
        with cls._lock:
            cls._subscribers.clear()
            cls._history.clear()
            cls._global_history.clear()
            cls._total_published = 0
            cls._total_delivered = 0
            cls._total_errors = 0

    # -- ledger query -------------------------------------------------------

    @classmethod
    def ledger_query(
        cls,
        event_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query the persistent event ledger."""
        try:
            with _LEDGER_LOCK:
                conn = _get_ledger()
                if event_name:
                    rows = conn.execute(
                        "SELECT * FROM event_ledger WHERE name=? ORDER BY published_at DESC LIMIT ?",
                        (event_name, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM event_ledger ORDER BY published_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            log_event(f"EventBus ledger_query failed: {exc}")
            return []


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def subscribe(event_name: str, handler: Handler) -> None:
    EventBus.subscribe(event_name, handler)


def publish(
    event_name: str,
    payload: dict[str, Any] | None = None,
    *,
    source: str = "unknown",
) -> Event:
    return EventBus.publish(event_name, payload, source=source)
