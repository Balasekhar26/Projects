from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from backend.core.ledger.models.enums import EventType


@dataclass(frozen=True)
class LedgerEvent:
    event_id: str
    parent_event_ids: List[str]
    goal_id: str
    session_id: str
    correlation_id: str
    timestamp_utc: float
    actor: str
    subsystem: str
    event_type: EventType
    payload: Dict[str, Any]
    evidence: Optional[Dict[str, Any]] = None
    confidence: float = 1.0
    status: str = "PENDING"
    metadata: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1
    event_version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "parent_event_ids": self.parent_event_ids,
            "goal_id": self.goal_id,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "timestamp_utc": self.timestamp_utc,
            "actor": self.actor,
            "subsystem": self.subsystem,
            "event_type": self.event_type.value,
            "payload": self.payload,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "status": self.status,
            "metadata": self.metadata,
            "schema_version": self.schema_version,
            "event_version": self.event_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LedgerEvent:
        return cls(
            event_id=data["event_id"],
            parent_event_ids=data["parent_event_ids"],
            goal_id=data["goal_id"],
            session_id=data["session_id"],
            correlation_id=data["correlation_id"],
            timestamp_utc=data["timestamp_utc"],
            actor=data["actor"],
            subsystem=data["subsystem"],
            event_type=EventType(data["event_type"]),
            payload=data["payload"],
            evidence=data.get("evidence"),
            confidence=data.get("confidence", 1.0),
            status=data.get("status", "PENDING"),
            metadata=data.get("metadata", {}),
            schema_version=data.get("schema_version", 1),
            event_version=data.get("event_version", 1),
        )
