from typing import Any
from backend.core.ledger.interfaces.ledger_store import LedgerStore
from backend.core.ledger.interfaces.reducer import Reducer


class ReplayEngine:
    def __init__(self, store: LedgerStore) -> None:
        self.store = store

    def replay(self, goal_id: str, reducer: Reducer, initial_state: Any = None) -> Any:
        """Replays all events for the target goal from the beginning, returning the reconstructed state."""
        events = self.store.query({"goal_id": goal_id})
        # Sort chronologically by timestamp
        events.sort(key=lambda e: e.timestamp_utc)

        state = initial_state if initial_state is not None else {}
        for event in events:
            state = reducer.reduce(state, event)
        return state
