"""WSE Component 6: WSECoordinator.

Single entry point for the World State & Event System.
Provides:
  - record_observation() → creates Observation, persists as LedgerEvent
  - record_transition()  → creates StateTransition, persists as LedgerEvent
  - emit()               → publishes any LedgerEvent to WSEEventBus
  - timeline             → WSETimeline instance for temporal queries
  - diff(t1, t2)         → WorldDiff between two timestamps
"""
from __future__ import annotations

import time
import uuid
import logging
from typing import Any, Dict, Optional

from backend.core.ledger.interfaces.clock import SystemClock
from backend.core.ledger.models.enums import EventType
from backend.core.ledger.models.event import LedgerEvent
from backend.core.wse.event_bus import WSEEventBus
from backend.core.wse.observation import Observation
from backend.core.wse.state_transition import StateTransition
from backend.core.wse.timeline import WSETimeline
from backend.core.wse.world_diff import WSEWorldDiff, WorldDiffReport

logger = logging.getLogger(__name__)

_clock = SystemClock()


class WSECoordinator:
    """Unified entry point for the World State & Event System."""

    _instance: Optional["WSECoordinator"] = None

    def __init__(self, bus: Optional[WSEEventBus] = None) -> None:
        self._bus = bus or WSEEventBus.get_instance()
        self._timeline = WSETimeline(self._bus.store)
        self._diff_engine = WSEWorldDiff(self._timeline)

    @classmethod
    def get_instance(cls) -> "WSECoordinator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def timeline(self) -> WSETimeline:
        return self._timeline

    @property
    def bus(self) -> WSEEventBus:
        return self._bus

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def record_observation(
        self,
        source: str,
        subject: str,
        predicate: str,
        value: Any,
        confidence: float = 1.0,
        session_id: str = "",
        goal_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Observation:
        """Create and persist an Observation as a LedgerEvent."""
        obs = Observation.create(
            source=source,
            subject=subject,
            predicate=predicate,
            value=value,
            confidence=confidence,
            session_id=session_id,
            goal_id=goal_id,
            metadata=metadata,
        )
        event = LedgerEvent(
            event_id=f"evt_{obs.observation_id}",
            parent_event_ids=[],
            goal_id=goal_id,
            session_id=session_id,
            correlation_id=obs.correlation_id,
            timestamp_utc=obs.observed_at,
            actor=source,
            subsystem="wse",
            event_type=EventType.OBSERVATION_RECORDED,
            payload=obs.to_dict(),
            confidence=confidence,
        )
        self._bus.publish(event)
        return obs

    def record_transition(
        self,
        entity_id: str,
        entity_type: str,
        from_state: Dict[str, Any],
        to_state: Dict[str, Any],
        trigger_event_id: str = "",
        actor: str = "system",
        session_id: str = "",
        goal_id: str = "",
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StateTransition:
        """Create and persist a StateTransition as a LedgerEvent."""
        trans = StateTransition.create(
            entity_id=entity_id,
            entity_type=entity_type,
            from_state=from_state,
            to_state=to_state,
            trigger_event_id=trigger_event_id,
            actor=actor,
            session_id=session_id,
            goal_id=goal_id,
            reason=reason,
            metadata=metadata,
        )
        event = LedgerEvent(
            event_id=f"evt_{trans.transition_id}",
            parent_event_ids=[trigger_event_id] if trigger_event_id else [],
            goal_id=goal_id,
            session_id=session_id,
            correlation_id=trans.correlation_id,
            timestamp_utc=trans.transitioned_at,
            actor=actor,
            subsystem="wse",
            event_type=EventType.STATE_TRANSITIONED,
            payload=trans.to_dict(),
        )
        self._bus.publish(event)
        return trans

    def emit(self, event: LedgerEvent) -> None:
        """Publish any raw LedgerEvent to the WSEEventBus."""
        self._bus.publish(event)

    def diff(self, t1: float, t2: float) -> WorldDiffReport:
        """Returns a WorldDiffReport comparing world state at t1 vs t2."""
        return self._diff_engine.diff(t1, t2)

    def take_snapshot(self, goal_id: str = "global") -> Dict[str, Any]:
        """Take a current world snapshot and emit a WORLD_SNAPSHOT_TAKEN event."""
        now = _clock.now_utc()
        world_state = self._timeline.at(now)
        snapshot_id = f"snap_{uuid.uuid4().hex[:10]}"

        event = LedgerEvent(
            event_id=f"evt_{snapshot_id}",
            parent_event_ids=[],
            goal_id=goal_id,
            session_id="",
            correlation_id=f"corr_{uuid.uuid4().hex[:8]}",
            timestamp_utc=now,
            actor="wse",
            subsystem="wse",
            event_type=EventType.WORLD_SNAPSHOT_TAKEN,
            payload={
                "snapshot_id": snapshot_id,
                "taken_at": now,
                "entity_count": len(world_state),
                "world_state": world_state,
            },
        )
        self._bus.publish(event)
        return {"snapshot_id": snapshot_id, "taken_at": now, "world_state": world_state}
