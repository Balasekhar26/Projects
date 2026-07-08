import pytest
import tempfile
import os
from backend.core.ledger.interfaces.clock import SystemClock, TestClock
from backend.core.ledger.interfaces.id_generator import (
    UUIDGenerator,
    SequentialGenerator,
)
from backend.core.ledger.interfaces.serializer import JSONSerializer
from backend.core.ledger.models.enums import EventType
from backend.core.ledger.models.payloads import GoalCreatedPayload
from backend.core.ledger.models.event import LedgerEvent
from backend.core.ledger.models.snapshot import LedgerSnapshot
from backend.core.ledger.stores.memory_store import MemoryLedgerStore
from backend.core.ledger.stores.sqlite_store import SQLiteLedgerStore
from backend.core.ledger.interfaces.reducer import Reducer


def test_clocks():
    sys_clock = SystemClock()
    assert sys_clock.now_utc() > 0

    test_clock = TestClock(100.0)
    assert test_clock.now_utc() == 100.0
    test_clock.advance(50.0)
    assert test_clock.now_utc() == 150.0


def test_id_generators():
    uuid_gen = UUIDGenerator()
    id1 = uuid_gen.generate_id()
    id2 = uuid_gen.generate_id()
    assert id1 != id2
    assert len(id1) > 10

    seq_gen = SequentialGenerator(prefix="test-", start=10)
    assert seq_gen.generate_id() == "test-10"
    assert seq_gen.generate_id() == "test-11"


def test_serializer():
    serializer = JSONSerializer()
    payload = GoalCreatedPayload(
        goal_id="g1", description="desc", priority=1.0, dependencies=[]
    )
    serialized = serializer.serialize(payload)
    assert "g1" in serialized
    deserialized = serializer.deserialize(serialized, GoalCreatedPayload)
    assert deserialized.goal_id == "g1"
    assert deserialized.description == "desc"
    assert deserialized.priority == 1.0


def test_memory_store():
    store = MemoryLedgerStore()
    event = LedgerEvent(
        event_id="e1",
        parent_event_ids=[],
        goal_id="g1",
        session_id="s1",
        correlation_id="c1",
        timestamp_utc=12345.0,
        actor="user",
        subsystem="scheduler",
        event_type=EventType.GOAL_CREATED,
        payload={"goal_id": "g1"},
    )
    store.append(event)

    # Double append raises ValueError
    with pytest.raises(ValueError):
        store.append(event)

    assert store.get("e1") == event
    assert store.get("e2") is None

    # Test children/parents
    child_event = LedgerEvent(
        event_id="e2",
        parent_event_ids=["e1"],
        goal_id="g1",
        session_id="s1",
        correlation_id="c1",
        timestamp_utc=12346.0,
        actor="system",
        subsystem="planner",
        event_type=EventType.PLAN_GENERATED,
        payload={},
    )
    store.append(child_event)

    assert store.children("e1") == [child_event]
    assert store.parents("e2") == [event]

    # Test query
    assert store.query({"actor": "user"}) == [event]
    assert store.query({"event_type": "PlanGenerated"}) == [child_event]


def test_sqlite_store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        store = SQLiteLedgerStore(db_path)
        event = LedgerEvent(
            event_id="e1",
            parent_event_ids=[],
            goal_id="g1",
            session_id="s1",
            correlation_id="c1",
            timestamp_utc=12345.0,
            actor="user",
            subsystem="scheduler",
            event_type=EventType.GOAL_CREATED,
            payload={"goal_id": "g1"},
        )
        store.append(event)

        with pytest.raises(ValueError):
            store.append(event)

        assert store.get("e1") == event

        child_event = LedgerEvent(
            event_id="e2",
            parent_event_ids=["e1"],
            goal_id="g1",
            session_id="s1",
            correlation_id="c1",
            timestamp_utc=12346.0,
            actor="system",
            subsystem="planner",
            event_type=EventType.PLAN_GENERATED,
            payload={},
        )
        store.append(child_event)

        assert store.children("e1") == [child_event]
        assert store.parents("e2") == [event]

        # Test query
        assert store.query({"actor": "user"}) == [event]
        assert store.query({"event_type": EventType.PLAN_GENERATED}) == [child_event]

        # Test snapshots
        snapshot = LedgerSnapshot(
            snapshot_id="snap1",
            goal_id="g1",
            last_event_id="e2",
            timestamp_utc=99999.0,
            state={"status": "active"},
        )
        store.save_snapshot(snapshot)
        latest = store.get_latest_snapshot("g1")
        assert latest == snapshot
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


class SimpleGoalReducer(Reducer):
    def reduce(self, state: dict, event: LedgerEvent) -> dict:
        if event.event_type == EventType.GOAL_CREATED:
            state["goal_id"] = event.payload["goal_id"]
            state["status"] = "created"
        elif event.event_type == EventType.PLAN_GENERATED:
            state["status"] = "planned"
        return state


def test_simple_replay():
    store = MemoryLedgerStore()
    event1 = LedgerEvent(
        event_id="e1",
        parent_event_ids=[],
        goal_id="g1",
        session_id="s1",
        correlation_id="c1",
        timestamp_utc=100.0,
        actor="user",
        subsystem="scheduler",
        event_type=EventType.GOAL_CREATED,
        payload={"goal_id": "g1"},
    )
    event2 = LedgerEvent(
        event_id="e2",
        parent_event_ids=["e1"],
        goal_id="g1",
        session_id="s1",
        correlation_id="c1",
        timestamp_utc=101.0,
        actor="system",
        subsystem="planner",
        event_type=EventType.PLAN_GENERATED,
        payload={},
    )
    store.append(event1)
    store.append(event2)

    reducer = SimpleGoalReducer()
    state = {}
    events = store.query({"goal_id": "g1"})
    # Sort events by timestamp to ensure correct order
    events.sort(key=lambda e: e.timestamp_utc)
    for e in events:
        state = reducer.reduce(state, e)

    assert state["goal_id"] == "g1"
    assert state["status"] == "planned"


