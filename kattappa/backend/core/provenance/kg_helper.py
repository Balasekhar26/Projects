"""Provenance Engine Component 5: KG Helper.

Wraps KnowledgeGraph writes with automatic provenance registration
and handles citation retrieval for nodes and edges.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.knowledge_graph import KnowledgeGraph, EntityType, RelationType
from backend.core.provenance.models import ProvenanceEvidenceItem, ProvenanceRecord, Source
from backend.core.provenance.store import ProvenanceStore

logger = logging.getLogger(__name__)


class ProvenanceKGHelper:
    """Wrapper that coordinates KG writes with WSE/Provenance metadata."""

    def __init__(self, store: ProvenanceStore) -> None:
        self._store = store
        self._kg = KnowledgeGraph.get_instance()

    def add_node_with_provenance(
        self,
        node_id: str,
        name: str,
        entity_type: str | EntityType,
        evidence: ProvenanceEvidenceItem,
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
        source_layer: Optional[str] = None,
    ) -> Any:
        """Registers the evidence item, writes to the KG, and links target_id -> evidence_id."""
        # 1. Persist the evidence to the store
        self._store.save_evidence(evidence)

        # 2. Add node to the KG, passing the evidence_id in the evidence list
        node = self._kg.add_node(
            node_id=node_id,
            name=name,
            entity_type=entity_type,
            properties=properties,
            confidence=confidence,
            source_layer=source_layer,
            evidence=[evidence.evidence_id],
        )

        # 3. Create the provenance link mapping target_id -> evidence_id
        # We use the generated node ID (or the node_id argument)
        self._store.link_target_to_evidence(node_id, evidence.evidence_id)
        return node

    def add_edge_with_provenance(
        self,
        source_id: str,
        target_id: str,
        relation_type: str | RelationType,
        evidence: ProvenanceEvidenceItem,
        weight: float = 1.0,
        confidence: float = 1.0,
        source_layer: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Registers the evidence item, writes to the KG, and links the edge to the evidence."""
        # 1. Persist the evidence to the store
        self._store.save_evidence(evidence)

        # 2. Add edge to the KG, passing evidence_id in the list
        edge = self._kg.add_edge(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            weight=weight,
            confidence=confidence,
            source_layer=source_layer,
            evidence=[evidence.evidence_id],
            properties=properties,
        )

        # 3. Create the provenance link mapping edge_id -> evidence_id
        # In Core v1, the edge has a generated unique ID (edge.id)
        edge_id = getattr(edge, "id", f"{source_id}_{target_id}_{relation_type}")
        self._store.link_target_to_evidence(edge_id, evidence.evidence_id)
        return edge

    def get_provenance_record(self, target_id: str) -> ProvenanceRecord:
        """Returns the ProvenanceRecord mapping the target_id to evidence IDs."""
        return self._store.get_provenance_record(target_id)

    def get_evidence_for_target(self, target_id: str) -> List[ProvenanceEvidenceItem]:
        """Returns the list of ProvenanceEvidenceItem records supporting the target."""
        return self._store.get_evidence_for_target(target_id)
