"""Belief Management Component 9: Coordinator.

Provides the single entry point coordinating all belief store,
dependency propagation, contradiction checks, and KG synchronizations.
"""
from __future__ import annotations

import time
import uuid
import logging
from typing import Any, Dict, List, Optional


from backend.core.cos.state_representation import BeliefStatus
from backend.core.beliefs.belief import Belief, Justification, BeliefDependency
from backend.core.beliefs.belief_store import BeliefStore
from backend.core.beliefs.dependency_graph import DependencyGraph
from backend.core.beliefs.contradiction_detector import ContradictionDetector, BeliefConflict
from backend.core.beliefs.confidence_engine import ConfidenceEngine
from backend.core.beliefs.belief_revision import BeliefRevisionEngine
from backend.core.beliefs.explanation_engine import ExplanationEngine
from backend.core.provenance.coordinator import ProvenanceCoordinator
from backend.core.provenance.models import ProvenanceEvidenceItem
from backend.core.knowledge_graph import KnowledgeGraph, EntityType, RelationType
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


class BeliefCoordinator:
    """Unified entry point coordinating all truth maintenance operations."""

    _instance: Optional["BeliefCoordinator"] = None

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._store = BeliefStore(db_path=db_path)
        self._graph = DependencyGraph(self._store)
        self._contradictions = ContradictionDetector(self._store)
        self._revision = BeliefRevisionEngine(self._store)
        self._explanations = ExplanationEngine(self._store)
        self._prov = ProvenanceCoordinator.get_instance()

    @classmethod
    def get_instance(cls) -> "BeliefCoordinator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls, db_path: Optional[str] = None) -> "BeliefCoordinator":
        """For testing: replaces the singleton instance with a custom DB file."""
        cls._instance = cls(db_path=db_path)
        return cls._instance

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def store(self) -> BeliefStore:
        return self._store

    @property
    def graph(self) -> DependencyGraph:
        return self._graph

    @property
    def contradictions(self) -> ContradictionDetector:
        return self._contradictions

    @property
    def explanations(self) -> ExplanationEngine:
        return self._explanations

    # ------------------------------------------------------------------
    # Core Operations
    # ------------------------------------------------------------------

    def process_assertion(
        self,
        subject: str,
        predicate: str,
        value: Any,
        evidence: ProvenanceEvidenceItem,
        rationale: str = "",
        dependencies: Optional[List[str]] = None,
        valid_until: Optional[float] = None,
    ) -> Belief:
        """Processes a new belief assertion, validating it against conflicts and propagating truth bounds.

        Saves the resulting active belief in the Knowledge Graph automatically.
        """
        # 1. Register evidence in Provenance Store first
        self._prov.store.save_evidence(evidence)

        # 2. Gather all evidence for this subject+predicate to calculate composite confidence
        evidence_list = self._prov.kg.get_evidence_for_target(subject)
        # Append the new evidence if not already listed
        if not any(e.evidence_id == evidence.evidence_id for e in evidence_list):
            evidence_list.append(evidence)

        confidence = ConfidenceEngine.calculate_confidence(evidence_list, statement=f"{subject}.{predicate}")

        # 3. Create candidate belief object
        candidate = Belief.create(
            subject=subject,
            predicate=predicate,
            value=value,
            confidence=confidence,
            truth_status=BeliefStatus.BELIEVED if confidence >= 0.5 else BeliefStatus.HYPOTHESIS,
            source_ids=[evidence.source_id],
            evidence_ids=[evidence.evidence_id],
            valid_until=valid_until,
        )

        # 4. Check for conflicts with existing active beliefs
        prior = self._store.get_belief_by_claim(subject, predicate)
        if prior:
            conflict = self._contradictions.check_conflict(candidate)
            if conflict:
                # Conflict resolution: check confidence scores
                if candidate.confidence > prior.confidence:
                    # Incoming belief is stronger: retract/refute prior belief, keep candidate
                    self._revision.revise_belief(prior, prior.claim_value, prior.confidence * 0.5, BeliefStatus.REFUTED)
                    # Candidate remains active
                    self._store.save_belief(candidate)
                    log_event("tms_conflict_resolved", f"Incoming belief '{value}' superseded prior '{prior.claim_value}'")
                else:
                    # Prior belief is stronger: incoming is stored as refuted hypothesis
                    candidate = Belief(
                        belief_id=candidate.belief_id,
                        claim_subject=candidate.claim_subject,
                        claim_predicate=candidate.claim_predicate,
                        claim_value=candidate.claim_value,
                        confidence=candidate.confidence,
                        truth_status=BeliefStatus.REFUTED,
                        source_ids=candidate.source_ids,
                        evidence_ids=candidate.evidence_ids,
                        created_at=candidate.created_at,
                        updated_at=time.time(),
                        valid_from=candidate.valid_from,
                        valid_until=candidate.valid_until,
                        version=candidate.version,
                        metadata=candidate.metadata,
                    )
                    self._store.save_belief(candidate)
                    log_event("tms_conflict_resolved", f"Prior belief '{prior.claim_value}' resisted incoming '{value}'")
            else:
                # No contradiction — update version
                candidate = Belief(
                    belief_id=prior.belief_id,
                    claim_subject=candidate.claim_subject,
                    claim_predicate=candidate.claim_predicate,
                    claim_value=value,
                    confidence=confidence,
                    truth_status=candidate.truth_status,
                    source_ids=list(set(prior.source_ids + candidate.source_ids)),
                    evidence_ids=list(set(prior.evidence_ids + candidate.evidence_ids)),
                    created_at=prior.created_at,
                    updated_at=time.time(),
                    valid_from=prior.valid_from,
                    valid_until=valid_until,
                    version=prior.version + 1,
                    metadata=candidate.metadata,
                )
                self._store.save_belief(candidate)
        else:
            # Fresh belief
            self._store.save_belief(candidate)

        # 5. Save justification entry
        just_id = f"just_{uuid.uuid4().hex[:12]}"
        just = Justification(
            justification_id=just_id,
            belief_id=candidate.belief_id,
            rationale=rationale or f"Sourced from {evidence.source_id}",
            evidence_ids=[evidence.evidence_id],
            dependency_ids=dependencies or [],
            created_at=time.time(),
        )
        self._store.save_justification(just)

        # 6. Establish dependencies in dependency graph
        if dependencies:
            for dep_id in dependencies:
                try:
                    self._graph.add_dependency(dep_id, candidate.belief_id)
                except ValueError as e:
                    logger.warning("Failed to establish dependency: %s", e)

        # 7. Propagate downstream confidence boundaries
        self._graph.propagate_confidence(candidate)

        # 8. Synchronize/Write validated active belief state to the Knowledge Graph
        # KG nodes and edges are mapped here based on belief validity and status
        self._sync_kg_belief(candidate, evidence)

        return candidate

    def _sync_kg_belief(self, belief: Belief, evidence: ProvenanceEvidenceItem) -> None:
        """Propagates active validated belief properties directly to KnowledgeGraph."""
        try:
            kg = KnowledgeGraph.get_instance()
            node_data = kg.get_node(belief.claim_subject)
            node_props = dict(node_data.get("properties", {})) if node_data else {}

            if belief.truth_status in (BeliefStatus.BELIEVED, BeliefStatus.HYPOTHESIS):
                # Write attribute value to node properties
                node_props[belief.claim_predicate] = belief.claim_value
                node_props["provenance_belief_id"] = belief.belief_id

                kg.add_node(
                    name=belief.claim_subject,
                    entity_type=EntityType.CONCEPT,
                    node_id=belief.claim_subject,
                    properties=node_props,
                    confidence=belief.confidence,
                    belief_state=belief.truth_status.value,
                    evidence=[evidence.evidence_id],
                )
                # Register link in Provenance store
                self._prov.store.link_target_to_evidence(belief.claim_subject, evidence.evidence_id)
            elif belief.truth_status in (BeliefStatus.RETRACTED, BeliefStatus.REFUTED):
                # Retracted or refuted: remove property or flag it
                if belief.claim_predicate in node_props:
                    del node_props[belief.claim_predicate]
                node_props["provenance_belief_id"] = belief.belief_id

                kg.add_node(
                    name=belief.claim_subject,
                    entity_type=EntityType.CONCEPT,
                    node_id=belief.claim_subject,
                    properties=node_props,
                    confidence=0.0,
                    belief_state=belief.truth_status.value,
                    evidence=[evidence.evidence_id],
                )
        except Exception as exc:
            logger.error("BeliefCoordinator: failed to sync belief with KG: %s", exc)
