"""
backend/core/memory/schemas.py

Memory contracts and data types for the Kattappa Persistent Memory Engine (v0.2).

Defines the canonical MemoryRecord dataclass and MemoryType enum used by all
memory subsystems (working, episodic, semantic, procedural, reflection, policy).

Design principles:
  - Separation of presentation from storage: MemoryRecord is transport-neutral.
  - Immutable identity fields (memory_id, timestamp) to prevent tampering.
  - Validated confidence and importance scores to enforce invariants at creation time.
  - Payload carries subsystem-specific structured content as a plain dict,
    keeping the schema open for extension without changing the contract.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MemoryType(str, Enum):
    """Classification of memory by temporal horizon and decay characteristics.

    Retention order from shortest to permanent:
        WORKING     -> hours    (active task context)
        EPISODIC    -> months   (autobiographical experience log)
        REFLECTION  -> months   (distilled insights from episodes)
        SEMANTIC    -> years    (verified generalized facts)
        PROCEDURAL  -> permanent (learned skills and workflows)
        POLICY      -> permanent (safety and alignment rules)
    """

    WORKING = "working"
    EPISODIC = "episodic"
    REFLECTION = "reflection"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    POLICY = "policy"


# Default retention durations in seconds for each memory type.
# These values inform the ForgettingEngine; permanent types use None.
DEFAULT_TTL: Dict[MemoryType, Optional[float]] = {
    MemoryType.WORKING: 3 * 3600,            # 3 hours
    MemoryType.EPISODIC: 90 * 86400,         # 90 days
    MemoryType.REFLECTION: 90 * 86400,       # 90 days
    MemoryType.SEMANTIC: 365 * 86400 * 3,    # 3 years
    MemoryType.PROCEDURAL: None,             # permanent
    MemoryType.POLICY: None,                 # permanent
}


def _new_memory_id() -> str:
    return str(uuid.uuid4())


def _now() -> float:
    return time.time()


@dataclass
class MemoryRecord:
    """The canonical transport object for all Kattappa memory operations.

    Every read, write, retrieval, and decay operation in the memory engine
    works with MemoryRecord instances. Subsystem-specific logic is confined
    entirely to the ``payload`` dict; this contract remains stable.

    Fields:
        memory_id:       Unique identifier for this record.  Auto-generated if omitted.
        memory_type:     Temporal class that determines storage tier and decay rate.
        timestamp:       Unix epoch seconds at creation.  Auto-set if omitted.
        source_agent:    Identifier of the agent or subsystem that generated this memory.
        confidence:      Epistemic confidence in the payload contents (0.0 – 1.0).
        importance_score: Salience heuristic used by the ForgettingEngine (0.0 – 1.0).
        tags:            Arbitrary labels for filtering and retrieval.
        embedding_id:    Optional reference to a vector store embedding for semantic search.
        payload:         Subsystem-specific structured content.
    """

    memory_type: MemoryType
    source_agent: str
    payload: Dict[str, Any]

    # Identity — auto-populated when not supplied
    memory_id: str = field(default_factory=_new_memory_id)
    timestamp: float = field(default_factory=_now)

    # Quality signals
    confidence: float = 1.0
    importance_score: float = 0.5

    # Metadata
    tags: List[str] = field(default_factory=list)
    embedding_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Post-init validation
    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"MemoryRecord.confidence must be in [0.0, 1.0]; got {self.confidence!r}"
            )
        if not (0.0 <= self.importance_score <= 1.0):
            raise ValueError(
                f"MemoryRecord.importance_score must be in [0.0, 1.0]; got {self.importance_score!r}"
            )
        if not isinstance(self.memory_type, MemoryType):
            raise TypeError(
                f"MemoryRecord.memory_type must be a MemoryType; got {type(self.memory_type)!r}"
            )
        if not self.source_agent or not self.source_agent.strip():
            raise ValueError("MemoryRecord.source_agent must be a non-empty string.")
        if not isinstance(self.payload, dict):
            raise TypeError(
                f"MemoryRecord.payload must be a dict; got {type(self.payload)!r}"
            )
        # Normalize tags
        self.tags = [str(t) for t in self.tags]

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """Serialize the record to a plain dict suitable for JSON or SQLite storage."""
        return {
            "memory_id": self.memory_id,
            "memory_type": self.memory_type.value,
            "timestamp": self.timestamp,
            "source_agent": self.source_agent,
            "confidence": self.confidence,
            "importance_score": self.importance_score,
            "tags": self.tags,
            "embedding_id": self.embedding_id,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        """Serialize the record to a compact JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRecord":
        """Deserialize a MemoryRecord from a plain dict (e.g., from SQLite row)."""
        return cls(
            memory_id=data["memory_id"],
            memory_type=MemoryType(data["memory_type"]),
            timestamp=float(data["timestamp"]),
            source_agent=data["source_agent"],
            confidence=float(data.get("confidence", 1.0)),
            importance_score=float(data.get("importance_score", 0.5)),
            tags=list(data.get("tags", [])),
            embedding_id=data.get("embedding_id"),
            payload=dict(data.get("payload", {})),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "MemoryRecord":
        """Deserialize a MemoryRecord from a JSON string."""
        return cls.from_dict(json.loads(json_str))

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------
    @property
    def default_ttl(self) -> Optional[float]:
        """Return the default time-to-live in seconds, or None if permanent."""
        return DEFAULT_TTL.get(self.memory_type)

    @property
    def is_permanent(self) -> bool:
        """True if this memory type has no decay TTL."""
        return self.default_ttl is None

    def retention_score(self, now: Optional[float] = None) -> float:
        """Compute the current retention score using a simple decay model.

        retention_score = importance_score × confidence × recency_factor

        recency_factor decays linearly from 1.0 (just created) to 0.0 at
        default_ttl expiry.  Permanent memories always return 1.0.
        """
        if self.is_permanent:
            return 1.0

        if now is None:
            now = time.time()

        age = max(0.0, now - self.timestamp)
        ttl = self.default_ttl  # guaranteed non-None here
        recency_factor = max(0.0, 1.0 - (age / ttl))
        return self.importance_score * self.confidence * recency_factor

    def __repr__(self) -> str:
        return (
            f"MemoryRecord(type={self.memory_type.value!r}, "
            f"agent={self.source_agent!r}, "
            f"id={self.memory_id[:8]}...)"
        )
