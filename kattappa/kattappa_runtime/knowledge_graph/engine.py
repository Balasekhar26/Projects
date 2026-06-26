"""
KnowledgeGraph — unified facade combining GraphStore + GraphQuery
=================================================================

This is the single public object you interact with.

Usage
-----
    from kattappa_runtime.knowledge_graph import KnowledgeGraph, EntityType, RelationshipType

    kg = KnowledgeGraph(store_dir="/path/to/kg_data")

    # Add entities
    rf   = kg.add("RF Systems",         EntityType.RESEARCH_TOPIC)
    smith = kg.add("Smith Chart",        EntityType.TOOL)
    imp  = kg.add("Impedance Matching",  EntityType.CONCEPT)
    bala = kg.add("Bala Sekhar",         EntityType.PERSON)

    # Add relationships
    kg.relate(rf,   smith, RelationshipType.USES,         weight=0.9)
    kg.relate(rf,   imp,   RelationshipType.DEPENDS_ON,   weight=0.85)
    kg.relate(bala, rf,    RelationshipType.WORKED_ON,    weight=0.7)

    # Query
    related = kg.find_related("RF Systems")
    gaps    = kg.find_knowledge_gaps("RF Systems", learner_name="Bala Sekhar")
    tools   = kg.find_tools_for_skill("RF Systems")

    # Print summary
    print(kg.stats().summary())

Integration with cognitive pipeline
------------------------------------
    # Auto-extract from a ResearchReport
    kg.ingest_research_report(report, domain="rf_systems")

    # Auto-extract from a LearningRecord
    kg.ingest_learning_record(record)

    # Auto-extract from a MistakeEntry
    kg.ingest_mistake(mistake, domain="rf_systems")
"""

from __future__ import annotations

import re
from typing import List, Optional, TYPE_CHECKING

from kattappa_runtime.knowledge_graph.schema import (
    Node, Edge, EntityType, RelationshipType, GraphStats
)
from kattappa_runtime.knowledge_graph.store  import GraphStore
from kattappa_runtime.knowledge_graph.query  import GraphQuery, TraversalResult, PathResult

if TYPE_CHECKING:
    from kattappa_runtime.research.schema   import ResearchReport
    from kattappa_runtime.learning.schema   import LearningRecord
    from kattappa_runtime.reflection.schema import MistakeEntry


