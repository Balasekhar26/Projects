import pytest
import tempfile
import os
from backend.core.ledger.interfaces.clock import SystemClock, TestClock
from backend.core.ledger.interfaces.id_generator import UUIDGenerator, SequentialGenerator
from backend.core.ledger.interfaces.serializer import JSONSerializer
from backend.core.ledger.models.enums import EventType
from backend.core.ledger.models.payloads import GoalCreatedPayload, ToolExecutedPayload
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
    payload = GoalCreatedPayload(goal_id="g1", description="desc", priority=1.0, dependencies=[])
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
        payload={"goal_id": "g1"}
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
        payload={}
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
            payload={"goal_id": "g1"}
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
            payload={}
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
            state={"status": "active"}
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
        payload={"goal_id": "g1"}
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
        payload={}
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
