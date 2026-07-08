from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class LedgerSnapshot:
    snapshot_id: str
    goal_id: str
    last_event_id: str
    timestamp_utc: float
    state: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "goal_id": self.goal_id,
            "last_event_id": self.last_event_id,
            "timestamp_utc": self.timestamp_utc,
            "state": self.state,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LedgerSnapshot:
        return cls(
            snapshot_id=data["snapshot_id"],
            goal_id=data["goal_id"],
            last_event_id=data["last_event_id"],
            timestamp_utc=data["timestamp_utc"],
            state=data["state"],
            metadata=data.get("metadata", {}),
        )