class KnowledgeGraph:
    """
    Unified Knowledge Graph facade.

    Combines GraphStore (persistence) and GraphQuery (traversal)
    into a single coherent interface.

    Parameters
    ----------
    store_dir : str
        Directory for JSONL persistence files.
    """

    def __init__(self, store_dir: str):
        self._store = GraphStore(store_dir=store_dir)
        self._query = GraphQuery(store=self._store)

    # ------------------------------------------------------------------
    # Core write operations
    # ------------------------------------------------------------------

    def add(
        self,
        name:        str,
        entity_type: EntityType = EntityType.CONCEPT,
        description: str        = "",
        confidence:  float      = 1.0,
        **properties,
    ) -> Node:
        """
        Add an entity to the graph (or increment its mention_count
        if an entity with this name + type already exists).

        Returns the Node now in the graph.
        """
        node = Node(
            name        = name,
            entity_type = entity_type,
            description = description,
            confidence  = confidence,
            properties  = {k: str(v) for k, v in properties.items()},
        )
        return self._store.add_node(node)

    def relate(
        self,
        source:       Node,
        target:       Node,
        relationship: RelationshipType,
        weight:       float = 0.5,
        evidence:     str   = "",
    ) -> Edge:
        """
        Add a directed relationship source → target.
        If the same (source, target, relationship) already exists,
        updates the weight to max(existing, new).

        Returns the Edge now in the graph.
        """
        edge = Edge(
            source_id    = source.node_id,
            target_id    = target.node_id,
            relationship = relationship,
            weight       = weight,
            evidence     = evidence,
        )
        return self._store.add_edge(edge)

    def relate_by_name(
        self,
        source_name:   str,
        target_name:   str,
        relationship:  RelationshipType,
        weight:        float = 0.5,
        evidence:      str   = "",
        source_type:   EntityType = EntityType.CONCEPT,
        target_type:   EntityType = EntityType.CONCEPT,
    ) -> Optional[Edge]:
        """
        Add a relationship between two named entities.
        Creates the nodes if they don't exist yet.
        """
        src = self._store.find_by_name(source_name) or self.add(source_name, source_type)
        tgt = self._store.find_by_name(target_name) or self.add(target_name, target_type)
        return self.relate(src, tgt, relationship, weight=weight, evidence=evidence)

    # ------------------------------------------------------------------
    # Core read operations
    # ------------------------------------------------------------------

    def get(self, name: str, entity_type: Optional[EntityType] = None) -> Optional[Node]:
        return self._store.find_by_name(name, entity_type)

    def node_count(self) -> int:
        return self._store.node_count()

    def edge_count(self) -> int:
        return self._store.edge_count()

    def stats(self) -> GraphStats:
        return self._store.stats()

    # ------------------------------------------------------------------
    # Query delegation — all 5 user-specified queries
    # ------------------------------------------------------------------

    def find_related(
        self,
        name:          str,
        entity_type:   Optional[EntityType]       = None,
        relation_type: Optional[RelationshipType] = None,
        max_depth:     int                        = 2,
        min_weight:    float                      = 0.0,
    ) -> List[TraversalResult]:
        return self._query.find_related(
            name=name, entity_type=entity_type,
            relation_type=relation_type,
            max_depth=max_depth, min_weight=min_weight,
        )

    def find_dependencies(self, name: str, max_depth: int = 3) -> List[TraversalResult]:
        return self._query.find_dependencies(name, max_depth=max_depth)

    def find_prerequisites(self, name: str, max_depth: int = 3) -> List[TraversalResult]:
        return self._query.find_prerequisites(name, max_depth=max_depth)

    def find_tools_for_skill(self, skill_name: str) -> List[Node]:
        return self._query.find_tools_for_skill(skill_name)

    def find_knowledge_gaps(
        self, topic_name: str, learner_name: str = "kattappa"
    ) -> List[Node]:
        return self._query.find_knowledge_gaps(topic_name, learner_name=learner_name)

    def find_path(self, source_name: str, target_name: str, max_depth: int = 5) -> PathResult:
        return self._query.find_path(source_name, target_name, max_depth=max_depth)

    def get_subgraph(self, center_name: str, radius: int = 2):
        return self._query.get_subgraph(center_name, radius=radius)

    def search(self, query_text: str, entity_type: Optional[EntityType] = None) -> List[Node]:
        return self._query.search_nodes(query_text, entity_type=entity_type)

    def get_hubs(self, n: int = 10, entity_type: Optional[EntityType] = None) -> List[Node]:
        return self._query.get_hubs(n=n, entity_type=entity_type)

    # ------------------------------------------------------------------
    # Cognitive pipeline ingestion
    # ------------------------------------------------------------------

    def ingest_research_report(
        self,
        report,         # ResearchReport
        domain: str     = "general",
        weight: float   = 0.7,
    ) -> int:
        """
        Auto-extract entities and relationships from a ResearchReport.

        Adds:
          - A RESEARCH_TOPIC node for report.topic
          - CONCEPT nodes for each key_fact (heuristic extraction)
          - RELATED_TO edges connecting them

        Returns number of nodes added (including duplicates that incremented count).
        """
        if not report:
            return 0

        added = 0
        topic_node = self.add(report.topic, EntityType.RESEARCH_TOPIC,
                              description=report.summary[:200] if report.summary else "",
                              confidence=0.9, domain=domain)
        added += 1

        # Extract simple noun phrases from key facts
        for fact in (report.key_facts or [])[:10]:
            concepts = self._extract_concepts(fact)
            for c in concepts:
                concept_node = self.add(c, EntityType.CONCEPT,
                                        confidence=0.7, source="research")
                self.relate(topic_node, concept_node,
                            RelationshipType.RELATED_TO, weight=weight,
                            evidence=f"research:{report.topic[:40]}")
                added += 1

        return added

    def ingest_learning_record(
        self,
        record,         # LearningRecord
        learner_name: str = "kattappa",
        weight: float     = 0.8,
    ) -> int:
        """
        Record a learning event in the graph.

        Adds:
          - LEARNED_FROM edge from learner → concept
          - Updates confidence based on record.confidence_score
        """
        if not record or not getattr(record, "domain", None):
            return 0

        learner = (self._store.find_by_name(learner_name)
                   or self.add(learner_name, EntityType.PERSON))
        concept = self.add(record.domain, EntityType.CONCEPT,
                           confidence=getattr(record, "confidence_score", 0.7))
        self.relate(learner, concept, RelationshipType.LEARNED_FROM,
                    weight=weight,
                    evidence=f"learning_record:{getattr(record, 'record_id', '')[:8]}")
        return 2  # learner + concept

    def ingest_mistake(
        self,
        mistake,        # MistakeEntry
        domain: str     = "general",
        learner_name: str = "kattappa",
    ) -> int:
        """
        Record a mistake as a knowledge gap in the graph.
        Adds a CONCEPT node for the weakness with low confidence.
        """
        if not mistake:
            return 0

        weakness_name = getattr(mistake, "root_cause", None) or domain
        weakness = self.add(weakness_name, EntityType.CONCEPT,
                            confidence=0.3,
                            description=f"Knowledge gap from mistake in {domain}",
                            source="mistake_log")
        learner = (self._store.find_by_name(learner_name)
                   or self.add(learner_name, EntityType.PERSON))
        domain_node = self.add(domain, EntityType.DOMAIN, confidence=0.8)

        self.relate(domain_node, weakness, RelationshipType.DEPENDS_ON, weight=0.6)
        return 3

    # ------------------------------------------------------------------
    # Visual dump
    # ------------------------------------------------------------------

    def describe(self, name: str) -> str:
        """
        Human-readable description of an entity and its relationships.

        Example:
            RF Systems [research_topic]
              → uses        Smith Chart          (weight=0.90)
              → depends_on  Impedance Matching   (weight=0.85)
              ← worked_on   Bala Sekhar          (weight=0.70)
        """
        node = self._store.find_by_name(name)
        if not node:
            return f"Entity '{name}' not found in knowledge graph."

        lines = [f"\n{node.name} [{node.entity_type.value}]"]
        if node.description:
            lines.append(f"  {node.description[:100]}")

        out_edges = self._store.get_edges_from(node.node_id)
        for e in out_edges:
            tgt = self._store.get_node(e.target_id)
            if tgt:
                lines.append(
                    f"  → {e.relationship.value:<14} {tgt.name:<30} (weight={e.weight:.2f})"
                )

        in_edges = self._store.get_edges_to(node.node_id)
        for e in in_edges:
            src = self._store.get_node(e.source_id)
            if src:
                lines.append(
                    f"  ← {e.relationship.value:<14} {src.name:<30} (weight={e.weight:.2f})"
                )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_concepts(text: str) -> List[str]:
        """
        Heuristic: extract candidate concept phrases from a sentence.
        Takes 2-3 word title-case chunks or quoted terms.
        Keeps it simple — no NLP dependency required.
        """
        concepts = []
        # Quoted terms
        quoted = re.findall(r'"([^"]{3,40})"', text)
        concepts.extend(quoted)
        # Capitalized 1-3 word phrases (not at sentence start)
        caps = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b', text)
        concepts.extend(c for c in caps if len(c) > 3)
        # Deduplicate
        seen: set = set()
        result: List[str] = []
        for c in concepts:
            c_lower = c.lower()
            if c_lower not in seen:
                seen.add(c_lower)
                result.append(c)
        return result[:5]  # cap at 5 per fact
