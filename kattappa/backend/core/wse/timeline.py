"""WSE Component 3: Timeline Query API.

Provides temporal queries over the LedgerStore:
  - at(timestamp)             → reconstruct world state at a point in time
  - between(t_start, t_end)   → events in a time window
  - history_of(entity_id)     → all state transitions for an entity
  - last_observation_of(...)  → most recent observed value for a predicate
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from backend.core.ledger.interfaces.ledger_store import LedgerStore
from backend.core.ledger.models.enums import EventType
from backend.core.ledger.models.event import LedgerEvent
from backend.core.wse.observation import Observation
from backend.core.wse.state_transition import StateTransition

logger = logging.getLogger(__name__)


class WSETimeline:
    """Temporal query interface over the WSE LedgerStore."""

    def __init__(self, store: LedgerStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Core queries
    # ------------------------------------------------------------------

    def between(
        self,
        t_start: float,
        t_end: float,
        event_type: Optional[EventType] = None,
    ) -> List[LedgerEvent]:
        """Returns all events in [t_start, t_end] ordered chronologically."""
        filters: Dict[str, Any] = {"start_time": t_start, "end_time": t_end}
        if event_type is not None:
            filters["event_type"] = event_type
        events = self._store.query(filters)
        events.sort(key=lambda e: e.timestamp_utc)
        return events

    def at(self, timestamp: float) -> Dict[str, Any]:
        """Reconstructs the world state at the given timestamp.

        Returns a dict: {entity_id → latest_state_at_or_before_timestamp}.
        Uses STATE_TRANSITIONED events to rebuild entity states.
        """
        events = self._store.query({
            "event_type": EventType.STATE_TRANSITIONED,
            "end_time": timestamp,
        })
        events.sort(key=lambda e: e.timestamp_utc)

        world_state: Dict[str, Any] = {}
        for event in events:
            payload = event.payload
            entity_id = payload.get("entity_id", "")
            if entity_id:
                world_state[entity_id] = payload.get("to_state", {})
        return world_state

    def history_of(self, entity_id: str) -> List[StateTransition]:
        """Returns all StateTransitions for the given entity, oldest first."""
        events = self._store.query({"event_type": EventType.STATE_TRANSITIONED})
        transitions = []
        for event in events:
            if event.payload.get("entity_id") == entity_id:
                try:
                    transitions.append(StateTransition.from_dict(event.payload))
                except Exception as exc:
                    logger.debug("WSETimeline: skipping malformed transition: %s", exc)
        transitions.sort(key=lambda t: t.transitioned_at)
        return transitions

    def last_observation_of(
        self, subject: str, predicate: str
    ) -> Optional[Observation]:
        """Returns the most recent Observation for a given subject + predicate."""
        events = self._store.query({"event_type": EventType.OBSERVATION_RECORDED})
        candidates = []
        for event in events:
            payload = event.payload
            if payload.get("subject") == subject and payload.get("predicate") == predicate:
                try:
                    candidates.append(Observation.from_dict(payload))
                except Exception as exc:
                    logger.debug("WSETimeline: skipping malformed observation: %s", exc)
        if not candidates:
            return None
        return max(candidates, key=lambda o: o.observed_at)

    def observations_between(
        self,
        t_start: float,
        t_end: float,
        subject: Optional[str] = None,
    ) -> List[Observation]:
        """Returns all observations in a time window, optionally filtered by subject."""
        events = self.between(t_start, t_end, event_type=EventType.OBSERVATION_RECORDED)
        obs_list = []
        for event in events:
            payload = event.payload
            if subject and payload.get("subject") != subject:
                continue
            try:
                obs_list.append(Observation.from_dict(payload))
            except Exception:
                pass
        return obs_list
