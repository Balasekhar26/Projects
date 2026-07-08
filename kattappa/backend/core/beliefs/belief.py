"""Belief Management Component 1: Models.

Defines structural models for Beliefs, Justifications, and Dependencies.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.core.cos.state_representation import BeliefStatus


@dataclass(frozen=True)
class Belief:
    """Represents a validated, versioned assertion about reality."""
    belief_id: str
    claim_subject: str          # Entity ID or concept being described
    claim_predicate: str        # Attribute name (e.g. "status", "level")
    claim_value: Any            # Value believed to be true
    confidence: float           # Aggregated confidence score
    truth_status: BeliefStatus  # BELIEVED, HYPOTHESIS, RETRACTED, REFUTED
    source_ids: List[str]       # Registered sources supporting this belief
    evidence_ids: List[str]     # Evidence item IDs backing this belief
    created_at: float
    updated_at: float
    valid_from: float           # Temporal validity start
    valid_until: Optional[float] = None  # Temporal validity end (None = indefinite)
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "belief_id": self.belief_id,
            "claim_subject": self.claim_subject,
            "claim_predicate": self.claim_predicate,
            "claim_value": self.claim_value,
            "confidence": self.confidence,
            "truth_status": self.truth_status.value,
            "source_ids": self.source_ids,
            "evidence_ids": self.evidence_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "version": self.version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Belief:
        return cls(
            belief_id=data["belief_id"],
            claim_subject=data["claim_subject"],
            claim_predicate=data["claim_predicate"],
            claim_value=data["claim_value"],
            confidence=float(data["confidence"]),
            truth_status=BeliefStatus(data["truth_status"]),
            source_ids=data.get("source_ids", []),
            evidence_ids=data.get("evidence_ids", []),
            created_at=float(data["created_at"]),
            updated_at=float(data["updated_at"]),
            valid_from=float(data["valid_from"]),
            valid_until=float(data["valid_until"]) if data.get("valid_until") is not None else None,
            version=int(data.get("version", 1)),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        subject: str,
        predicate: str,
        value: Any,
        confidence: float,
        truth_status: BeliefStatus = BeliefStatus.BELIEVED,
        source_ids: Optional[List[str]] = None,
        evidence_ids: Optional[List[str]] = None,
        valid_from: Optional[float] = None,
        valid_until: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Belief:
        now = time.time()
        return cls(
            belief_id=f"bel_{uuid.uuid4().hex[:12]}",
            claim_subject=subject,
            claim_predicate=predicate,
            claim_value=value,
            confidence=max(0.0, min(1.0, confidence)),
            truth_status=truth_status,
            source_ids=source_ids or [],
            evidence_ids=evidence_ids or [],
            created_at=now,
            updated_at=now,
            valid_from=valid_from or now,
            valid_until=valid_until,
            version=1,
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class Justification:
    """Explains why a belief is held, linking it to evidence and dependencies."""
    justification_id: str
    belief_id: str
    rationale: str
    evidence_ids: List[str]
    dependency_ids: List[str]  # Belief IDs that this justification depends on
    created_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "justification_id": self.justification_id,
            "belief_id": self.belief_id,
            "rationale": self.rationale,
            "evidence_ids": self.evidence_ids,
            "dependency_ids": self.dependency_ids,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class BeliefDependency:
    """Represents a parent-child truth dependency link in the justification graph."""
    parent_belief_id: str
    child_belief_id: str
    dependency_type: str = "supports"  # E.g. "supports", "contradicts", "derived_from"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parent_belief_id": self.parent_belief_id,
            "child_belief_id": self.child_belief_id,
            "dependency_type": self.dependency_type,
        }
