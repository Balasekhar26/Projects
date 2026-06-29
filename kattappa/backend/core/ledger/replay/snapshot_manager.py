from typing import Any
from backend.core.ledger.interfaces.ledger_store import LedgerStore
from backend.core.ledger.interfaces.reducer import Reducer
from backend.core.ledger.interfaces.id_generator import IdGenerator
from backend.core.ledger.interfaces.clock import Clock
from backend.core.ledger.models.snapshot import LedgerSnapshot
from backend.core.ledger.replay.replay_engine import ReplayEngine


class SnapshotManager:
    def __init__(self, store: LedgerStore, id_gen: IdGenerator, clock: Clock) -> None:
        self.store = store
        self.id_gen = id_gen
        self.clock = clock
        self.replay_engine = ReplayEngine(store)

    def take_snapshot(
        self, goal_id: str, current_state: Any, last_event_id: str
    ) -> LedgerSnapshot:
        """Saves a snapshot of the goal state directly."""
        snapshot = LedgerSnapshot(
            snapshot_id=self.id_gen.generate_id(),
            goal_id=goal_id,
            last_event_id=last_event_id,
            timestamp_utc=self.clock.now_utc(),
            state=current_state,
        )
        self.store.save_snapshot(snapshot)
        return snapshot

    def recover(self, goal_id: str, reducer: Reducer) -> Any:
        """Recovers goal state by loading the latest snapshot and replaying subsequent events from that point forward."""
        snapshot = self.store.get_latest_snapshot(goal_id)
        if not snapshot:
            return self.replay_engine.replay(goal_id, reducer)

        state = snapshot.state
        all_events = self.store.query({"goal_id": goal_id})
        last_event = self.store.get(snapshot.last_event_id)
        if not last_event:
            return self.replay_engine.replay(goal_id, reducer)

        subsequent_events = [
            e for e in all_events if e.timestamp_utc > last_event.timestamp_utc
        ]
        subsequent_events.sort(key=lambda e: e.timestamp_utc)

        for event in subsequent_events:
            state = reducer.reduce(state, event)

        return state
