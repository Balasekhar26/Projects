"""WSE Component 1: Observation Model.

A first-class primitive representing a single sensed fact about the world.
Observations are immutable once created and are persisted as LedgerEvents.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Observation:
    """Represents a single sensed/observed fact about the world.

    Immutable after creation. Each Observation maps 1-to-1 with a
    LedgerEvent(event_type=OBSERVATION_RECORDED).
    """
    observation_id: str
    source: str           # agent_id, sensor name, subsystem, or "user"
    subject: str          # entity or concept being observed
    predicate: str        # property being observed (e.g. "status", "temperature")
    value: Any            # the observed value (string, number, dict, etc.)
    confidence: float     # 0.0–1.0
    observed_at: float    # unix timestamp (UTC)
    session_id: str = ""
    goal_id: str = ""
    correlation_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "source": self.source,
            "subject": self.subject,
            "predicate": self.predicate,
            "value": self.value,
            "confidence": self.confidence,
            "observed_at": self.observed_at,
            "session_id": self.session_id,
            "goal_id": self.goal_id,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Observation":
        return cls(
            observation_id=data["observation_id"],
            source=data["source"],
            subject=data["subject"],
            predicate=data["predicate"],
            value=data["value"],
            confidence=float(data.get("confidence", 1.0)),
            observed_at=float(data["observed_at"]),
            session_id=data.get("session_id", ""),
            goal_id=data.get("goal_id", ""),
            correlation_id=data.get("correlation_id", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        source: str,
        subject: str,
        predicate: str,
        value: Any,
        confidence: float = 1.0,
        session_id: str = "",
        goal_id: str = "",
        correlation_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Observation":
        """Factory method — generates a unique ID and timestamps automatically."""
        return cls(
            observation_id=f"obs_{uuid.uuid4().hex[:12]}",
            source=source,
            subject=subject,
            predicate=predicate,
            value=value,
            confidence=max(0.0, min(1.0, confidence)),
            observed_at=time.time(),
            session_id=session_id,
            goal_id=goal_id,
            correlation_id=correlation_id or f"corr_{uuid.uuid4().hex[:8]}",
            metadata=metadata or {},
        )
