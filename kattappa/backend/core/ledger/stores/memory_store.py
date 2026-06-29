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

    def ancestors(self, event_id: str) -> List[LedgerEvent]:
        with self._lock:
            visited = set()
            ancestor_events = []

            def dfs(eid: str) -> None:
                event = None
                for e in self._events:
                    if e.event_id == eid:
                        event = e
                        break
                if not event:
                    return
                for pid in event.parent_event_ids:
                    if pid not in visited:
                        visited.add(pid)
                        pevent = None
                        for e in self._events:
                            if e.event_id == pid:
                                pevent = e
                                break
                        if pevent:
                            ancestor_events.append(pevent)
                        dfs(pid)

            dfs(event_id)
            ancestor_events.sort(key=lambda x: x.timestamp_utc)
            return ancestor_events

    def descendants(self, event_id: str) -> List[LedgerEvent]:
        with self._lock:
            visited = set()
            descendant_events = []

            def dfs(eid: str) -> None:
                children_events = [e for e in self._events if eid in e.parent_event_ids]
                for child in children_events:
                    if child.event_id not in visited:
                        visited.add(child.event_id)
                        descendant_events.append(child)
                        dfs(child.event_id)

            dfs(event_id)
            descendant_events.sort(key=lambda x: x.timestamp_utc)
            return descendant_events

    def query(self, filters: Dict[str, Any]) -> List[LedgerEvent]:
        from backend.core.ledger.models.enums import EventType

        with self._lock:
            results = list(self._events)
            for key, val in filters.items():
                if not results:
                    break
                if key == "event_type":
                    if isinstance(val, EventType):
                        results = [e for e in results if e.event_type == val]
                    else:
                        results = [e for e in results if e.event_type.value == val]
                elif key == "min_confidence":
                    results = [e for e in results if e.confidence >= val]
                elif key == "max_confidence":
                    results = [e for e in results if e.confidence <= val]
                elif key == "start_time":
                    results = [e for e in results if e.timestamp_utc >= val]
                elif key == "end_time":
                    results = [e for e in results if e.timestamp_utc <= val]
                elif key == "metadata":
                    if isinstance(val, dict):
                        results = [
                            e
                            for e in results
                            if all(e.metadata.get(mk) == mv for mk, mv in val.items())
                        ]
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
