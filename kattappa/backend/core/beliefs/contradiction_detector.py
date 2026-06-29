"""Belief Management Component 4: Contradiction Detector.

Detects conflicting property assertions and flags active conflicts for review.
"""
from __future__ import annotations

import time
import uuid
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.core.beliefs.belief import Belief
from backend.core.beliefs.belief_store import BeliefStore
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BeliefConflict:
    """Represents a registered contradiction between two active beliefs."""
    conflict_id: str
    subject: str
    predicate: str
    belief_a_id: str
    belief_a_value: Any
    belief_a_confidence: float
    belief_b_id: str
    belief_b_value: Any
    belief_b_confidence: float
    detected_at: float
    status: str = "OPEN"  # OPEN, RESOLVED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "subject": self.subject,
            "predicate": self.predicate,
            "belief_a_id": self.belief_a_id,
            "belief_a_value": self.belief_a_value,
            "belief_a_confidence": self.belief_a_confidence,
            "belief_b_id": self.belief_b_id,
            "belief_b_value": self.belief_b_value,
            "belief_b_confidence": self.belief_b_confidence,
            "detected_at": self.detected_at,
            "status": self.status,
        }


class ContradictionDetector:
    """Detects and registers contradicting claims on entity attributes."""

    def __init__(self, store: BeliefStore) -> None:
        self._store = store
        self._conflicts: Dict[str, BeliefConflict] = {}

    def check_conflict(self, incoming: Belief) -> Optional[BeliefConflict]:
        """Compares incoming belief with active stored belief. Registers conflict if values differ."""
        prior = self._store.get_belief_by_claim(incoming.claim_subject, incoming.claim_predicate)
        if not prior:
            return None

        # If values are identical, there is no conflict
        if prior.claim_value == incoming.claim_value:
            return None

        # Values differ — we have a contradiction
        conflict_id = f"conf_{uuid.uuid4().hex[:12]}"
        conflict = BeliefConflict(
            conflict_id=conflict_id,
            subject=incoming.claim_subject,
            predicate=incoming.claim_predicate,
            belief_a_id=prior.belief_id,
            belief_a_value=prior.claim_value,
            belief_a_confidence=prior.confidence,
            belief_b_id=incoming.belief_id,
            belief_b_value=incoming.claim_value,
            belief_b_confidence=incoming.confidence,
            detected_at=time.time(),
            status="OPEN",
        )
        self._conflicts[conflict_id] = conflict
        
        log_event(
            "tms_contradiction_detected",
            f"Contradiction on {incoming.claim_subject}.{incoming.claim_predicate}: "
            f"'{prior.claim_value}' (conf={prior.confidence:.2f}) vs "
            f"'{incoming.claim_value}' (conf={incoming.confidence:.2f})",
        )
        return conflict

    def get_open_conflicts(self) -> List[BeliefConflict]:
        return [c for c in self._conflicts.values() if c.status == "OPEN"]

    def resolve_conflict(self, conflict_id: str) -> None:
        if conflict_id in self._conflicts:
            c = self._conflicts[conflict_id]
            # Replace with a resolved status copy
            self._conflicts[conflict_id] = BeliefConflict(
                conflict_id=c.conflict_id,
                subject=c.subject,
                predicate=c.predicate,
                belief_a_id=c.belief_a_id,
                belief_a_value=c.belief_a_value,
                belief_a_confidence=c.belief_a_confidence,
                belief_b_id=c.belief_b_id,
                belief_b_value=c.belief_b_value,
                belief_b_confidence=c.belief_b_confidence,
                detected_at=c.detected_at,
                status="RESOLVED",
            )
            log_event("tms_conflict_resolved", f"Conflict resolved: {conflict_id}")