def test_transitive_queries_and_filters():
    # Test on both memory and SQLite stores
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        stores = [MemoryLedgerStore(), SQLiteLedgerStore(db_path)]
        for store in stores:
            # Create a chain: e1 -> e2 -> e3
            # Also e1 -> e4 (branch)
            e1 = LedgerEvent(
                event_id="e1",
                parent_event_ids=[],
                goal_id="g1",
                session_id="s1",
                correlation_id="c1",
                timestamp_utc=100.0,
                actor="user",
                subsystem="scheduler",
                event_type=EventType.GOAL_CREATED,
                payload={},
                confidence=1.0,
                metadata={"env": "prod"},
            )
            e2 = LedgerEvent(
                event_id="e2",
                parent_event_ids=["e1"],
                goal_id="g1",
                session_id="s1",
                correlation_id="c1",
                timestamp_utc=101.0,
                actor="system",
                subsystem="planner",
                event_type=EventType.PLAN_GENERATED,
                payload={},
                confidence=0.8,
                metadata={"env": "prod", "tier": "A"},
            )
            e3 = LedgerEvent(
                event_id="e3",
                parent_event_ids=["e2"],
                goal_id="g1",
                session_id="s1",
                correlation_id="c1",
                timestamp_utc=102.0,
                actor="system",
                subsystem="agent",
                event_type=EventType.TOOL_COMPLETED,
                payload={},
                confidence=0.5,
                metadata={"env": "staging"},
            )
            e4 = LedgerEvent(
                event_id="e4",
                parent_event_ids=["e1"],
                goal_id="g1",
                session_id="s1",
                correlation_id="c1",
                timestamp_utc=103.0,
                actor="system",
                subsystem="agent",
                event_type=EventType.TOOL_COMPLETED,
                payload={},
                confidence=0.9,
                metadata={"env": "prod"},
            )

            store.append(e1)
            store.append(e2)
            store.append(e3)
            store.append(e4)

            # Test ancestors
            assert store.ancestors("e1") == []
            assert store.ancestors("e2") == [e1]
            assert store.ancestors("e3") == [e1, e2]
            assert store.ancestors("e4") == [e1]

            # Test descendants
            assert store.descendants("e3") == []
            assert store.descendants("e2") == [e3]
            assert store.descendants("e1") == [e2, e3, e4]

            # Test query filters
            # 1. confidence ranges
            assert store.query({"min_confidence": 0.8}) == [e1, e2, e4]
            assert store.query({"max_confidence": 0.8}) == [e2, e3]
            # 2. timestamp ranges
            assert store.query({"start_time": 101.0, "end_time": 102.0}) == [e2, e3]
            # 3. metadata
            assert store.query({"metadata": {"env": "prod"}}) == [e1, e2, e4]
            assert store.query({"metadata": {"env": "prod", "tier": "A"}}) == [e2]
            assert store.query({"metadata": {"env": "staging"}}) == [e3]
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_replay_and_snapshot_recovery():
    from backend.core.ledger.replay.snapshot_manager import SnapshotManager

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        stores = [MemoryLedgerStore(), SQLiteLedgerStore(db_path)]
        for store in stores:
            clock = TestClock(100.0)
            id_gen = SequentialGenerator(prefix="snap-", start=1)
            manager = SnapshotManager(store, id_gen, clock)

            # 1. Append initial events
            e1 = LedgerEvent(
                event_id="e1",
                parent_event_ids=[],
                goal_id="g2",
                session_id="s1",
                correlation_id="c1",
                timestamp_utc=100.0,
                actor="user",
                subsystem="scheduler",
                event_type=EventType.GOAL_CREATED,
                payload={"goal_id": "g2"},
            )
            e2 = LedgerEvent(
                event_id="e2",
                parent_event_ids=["e1"],
                goal_id="g2",
                session_id="s1",
                correlation_id="c1",
                timestamp_utc=101.0,
                actor="system",
                subsystem="planner",
                event_type=EventType.PLAN_GENERATED,
                payload={},
            )
            store.append(e1)
            store.append(e2)

            # 2. Replay all from start
            reducer = SimpleGoalReducer()
            state = manager.replay_engine.replay("g2", reducer)
            assert state == {"goal_id": "g2", "status": "planned"}

            # 3. Take snapshot at e2
            snap = manager.take_snapshot("g2", state, "e2")
            assert snap.snapshot_id == "snap-1"
            assert snap.state == {"goal_id": "g2", "status": "planned"}

            # 4. Append subsequent events after snapshot
            e3 = LedgerEvent(
                event_id="e3",
                parent_event_ids=["e2"],
                goal_id="g2",
                session_id="s1",
                correlation_id="c1",
                timestamp_utc=102.0,
                actor="system",
                subsystem="scheduler",
                event_type=EventType.GOAL_CREATED,
                payload={"goal_id": "g2"},
            )
            store.append(e3)

            # 5. Recover using snapshot + subsequent events
            recovered_state = manager.recover("g2", reducer)
            assert recovered_state == {"goal_id": "g2", "status": "created"}
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
