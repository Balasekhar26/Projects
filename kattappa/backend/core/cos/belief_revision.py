"""Belief Revision — Phase K21.6.

Implements the BeliefRevisionEngine with AGM-style expansion, revision,
and contraction operators, generating structured, enriched RevisionRecord entries.
Integrates with the TruthMaintenanceSystem (TMS) and BeliefStatus.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional

from backend.core.cos.belief_engine import BeliefEngine, EvidenceFusion
from backend.core.cos.state_representation import BeliefStatus, PropertyValue
from backend.core.cos.tms import (
    Justification,
    JustificationManager,
    TruthMaintenanceSystem,
)
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
    affected_nodes: List[str] = field(default_factory=list)
    previous_confidence: float = 0.0
    new_confidence: float = 0.0
    revision_strategy: str = "DIRECT"


class BeliefRevisionEngine:
    """Belief Revision Engine implementing AGM operators (Expansion, Revision, Contraction)."""

    def __init__(
        self, belief_engine: BeliefEngine, tms: Optional[TruthMaintenanceSystem] = None
    ):
        self.belief_engine = belief_engine
        self.tms = (
            tms if tms is not None else TruthMaintenanceSystem(JustificationManager())
        )
        self.revision_history: List[RevisionRecord] = []

    def expand(
        self,
        entity_uuid: str,
        prop_name: str,
        prop_val: PropertyValue,
        reason: str = "Expansion assertion",
    ) -> RevisionRecord:
        """AGM Expansion: inserts a new non-conflicting belief. Raises ValueError if already exists."""
        prior = self.belief_engine.state.get_property(entity_uuid, prop_name)
        if prior is not None:
            raise ValueError(
                f"Property {entity_uuid}.{prop_name} already exists. Cannot expand."
            )

        # Set status to BELIEVED on expansion
        expanded_pv = prop_val.clone()
        expanded_pv.status = BeliefStatus.BELIEVED
        expanded_pv.version = 1
        expanded_pv.revision_number = 0

        # Apply expansion
        self.belief_engine.state.set_property(entity_uuid, prop_name, expanded_pv)

        # Set up justification
        just = Justification(
            justification_id=f"just_{int(time.time() * 1000)}",
            entity_uuid=entity_uuid,
            property_name=prop_name,
            supporting_evidence_ids=(
                [e.evidence_id for e in expanded_pv.evidence_history]
                if expanded_pv.evidence_history
                else []
            ),
            supporting_antecedents=[],
            status="IN",
        )
        self.tms.justification_manager.add_justification(entity_uuid, prop_name, just)

        # Propagate
        self.belief_engine.dependency_tracker.propagate_change(
            self.belief_engine.state, entity_uuid, prop_name
        )

        record = RevisionRecord(
            revision_id=f"rev_{int(time.time() * 1000)}",
            operator="EXPANSION",
            entity_uuid=entity_uuid,
            property_name=prop_name,
            old_value=None,
            new_value=expanded_pv.value,
            triggering_evidence_id=None,
            timestamp=time.time(),
            reason=reason,
            affected_nodes=[f"{entity_uuid}.{prop_name}"],
            previous_confidence=0.0,
            new_confidence=expanded_pv.confidence,
            revision_strategy="DIRECT",
        )
        self.revision_history.append(record)
        log_event(
            "agm_expansion",
            f"Asserted fresh belief {entity_uuid}.{prop_name} = '{expanded_pv.value}'",
        )
        return record

    def revise(
        self,
        entity_uuid: str,
        prop_name: str,
        prop_val: PropertyValue,
        trigger_ev_id: Optional[str],
        reason: str = "Revision update",
    ) -> RevisionRecord:
        """AGM Revision: updates an existing belief with new evidence, checking for contradictions."""
        prior = self.belief_engine.state.get_property(entity_uuid, prop_name)
        if prior is None:
            return self.expand(entity_uuid, prop_name, prop_val, reason)

        # Detect contradiction
        conflict = self.belief_engine.contradiction_detector.check_contradiction(
            entity_uuid, prop_name, prior, prop_val
        )

        strategy = "BAYESIAN_LIKELIHOOD"
        if conflict:
            strategy = "CONTRADICTION_MITIGATION"
            # Degrade confidence of both to 0.50 (uncertainty mitigation)
            fused_pv = PropertyValue(
                value=prior.value,
                confidence=0.50,
                source=prop_val.source,
                timestamp=time.time(),
                history=[prior.clone()] + [h.clone() for h in prior.history],
                evidence_history=list(prior.evidence_history),
                status=BeliefStatus.HYPOTHESIS,
                version=prior.version,
                revision_number=prior.revision_number + 1,
            )
        else:
            # Fuse evidence using Bayesian Likelihood Ratios
            fused_pv = EvidenceFusion.fuse_properties(prior, prop_val)
            fused_pv.status = BeliefStatus.BELIEVED
            fused_pv.version = prior.version
            fused_pv.revision_number = prior.revision_number + 1

        self.belief_engine.state.set_property(entity_uuid, prop_name, fused_pv)

        # Update justification
        just = self.tms.justification_manager.get_justification(entity_uuid, prop_name)
        if just is None:
            just = Justification(
                justification_id=f"just_{int(time.time() * 1000)}",
                entity_uuid=entity_uuid,
                property_name=prop_name,
                status="IN",
            )
            self.tms.justification_manager.add_justification(
                entity_uuid, prop_name, just
            )

        if trigger_ev_id and trigger_ev_id not in just.supporting_evidence_ids:
            just.supporting_evidence_ids.append(trigger_ev_id)
        just.status = "IN"

        # Propagate dependency changes and run TMS validation
        self.belief_engine.dependency_tracker.propagate_change(
            self.belief_engine.state, entity_uuid, prop_name
        )
        self.tms.propagate_justifications(
            self.belief_engine.state, self.belief_engine.dependency_tracker.dependencies
        )

        record = RevisionRecord(
            revision_id=f"rev_{int(time.time() * 1000)}",
            operator="REVISION",
            entity_uuid=entity_uuid,
            property_name=prop_name,
            old_value=prior.value,
            new_value=fused_pv.value,
            triggering_evidence_id=trigger_ev_id,
            timestamp=time.time(),
            reason=reason,
            affected_nodes=[f"{entity_uuid}.{prop_name}"],
            previous_confidence=prior.confidence,
            new_confidence=fused_pv.confidence,
            revision_strategy=strategy,
        )
        self.revision_history.append(record)
        log_event(
            "agm_revision",
            f"Revised belief {entity_uuid}.{prop_name}: '{prior.value}' -> '{fused_pv.value}'",
        )
        return record

    def contract(
        self, entity_uuid: str, prop_name: str, reason: str = "Contraction request"
    ) -> Optional[RevisionRecord]:
        """AGM Contraction: retracts a belief by marking status RETRACTED and propagating justification loss."""
        prior = self.belief_engine.state.get_property(entity_uuid, prop_name)
        if prior is None:
            return None

        # Retract belief confidence to 0.0 and status to RETRACTED
        contracted_pv = PropertyValue(
            value=prior.value,
            confidence=0.0,
            source=prior.source,
            timestamp=time.time(),
            history=[prior.clone()] + [h.clone() for h in prior.history],
            evidence_history=list(prior.evidence_history),
            status=BeliefStatus.RETRACTED,
            version=prior.version,
            revision_number=prior.revision_number + 1,
        )
        self.belief_engine.state.set_property(entity_uuid, prop_name, contracted_pv)

        # Mark justification as OUT
        self.tms.justification_manager.invalidate_justification(entity_uuid, prop_name)

        # Propagate TMS justification loss recursively down to dependent child nodes
        self.tms.propagate_justifications(
            self.belief_engine.state, self.belief_engine.dependency_tracker.dependencies
        )

        record = RevisionRecord(
            revision_id=f"rev_{int(time.time() * 1000)}",
            operator="CONTRACTION",
            entity_uuid=entity_uuid,
            property_name=prop_name,
            old_value=prior.value,
            new_value=None,
            triggering_evidence_id=None,
            timestamp=time.time(),
            reason=reason,
            affected_nodes=[f"{entity_uuid}.{prop_name}"],
            previous_confidence=prior.confidence,
            new_confidence=0.0,
            revision_strategy="RETRACTION",
        )
        self.revision_history.append(record)
        log_event(
            "agm_contraction",
            f"Contracted belief {entity_uuid}.{prop_name} (status=RETRACTED)",
        )
        return record
