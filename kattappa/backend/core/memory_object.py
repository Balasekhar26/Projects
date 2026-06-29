from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time
import uuid


@dataclass(frozen=True)
class MemoryObject:
    """Canonical memory object model representing a unified storage schema for all 8 subsystems."""

    memory_id: str
    revision_id: str
    parent_revision: Optional[str]
    system_type: str  # e.g., EPISODIC, SEMANTIC, PROCEDURAL, PREFERENCE, RELATIONSHIP, GOAL, BELIEF_GRAPH, KNOWLEDGE_GRAPH
    content: Dict[str, Any]
    belief_confidence: float = 1.0
    act_r_activation: float = 1.0
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    decay_rate: float = 0.05
    tags: List[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        system_type: str,
        content: Dict[str, Any],
        memory_id: Optional[str] = None,
        parent_revision: Optional[str] = None,
        belief_confidence: float = 1.0,
        act_r_activation: float = 1.0,
        decay_rate: float = 0.05,
        tags: Optional[List[str]] = None,
    ) -> MemoryObject:
        """Helper to create a fresh MemoryObject with generated unique IDs."""
        now = time.time()
        return cls(
            memory_id=memory_id or f"mem_{uuid.uuid4().hex[:8]}",
            revision_id=f"rev_{uuid.uuid4().hex[:8]}",
            parent_revision=parent_revision,
            system_type=system_type.upper().strip(),
            content=content,
            belief_confidence=belief_confidence,
            act_r_activation=act_r_activation,
            created_at=now,
            last_accessed_at=now,
            decay_rate=decay_rate,
            tags=tags or [],
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize memory object representation to dictionary."""
        return {
            "memory_id": self.memory_id,
            "revision_id": self.revision_id,
            "parent_revision": self.parent_revision,
            "system_type": self.system_type,
            "content": self.content,
            "belief_confidence": self.belief_confidence,
            "act_r_activation": self.act_r_activation,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
            "decay_rate": self.decay_rate,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MemoryObject:
        """Deserialize memory object from dictionary."""
        return cls(
            memory_id=data["memory_id"],
            revision_id=data["revision_id"],
            parent_revision=data.get("parent_revision"),
            system_type=data["system_type"],
            content=data["content"],
            belief_confidence=data.get("belief_confidence", 1.0),
            act_r_activation=data.get("act_r_activation", 1.0),
            created_at=data.get("created_at", time.time()),
            last_accessed_at=data.get("last_accessed_at", time.time()),
            decay_rate=data.get("decay_rate", 0.05),
            tags=data.get("tags", []),
        )
