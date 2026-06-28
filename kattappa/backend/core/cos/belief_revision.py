"""Belief Revision — Phase K21.5.

Implements the BeliefRevisionEngine with AGM-style expansion, revision,
and contraction operators, generating structured RevisionRecord entries.
"""
from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.core.cos.belief_engine import BeliefEngine, EvidenceFusion
from backend.core.cos.state_representation import BeliefState, Evidence, PropertyValue
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass
class RevisionRecord:
    """Represents a structured audit trace of a belief modification transaction."""
    revision_id: str
    operator: str  # E.g. 'EXPANSION', 'REVISION', 'CONTRACTION'
    entity_uuid: str
    property_name: str
    old_value: Any
    new_value: Any
    triggering_evidence_id: Optional[str]
    timestamp: float
    reason: str


class BeliefRevisionEngine:
    """Belief Revision Engine implementing AGM operators (Expansion, Revision, Contraction)."""

    def __init__(self, belief_engine: BeliefEngine):
        self.belief_engine = belief_engine
        self.revision_history: List[RevisionRecord] = []

    def expand(self, entity_uuid: str, prop_name: str, prop_val: PropertyValue, reason: str = "Expansion assertion") -> RevisionRecord:
        """AGM Expansion: inserts a new non-conflicting belief directly into the state."""
        prior = self.belief_engine.state.get_property(entity_uuid, prop_name)
        if prior is not None:
            # If it already exists, delegate to revise operator
            return self.revise(entity_uuid, prop_name, prop_val, "delegated_from_expansion", reason)

        # Apply expansion
        self.belief_engine.state.set_property(entity_uuid, prop_name, prop_val.clone())
        self.belief_engine.dependency_tracker.propagate_change(self.belief_engine.state, entity_uuid, prop_name)

        record = RevisionRecord(
            revision_id=f"rev_{int(time.time() * 1000)}",
            operator="EXPANSION",
            entity_uuid=entity_uuid,
            property_name=prop_name,
            old_value=None,
            new_value=prop_val.value,
            triggering_evidence_id=None,
            timestamp=time.time(),
            reason=reason
        )
        self.revision_history.append(record)
        log_event("agm_expansion", f"Asserted fresh belief {entity_uuid}.{prop_name} = '{prop_val.value}'")
        return record

    def revise(
        self,
        entity_uuid: str,
        prop_name: str,
        prop_val: PropertyValue,
        trigger_ev_id: Optional[str],
        reason: str = "Revision update"
    ) -> RevisionRecord:
        """AGM Revision: updates an existing belief with new evidence, checking for contradictions."""
        prior = self.belief_engine.state.get_property(entity_uuid, prop_name)
        if prior is None:
            return self.expand(entity_uuid, prop_name, prop_val, reason)

        # Detect contradiction
        conflict = self.belief_engine.contradiction_detector.check_contradiction(
            entity_uuid, prop_name, prior, prop_val
        )

        if conflict:
            # Degrade confidence of both to 0.50 (uncertainty mitigation)
            fused_pv = PropertyValue(
                value=prior.value,
                confidence=0.50,
                source=prop_val.source,
                timestamp=time.time(),
                history=[prior.clone()] + [h.clone() for h in prior.history],
                evidence_history=list(prior.evidence_history)
            )
        else:
            # Fuse evidence using Bayesian Likelihood Ratios
            fused_pv = EvidenceFusion.fuse_properties(prior, prop_val)

        self.belief_engine.state.set_property(entity_uuid, prop_name, fused_pv)
        self.belief_engine.dependency_tracker.propagate_change(self.belief_engine.state, entity_uuid, prop_name)

        record = RevisionRecord(
            revision_id=f"rev_{int(time.time() * 1000)}",
            operator="REVISION",
            entity_uuid=entity_uuid,
            property_name=prop_name,
            old_value=prior.value,
            new_value=fused_pv.value,
            triggering_evidence_id=trigger_ev_id,
            timestamp=time.time(),
            reason=reason
        )
        self.revision_history.append(record)
        log_event("agm_revision", f"Revised belief {entity_uuid}.{prop_name}: '{prior.value}' -> '{fused_pv.value}'")
        return record

    def contract(self, entity_uuid: str, prop_name: str, reason: str = "Contraction request") -> Optional[RevisionRecord]:
        """AGM Contraction: retracts a belief by setting its confidence level to 0.0 and propagating change."""
        prior = self.belief_engine.state.get_property(entity_uuid, prop_name)
        if prior is None:
            return None

        # Retract belief confidence to 0.0
        contracted_pv = PropertyValue(
            value=prior.value,
            confidence=0.0,
            source=prior.source,
            timestamp=time.time(),
            history=[prior.clone()] + [h.clone() for h in prior.history],
            evidence_history=list(prior.evidence_history)
        )
        self.belief_engine.state.set_property(entity_uuid, prop_name, contracted_pv)
        
        # Propagate changes: child nodes bounded recursively by min(child_conf, 0.0) -> child confidence will drop to 0.0
        self.belief_engine.dependency_tracker.propagate_change(self.belief_engine.state, entity_uuid, prop_name)

        record = RevisionRecord(
            revision_id=f"rev_{int(time.time() * 1000)}",
            operator="CONTRACTION",
            entity_uuid=entity_uuid,
            property_name=prop_name,
            old_value=prior.value,
            new_value=None,
            triggering_evidence_id=None,
            timestamp=time.time(),
            reason=reason
        )
        self.revision_history.append(record)
        log_event("agm_contraction", f"Contracted belief {entity_uuid}.{prop_name} (confidence degraded to 0.0)")
        return record
