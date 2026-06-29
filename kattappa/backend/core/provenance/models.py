"""Provenance Engine Component 1: Models.

Defines structural models for Sources, Evidence Items, and Provenance Records.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.core.trust_evidence import EvidenceLevel, ConfidenceTier


class VerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    CORROBORATED = "CORROBORATED"
    CONTRADICTED = "CONTRADICTED"


@dataclass(frozen=True)
class Source:
    """Represents an origin of observations/data (model, user, sensor, web)."""
    source_id: str
    name: str
    source_type: str  # e.g., "model", "user", "sensor", "web", "tool", "system"
    base_reputation: float = 0.3
    current_reputation: float = 0.3
    trust_level: str = "LOW"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "source_type": self.source_type,
            "base_reputation": self.base_reputation,
            "current_reputation": self.current_reputation,
            "trust_level": self.trust_level,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Source:
        return cls(
            source_id=data["source_id"],
            name=data["name"],
            source_type=data["source_type"],
            base_reputation=float(data.get("base_reputation", 0.3)),
            current_reputation=float(data.get("current_reputation", 0.3)),
            trust_level=data.get("trust_level", "LOW"),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class ProvenanceEvidenceItem:
    """A single unit of verification supporting or refuting a belief."""
    evidence_id: str
    source_id: str
    evidence_level: EvidenceLevel
    confidence: float
    verification_state: VerificationState
    observed_at: float
    context_citation: str = ""  # URL, file reference, conversation message ID
    supports: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "evidence_level": self.evidence_level.name,
            "evidence_level_value": self.evidence_level.value,
            "confidence": self.confidence,
            "verification_state": self.verification_state.value,
            "observed_at": self.observed_at,
            "context_citation": self.context_citation,
            "supports": self.supports,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProvenanceEvidenceItem:
        return cls(
            evidence_id=data["evidence_id"],
            source_id=data["source_id"],
            evidence_level=EvidenceLevel.coerce(data["evidence_level"]),
            confidence=float(data.get("confidence", 1.0)),
            verification_state=VerificationState(data.get("verification_state", "UNVERIFIED")),
            observed_at=float(data["observed_at"]),
            context_citation=data.get("context_citation", ""),
            supports=bool(data.get("supports", True)),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        source_id: str,
        evidence_level: EvidenceLevel | str | int,
        confidence: float = 1.0,
        verification_state: VerificationState | str = VerificationState.UNVERIFIED,
        context_citation: str = "",
        supports: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProvenanceEvidenceItem:
        return cls(
            evidence_id=f"ev_{uuid.uuid4().hex[:12]}",
            source_id=source_id,
            evidence_level=EvidenceLevel.coerce(evidence_level),
            confidence=max(0.0, min(1.0, confidence)),
            verification_state=VerificationState(verification_state),
            observed_at=time.time(),
            context_citation=context_citation,
            supports=supports,
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class ProvenanceRecord:
    """Lineage container linking a Knowledge Graph target_id to its evidence list."""
    target_id: str  # KG Node ID or Edge ID
    evidence_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "evidence_ids": self.evidence_ids,
        }
