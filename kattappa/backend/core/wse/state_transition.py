"""WSE Component 2: StateTransition.

Records a structured state change for an entity triggered by a LedgerEvent.
StateTransitions are persisted as LedgerEvents with
event_type=STATE_TRANSITIONED.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class StateTransition:
    """Represents a structured state change for a tracked entity.

    Immutable after creation. Maps 1-to-1 with a
    LedgerEvent(event_type=STATE_TRANSITIONED).
    """
    transition_id: str
    entity_id: str             # the entity whose state changed
    entity_type: str           # e.g. "goal", "task", "agent", "resource"
    from_state: Dict[str, Any] # previous state snapshot
    to_state: Dict[str, Any]   # new state snapshot
    trigger_event_id: str      # LedgerEvent that caused this transition
    transitioned_at: float     # unix timestamp (UTC)
    actor: str = "system"      # who/what triggered the transition
    session_id: str = ""
    goal_id: str = ""
    correlation_id: str = ""
    reason: str = ""           # human-readable reason for the change
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "trigger_event_id": self.trigger_event_id,
            "transitioned_at": self.transitioned_at,
            "actor": self.actor,
            "session_id": self.session_id,
            "goal_id": self.goal_id,
            "correlation_id": self.correlation_id,
            "reason": self.reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateTransition":
        return cls(
            transition_id=data["transition_id"],
            entity_id=data["entity_id"],
            entity_type=data.get("entity_type", "unknown"),
            from_state=data.get("from_state", {}),
            to_state=data.get("to_state", {}),
            trigger_event_id=data.get("trigger_event_id", ""),
            transitioned_at=float(data["transitioned_at"]),
            actor=data.get("actor", "system"),
            session_id=data.get("session_id", ""),
            goal_id=data.get("goal_id", ""),
            correlation_id=data.get("correlation_id", ""),
            reason=data.get("reason", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
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
    ) -> "StateTransition":
        """Factory method — generates unique ID and timestamp automatically."""
        return cls(
            transition_id=f"trans_{uuid.uuid4().hex[:12]}",
            entity_id=entity_id,
            entity_type=entity_type,
            from_state=from_state,
            to_state=to_state,
            trigger_event_id=trigger_event_id,
            transitioned_at=time.time(),
            actor=actor,
            session_id=session_id,
            goal_id=goal_id,
            correlation_id=f"corr_{uuid.uuid4().hex[:8]}",
            reason=reason,
            metadata=metadata or {},
        )
