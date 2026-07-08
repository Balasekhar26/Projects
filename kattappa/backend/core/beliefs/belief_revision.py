"""Belief Management Component 6: Belief Revision Engine.

Implements non-destructive belief updates (retractions/refutations) when
contradictory evidence dominates prior assertions.
"""
from __future__ import annotations

import time
import logging
from typing import Any, Optional

from backend.core.cos.state_representation import BeliefStatus
from backend.core.beliefs.belief import Belief
from backend.core.beliefs.belief_store import BeliefStore
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


class BeliefRevisionEngine:
    """Manages non-destructive revision transitions for stored beliefs."""

    def __init__(self, store: BeliefStore) -> None:
        self._store = store

    def revise_belief(self, existing: Belief, new_value: Any, new_confidence: float, status: BeliefStatus) -> Belief:
        """Saves a versioned update of a belief, preserving its historical lineage."""
        revised = Belief(
            belief_id=existing.belief_id,
            claim_subject=existing.claim_subject,
            claim_predicate=existing.claim_predicate,
            claim_value=new_value,
            confidence=new_confidence,
            truth_status=status,
            source_ids=existing.source_ids,
            evidence_ids=existing.evidence_ids,
            created_at=existing.created_at,
            updated_at=time.time(),
            valid_from=existing.valid_from,
            valid_until=existing.valid_until,
            version=existing.version + 1,
            metadata=existing.metadata,
        )
        self._store.save_belief(revised)
        log_event(
            "belief_revised",
            f"Belief {existing.belief_id} revised: value={new_value} confidence={new_confidence:.2f} status={status.value}",
        )
        return revised

    def retract_belief(self, belief_id: str, reason: str = "") -> Optional[Belief]:
        """Transitions active belief to RETRACTED state non-destructively."""
        existing = self._store.get_belief(belief_id)
        if not existing:
            return None

        # Update status to RETRACTED, set confidence to 0.0
        meta = dict(existing.metadata)
        if reason:
            meta["retraction_reason"] = reason

        revised = Belief(
            belief_id=existing.belief_id,
            claim_subject=existing.claim_subject,
            claim_predicate=existing.claim_predicate,
            claim_value=existing.claim_value,
            confidence=0.0,
            truth_status=BeliefStatus.RETRACTED,
            source_ids=existing.source_ids,
            evidence_ids=existing.evidence_ids,
            created_at=existing.created_at,
            updated_at=time.time(),
            valid_from=existing.valid_from,
            valid_until=time.time(),  # Expired now
            version=existing.version + 1,
            metadata=meta,
        )
        self._store.save_belief(revised)
        log_event(
            "belief_retracted",
            f"Belief {belief_id} retracted. Reason: {reason}",
        )
        return revised
