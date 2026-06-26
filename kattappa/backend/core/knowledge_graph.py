"""Step 29: Unified Knowledge Graph for Kattappa.

Provides structured knowledge representation with typed entities,
weighted relationships, cross-layer entity reconciliation, and
graph-based query capabilities.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from backend.core.graph_store import GraphStore
from backend.core.graph_query import GraphQueryEngine
from backend.core.kg_sync import SyncManager

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EntityType(str, Enum):
    """Typed entity categories for KG nodes."""
    PERSON = "PERSON"
    CONCEPT = "CONCEPT"
    SKILL = "SKILL"
    TOOL = "TOOL"
    PROJECT = "PROJECT"
    GOAL = "GOAL"
    DOCUMENT = "DOCUMENT"
    RESEARCH_TOPIC = "RESEARCH_TOPIC"
    COMPONENT = "COMPONENT"
    DEVICE = "DEVICE"
    RESOURCE = "RESOURCE"
    FACT = "FACT"
    HYPOTHESIS = "HYPOTHESIS"
    EVENT = "EVENT"

    @classmethod
    def coerce(cls, value: "EntityType | str") -> "EntityType":
        try:
            return value if isinstance(value, cls) else cls(str(value).strip().upper())
        except ValueError:
            return cls.CONCEPT


class RelationType(str, Enum):
    """Relationship types for KG edges."""
    USES = "USES"
    DEPENDS_ON = "DEPENDS_ON"
    LEARNED_FROM = "LEARNED_FROM"
    RELATED_TO = "RELATED_TO"
    PART_OF = "PART_OF"
    WORKED_ON = "WORKED_ON"
    CAUSED = "CAUSED"
    IMPROVES = "IMPROVES"
    IS_A = "IS_A"
    IMPLEMENTS = "IMPLEMENTS"
    EXTENDS = "EXTENDS"
    CONTRADICTS = "CONTRADICTS"
    SUPERSEDES = "SUPERSEDES"
    CONTAINS = "CONTAINS"
    AFFECTS = "AFFECTS"
    PREREQUISITE_OF = "PREREQUISITE_OF"
    STUDIED_BY = "STUDIED_BY"
    PRODUCED_BY = "PRODUCED_BY"
    TRIGGERED = "TRIGGERED"

    @classmethod
    def coerce(cls, value: "RelationType | str") -> "RelationType":
        try:
            return value if isinstance(value, cls) else cls(str(value).strip().upper())
        except ValueError:
            return cls.RELATED_TO


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class KGNode:
    """A Knowledge Graph node."""
    id: str
    name: str
    entity_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source_layer: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class KGEdge:
    """A Knowledge Graph edge."""
    id: str
    source_id: str
    target_id: str
    relation_type: str
    weight: float = 1.0
    confidence: float = 1.0
    evidence: List[str] = field(default_factory=list)
    source_layer: Optional[str] = None
    created_at: str = ""


# ---------------------------------------------------------------------------
# KnowledgeGraph
# ---------------------------------------------------------------------------

class KnowledgeGraph:
    """Unified Knowledge Graph combining structured storage, graph queries,
    and cross-layer synchronization.

    Parameters
    ----------
    data_dir:
        Directory where the ``knowledge_graph.db`` SQLite file is stored.
    """

    def __init__(self, data_dir: str) -> None:
        import os
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "knowledge_graph.db")
        self._store = GraphStore(db_path)
        self._query = GraphQueryEngine(self._store)
        self._sync_manager = SyncManager(self._store)

    # ------------------------------------------------------------------ #
    #  CRUD                                                               #
    # ------------------------------------------------------------------ #

    def add_node(
        self,
        name: str,
        entity_type: str | EntityType,
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
        source_layer: Optional[str] = None,
    ) -> KGNode:
        """Add a new node to the knowledge graph."""
        etype = EntityType.coerce(entity_type).value if isinstance(entity_type, str) else entity_type.value
        nid = self._store.insert_node(
            name=name,
            entity_type=etype,
            properties=properties,
            confidence=confidence,
            source_layer=source_layer,
        )
        raw = self._store.get_node(nid)
        return self._to_kg_node(raw) if raw else KGNode(id=nid, name=name, entity_type=etype)

    def add_edge(
        self,
        source_name: str,
        target_name: str,
        relation_type: str | RelationType,
        weight: float = 1.0,
        confidence: float = 1.0,
        evidence: Optional[List[str]] = None,
        source_layer: Optional[str] = None,
    ) -> KGEdge:
        """Add a directed edge between two entities (resolved by name).

        If either endpoint does not exist yet, it will be auto-created
        with entity_type CONCEPT.
        """
        rel = RelationType.coerce(relation_type).value if isinstance(relation_type, str) else relation_type.value
        src = self._resolve_name(source_name)
        tgt = self._resolve_name(target_name)
        eid = self._store.insert_edge(
            source_id=src["id"],
            target_id=tgt["id"],
            relation_type=rel,
            weight=weight,
            confidence=confidence,
            evidence=evidence,
            source_layer=source_layer,
        )
        edges = self._store.get_edges_from(src["id"], relation_type=rel)
        for e in edges:
            if e["id"] == eid:
                return self._to_kg_edge(e)
        return KGEdge(id=eid, source_id=src["id"], target_id=tgt["id"], relation_type=rel)

    def update_node(
        self,
        node_id: str,
        **kwargs: Any,
    ) -> bool:
        """Update node attributes. Accepted kwargs: name, entity_type, properties, confidence, source_layer."""
        return self._store.update_node(node_id, **kwargs)

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all its edges."""
        return self._store.delete_node(node_id)

    def remove_edge(self, edge_id: str) -> bool:
        """Remove an edge by id."""
        return self._store.delete_edge(edge_id)

    # ------------------------------------------------------------------ #
    #  Entity Reconciliation                                              #
    # ------------------------------------------------------------------ #

    def register_alias(self, canonical_id: str, alias_name: str, alias_type: Optional[str] = None) -> None:
        """Register an alias for a canonical node."""
        self._store.insert_alias(canonical_id, alias_name, alias_type)

    def resolve_entity(self, name: str) -> Optional[KGNode]:
        """Resolve a name to its canonical KG node (checks aliases first, then name match)."""
        # Try alias resolution
        alias_node = self._store.resolve_alias(name)
        if alias_node:
            return self._to_kg_node(alias_node)
        # Try direct name lookup
        direct = self._store.get_node_by_name(name)
        if direct:
            return self._to_kg_node(direct)
        return None

    def merge_entities(self, node_ids: List[str]) -> KGNode:
        """Merge multiple nodes into one, consolidating edges and properties.

        The first id in *node_ids* becomes the canonical node; all others
        are merged into it and deleted.
        """
        if not node_ids:
            raise ValueError("node_ids must not be empty")
        if len(node_ids) == 1:
            raw = self._store.get_node(node_ids[0])
            return self._to_kg_node(raw) if raw else KGNode(id=node_ids[0], name="unknown", entity_type="CONCEPT")

        canonical_id = node_ids[0]
        canonical_raw = self._store.get_node(canonical_id)
        if not canonical_raw:
            raise ValueError(f"Canonical node {canonical_id} not found")

        merged_props = dict(canonical_raw.get("properties", {}))
        merged_conf = canonical_raw.get("confidence", 1.0)
        aliases_added: list[str] = []

        for other_id in node_ids[1:]:
            other = self._store.get_node(other_id)
            if not other:
                continue

            # Merge properties
            other_props = other.get("properties", {})
            for k, v in other_props.items():
                if k not in merged_props:
                    merged_props[k] = v

            # Take higher confidence
            merged_conf = max(merged_conf, other.get("confidence", 0.0))

            # Re-point incoming edges to canonical
            in_edges = self._store.get_edges_to(other_id)
            out_edges = self._store.get_edges_from(other_id)
            for e in in_edges:
                if e["source_id"] != canonical_id:
                    self._store.insert_edge(
                        source_id=e["source_id"],
                        target_id=canonical_id,
                        relation_type=e["relation_type"],
                        weight=e.get("weight", 1.0),
                        confidence=e.get("confidence", 1.0),
                        evidence=e.get("evidence", []),
                        source_layer=e.get("source_layer"),
                    )
            for e in out_edges:
                if e["target_id"] != canonical_id:
                    self._store.insert_edge(
                        source_id=canonical_id,
                        target_id=e["target_id"],
                        relation_type=e["relation_type"],
                        weight=e.get("weight", 1.0),
                        confidence=e.get("confidence", 1.0),
                        evidence=e.get("evidence", []),
                        source_layer=e.get("source_layer"),
                    )

            # Register old name as alias
            self._store.insert_alias(canonical_id, other["name"])
            aliases_added.append(other["name"])

            # Delete the merged node
            self._store.delete_node(other_id)

        self._store.update_node(canonical_id, properties=merged_props, confidence=merged_conf)
        raw = self._store.get_node(canonical_id)
        return self._to_kg_node(raw) if raw else KGNode(id=canonical_id, name=canonical_raw["name"], entity_type=canonical_raw["entity_type"])

    # ------------------------------------------------------------------ #
    #  User-Facing Query API                                              #
    # ------------------------------------------------------------------ #

    def find_related(
        self,
        entity_name: str,
        relation_type: Optional[str] = None,
        max_depth: int = 2,
    ) -> List[Tuple[KGNode, List[str]]]:
        """Find nodes related to *entity_name* within *max_depth* hops.

        Returns a list of ``(KGNode, edge_path)`` tuples.
        """
        node = self._resolve_name(entity_name)
        if not node:
            return []
        traversal = self._query.bfs_traverse(
            node["id"],
            max_depth=max_depth,
            relation_filter=relation_type,
        )
        results: list[Tuple[KGNode, List[str]]] = []
        for raw_node, _depth, path in traversal:
            if raw_node["id"] != node["id"]:
                results.append((self._to_kg_node(raw_node), path))
        return results

    def find_dependencies(self, entity_name: str) -> List[KGNode]:
        """Find all nodes that *entity_name* depends on (DEPENDS_ON outgoing edges)."""
        node = self._resolve_name(entity_name)
        if not node:
            return []
        edges = self._store.get_edges_from(node["id"], relation_type="DEPENDS_ON")
        results: list[KGNode] = []
        for e in edges:
            dep = self._store.get_node(e["target_id"])
            if dep:
                results.append(self._to_kg_node(dep))
        return results

    def find_prerequisites(self, entity_name: str) -> List[KGNode]:
        """Find prerequisite nodes for *entity_name* (incoming PREREQUISITE_OF edges)."""
        node = self._resolve_name(entity_name)
        if not node:
            return []
        edges = self._store.get_edges_to(node["id"], relation_type="PREREQUISITE_OF")
        results: list[KGNode] = []
        for e in edges:
            prereq = self._store.get_node(e["source_id"])
            if prereq:
                results.append(self._to_kg_node(prereq))
        return results

    def find_tools_for_skill(self, skill_name: str) -> List[KGNode]:
        """Find TOOL nodes connected to *skill_name* via USES relation."""
        node = self._resolve_name(skill_name)
        if not node:
            return []
        edges = self._store.get_edges_from(node["id"], relation_type="USES")
        tools: list[KGNode] = []
        for e in edges:
            target = self._store.get_node(e["target_id"])
            if target and target.get("entity_type") == "TOOL":
                tools.append(self._to_kg_node(target))
        return tools

    def find_knowledge_gaps(self, goal_or_topic: str) -> List[Dict[str, Any]]:
        """Identify concepts/skills not yet learned that are needed for *goal_or_topic*."""
        node = self._resolve_name(goal_or_topic)
        if not node:
            return []
        return self._query.find_knowledge_gaps(node["id"])

    # ------------------------------------------------------------------ #
    #  Graph Traversal                                                    #
    # ------------------------------------------------------------------ #

    def traverse(
        self,
        start_name: str,
        max_depth: int = 3,
        min_confidence: float = 0.0,
        relation_filter: Optional[str] = None,
    ) -> List[Tuple[KGNode, int, List[str]]]:
        """BFS traversal from *start_name*."""
        node = self._resolve_name(start_name)
        if not node:
            return []
        raw = self._query.bfs_traverse(node["id"], max_depth=max_depth, min_confidence=min_confidence, relation_filter=relation_filter)
        return [(self._to_kg_node(n), d, p) for n, d, p in raw]

    def find_path(self, start_name: str, end_name: str) -> List[KGEdge]:
        """Find the shortest weighted path between two named entities."""
        src = self._resolve_name(start_name)
        tgt = self._resolve_name(end_name)
        if not src or not tgt:
            return []
        raw_edges = self._query.find_shortest_path(src["id"], tgt["id"])
        return [self._to_kg_edge(e) for e in raw_edges]

    def get_subgraph(self, center_name: str, radius: int = 2) -> Dict[str, Any]:
        """Extract a subgraph around *center_name*."""
        node = self._resolve_name(center_name)
        if not node:
            return {"nodes": [], "edges": []}
        raw = self._query.get_subgraph(node["id"], radius=radius)
        return {
            "nodes": [self._to_kg_node(n) for n in raw.get("nodes", [])],
            "edges": [self._to_kg_edge(e) for e in raw.get("edges", [])],
        }

    # ------------------------------------------------------------------ #
    #  Cross-Layer Sync                                                   #
    # ------------------------------------------------------------------ #

    def sync_from_semantic(self, db_path: str) -> Dict[str, int]:
        """Sync Semantic Memory into the KG."""
        from backend.core.kg_sync import SemanticSyncAdapter
        adapter = SemanticSyncAdapter()
        return adapter.sync(self._store, db_path)

    def sync_from_world_model(self, db_path: str) -> Dict[str, int]:
        """Sync World Model into the KG."""
        from backend.core.kg_sync import WorldModelSyncAdapter
        adapter = WorldModelSyncAdapter()
        return adapter.sync(self._store, db_path)

    def sync_from_episodic(self, db_path: str) -> Dict[str, int]:
        """Sync Episodic Memory into the KG."""
        from backend.core.kg_sync import EpisodicSyncAdapter
        adapter = EpisodicSyncAdapter()
        return adapter.sync(self._store, db_path)

    def full_sync(
        self,
        semantic_db: Optional[str] = None,
        world_db: Optional[str] = None,
        episodic_db: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run full synchronization of all available layers."""
        return self._sync_manager.full_sync(semantic_db, world_db, episodic_db)

    # ------------------------------------------------------------------ #
    #  Internal Helpers                                                    #
    # ------------------------------------------------------------------ #

    def _resolve_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Resolve *name* to a raw node dict (alias → name match)."""
        alias_node = self._store.resolve_alias(name)
        if alias_node:
            return alias_node
        return self._store.get_node_by_name(name)

    @staticmethod
    def _to_kg_node(raw: Dict[str, Any]) -> KGNode:
        """Convert a raw store node dict to a KGNode dataclass."""
        return KGNode(
            id=raw["id"],
            name=raw["name"],
            entity_type=raw["entity_type"],
            properties=raw.get("properties", {}),
            confidence=raw.get("confidence", 1.0),
            source_layer=raw.get("source_layer"),
            created_at=raw.get("created_at", ""),
            updated_at=raw.get("updated_at", ""),
        )

    @staticmethod
    def _to_kg_edge(raw: Dict[str, Any]) -> KGEdge:
        """Convert a raw store edge dict to a KGEdge dataclass."""
        return KGEdge(
            id=raw["id"],
            source_id=raw["source_id"],
            target_id=raw["target_id"],
            relation_type=raw["relation_type"],
            weight=raw.get("weight", 1.0),
            confidence=raw.get("confidence", 1.0),
            evidence=raw.get("evidence", []),
            source_layer=raw.get("source_layer"),
            created_at=raw.get("created_at", ""),
        )
