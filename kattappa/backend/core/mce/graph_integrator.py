"""MCE Component 5: Graph Integrator.

Maps extracted knowledge triples to KnowledgeGraph.add_node() and
add_relation() calls via the frozen KOS Core v1 interface.
Never writes directly to GraphStore.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from backend.core.knowledge_graph import KnowledgeGraph, EntityType, RelationType
from backend.core.logger import log_event
from backend.core.mce.semantic_extractor import KnowledgeTriple
from backend.core.provenance.coordinator import ProvenanceCoordinator
from backend.core.provenance.models import ProvenanceEvidenceItem, VerificationState
from backend.core.trust_evidence import EvidenceLevel

logger = logging.getLogger(__name__)


@dataclass
class IntegrationReport:
    nodes_added: int = 0
    relations_added: int = 0
    errors: int = 0


# Map common string relations to KG RelationType enum
_RELATION_MAP = {
    "USES": RelationType.USES,
    "DEPENDS_ON": RelationType.DEPENDS_ON,
    "RELATED_TO": RelationType.RELATED_TO,
    "CAUSED": RelationType.CAUSED,
    "IMPROVES": RelationType.IMPROVES,
    "PART_OF": RelationType.PART_OF,
    "WORKED_ON": RelationType.WORKED_ON,
    "LEARNED_FROM": RelationType.LEARNED_FROM,
}


class MCEGraphIntegrator:
    """Writes extracted knowledge triples into the Knowledge Graph."""

    @classmethod
    def integrate(cls, triples: List[KnowledgeTriple]) -> IntegrationReport:
        """Writes all valid triples to the KG via frozen v1 interface."""
        report = IntegrationReport()
        prov = ProvenanceCoordinator.get_instance()

        # Register MCE source
        prov.sources.register_source(
            source_id="mce_consolidator",
            name="MCE Memory Consolidator",
            source_type="tool",
            base_reputation=0.8,
        )

        for triple in triples:
            try:
                # Normalize node IDs (slug-style, lower, max 64 chars)
                subj_id = triple.subject.lower().replace(" ", "_")[:64]
                obj_id = triple.obj.lower().replace(" ", "_")[:64]

                # Create evidence link for these node / edge additions
                evidence = ProvenanceEvidenceItem.create(
                    source_id="mce_consolidator",
                    evidence_level=EvidenceLevel.HISTORICAL,
                    confidence=triple.confidence,
                    verification_state=VerificationState.UNVERIFIED,
                    context_citation=f"hm_episodes:{triple.source_episode_id}",
                    supports=True,
                    metadata={"extractor": "semantic_extractor"}
                )

                # Upsert subject node
                prov.kg.add_node_with_provenance(
                    node_id=subj_id,
                    name=triple.subject[:120],
                    entity_type=EntityType.CONCEPT,
                    properties={
                        "source": triple.source_episode_id,
                        "mce_extracted": True,
                    },
                    confidence=triple.confidence,
                    evidence=evidence,
                )
                report.nodes_added += 1

                # Upsert object node
                prov.kg.add_node_with_provenance(
                    node_id=obj_id,
                    name=triple.obj[:120],
                    entity_type=EntityType.CONCEPT,
                    properties={
                        "source": triple.source_episode_id,
                        "mce_extracted": True,
                    },
                    confidence=triple.confidence,
                    evidence=evidence,
                )
                report.nodes_added += 1

                # Map relation string to enum (default RELATED_TO)
                rel_key = triple.relation.upper().replace(" ", "_")
                rel_type = _RELATION_MAP.get(rel_key, RelationType.RELATED_TO)

                prov.kg.add_edge_with_provenance(
                    source_id=subj_id,
                    target_id=obj_id,
                    relation_type=rel_type,
                    confidence=triple.confidence,
                    properties={"source_episode": triple.source_episode_id},
                    evidence=evidence,
                )
                report.relations_added += 1

            except Exception as exc:
                logger.error("GraphIntegrator: failed to write triple (%s): %s", triple, exc)
                report.errors += 1

        log_event(
            "mce_graph_integrated",
            f"Graph integration: nodes_added={report.nodes_added}, "
            f"relations_added={report.relations_added}, errors={report.errors}",
        )
        return report
