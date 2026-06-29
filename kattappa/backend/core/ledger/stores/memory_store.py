import threading
from typing import List, Optional, Dict, Any
from backend.core.ledger.interfaces.ledger_store import LedgerStore
from backend.core.ledger.models.event import LedgerEvent
from backend.core.ledger.models.snapshot import LedgerSnapshot


class MemoryLedgerStore(LedgerStore):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: List[LedgerEvent] = []
        self._snapshots: Dict[str, List[LedgerSnapshot]] = {}

    def append(self, event: LedgerEvent) -> None:
        with self._lock:
            if any(e.event_id == event.event_id for e in self._events):
                raise ValueError(f"Event with ID {event.event_id} already exists.")
            self._events.append(event)

    def get(self, event_id: str) -> Optional[LedgerEvent]:
        with self._lock:
            for event in self._events:
                if event.event_id == event_id:
                    return event
            return None

    def children(self, event_id: str) -> List[LedgerEvent]:
        with self._lock:
            return [e for e in self._events if event_id in e.parent_event_ids]

    def parents(self, event_id: str) -> List[LedgerEvent]:
        with self._lock:
            target = None
            for e in self._events:
                if e.event_id == event_id:
                    target = e
                    break
            if not target:
                return []
            return [e for e in self._events if e.event_id in target.parent_event_ids]

    def query(self, filters: Dict[str, Any]) -> List[LedgerEvent]:
        with self._lock:
            results = list(self._events)
            for key, val in filters.items():
                if not results:
                    break
                if key == "event_type" and isinstance(val, str):
                    results = [e for e in results if e.event_type.value == val]
                else:
                    results = [e for e in results if getattr(e, key, None) == val]
            return results

    def save_snapshot(self, snapshot: LedgerSnapshot) -> None:
        with self._lock:
            self._snapshots.setdefault(snapshot.goal_id, []).append(snapshot)

    def get_latest_snapshot(self, goal_id: str) -> Optional[LedgerSnapshot]:
        with self._lock:
            snaps = self._snapshots.get(goal_id, [])
            if not snaps:
                return None
            return sorted(snaps, key=lambda s: s.timestamp_utc, reverse=True)[0]
