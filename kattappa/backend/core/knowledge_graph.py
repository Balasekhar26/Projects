"""Step 29: Unified Knowledge Graph for Kattappa.

Provides structured knowledge representation with typed entities,
weighted relationships, cross-layer entity reconciliation, and
graph-based query capabilities.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from backend.core.graph_store import GraphStore
from backend.core.graph_query import GraphQueryEngine
from backend.core.kg_sync import SyncManager

logger = logging.getLogger(__name__)


def load_config() -> Any:
    """Helper to support legacy configuration monkeypatching."""
    from backend.core.config import load_config as _load_config
    return _load_config()



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
    AGENT = "AGENT"
    ARTIFACT = "ARTIFACT"
    CONSTRAINT = "CONSTRAINT"

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
    EXECUTED_BY = "EXECUTED_BY"
    REQUIRES_TOOL = "REQUIRES_TOOL"
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
    belief_state: str = "BELIEVED"
    evidence: List[str] = field(default_factory=list)
    last_verified_at: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
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
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    created_at: str = ""


# ---------------------------------------------------------------------------
# KnowledgeGraph
# ---------------------------------------------------------------------------

class hybridmethod:
    """Descriptor to support hybrid class-level and instance-level methods."""
    def __init__(self, func):
        self.func = func

    def __get__(self, instance, owner):
        if instance is None:
            def class_wrapper(*args, **kwargs):
                return self.func(owner, *args, **kwargs)
            return class_wrapper
        else:
            def instance_wrapper(*args, **kwargs):
                return self.func(instance, *args, **kwargs)
            return instance_wrapper


class KnowledgeGraph:
    """Unified Knowledge Graph combining structured storage, graph queries,
    and cross-layer synchronization.

    Parameters
    ----------
    data_dir:
        Directory where the ``knowledge_graph.db`` SQLite file is stored.
    """
    _instance = None
    _lock = threading.RLock()
    _schema_ensured = False

    @classmethod
    def get_instance(cls) -> "KnowledgeGraph":
        with cls._lock:
            if cls._instance is None:
                from backend.core.config import load_config as _load_config
                config = _load_config()
                data_dir = str(config.sqlite_path.parent / "knowledge_graph")
                cls._instance = cls(data_dir)
            return cls._instance

    def __init__(self, data_dir: str) -> None:
        import os
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "knowledge_graph.db")
        self._store = GraphStore(db_path)
        self._query = GraphQueryEngine(self._store)
        self._sync_manager = SyncManager(self._store)
        from backend.core.cos.pkg import ProbabilisticKnowledgeGraph
        self._pkg = ProbabilisticKnowledgeGraph(graph_store=self._store)

    # ------------------------------------------------------------------ #
    #  CRUD                                                               #
    # ------------------------------------------------------------------ #

    @hybridmethod
    def add_node(
        self_or_cls,
        name: str = "",
        entity_type: str | EntityType = "",
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
        source_layer: Optional[str] = None,
        belief_state: str = "BELIEVED",
        evidence: Optional[List[str]] = None,
        last_verified_at: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
        node_id: Optional[str] = None,
        *args,
        **kwargs,
    ) -> Any:
        """Add a new node to the knowledge graph."""
        name_val = name
        etype_val = entity_type
        props_val = properties

        if not name_val and node_id:
            name_val = node_id
        if not name_val and "node_id" in kwargs:
            name_val = kwargs["node_id"]
        if not etype_val and "node_type" in kwargs:
            etype_val = kwargs["node_type"]
        if not props_val and "properties" in kwargs:
            props_val = kwargs["properties"]

        if isinstance(self_or_cls, type):
            inst = self_or_cls.get_instance()
            return inst.add_node(
                name=name_val,
                entity_type=etype_val,
                properties=props_val,
                node_id=name_val,
            )

        self = self_or_cls
        etype = EntityType.coerce(etype_val).value if isinstance(etype_val, str) else etype_val.value
        target_nid = name_val if node_id is None else node_id
        
        # Idempotency check
        existing = self.get_node(target_nid)
        if existing:
            updates = {}
            if props_val is not None:
                updates["properties"] = props_val
            if confidence is not None:
                updates["confidence"] = confidence
            if belief_state is not None:
                updates["belief_state"] = belief_state
            if evidence is not None:
                updates["evidence"] = evidence
            if last_verified_at is not None:
                updates["last_verified_at"] = last_verified_at
            if valid_from is not None:
                updates["valid_from"] = valid_from
            if valid_until is not None:
                updates["valid_until"] = valid_until
            if source_layer is not None:
                updates["source_layer"] = source_layer
            
            if updates:
                self.update_node(target_nid, **updates)
            
            raw = self._store.get_node(target_nid)
            if raw:
                return self._to_kg_node(raw)
            return KGNode(id=existing["id"], name=name_val, entity_type=etype, properties=existing.get("properties", {}))

        nid = self._store.insert_node(
            name=name_val,
            entity_type=etype,
            properties=props_val,
            confidence=confidence,
            source_layer=source_layer,
            belief_state=belief_state,
            evidence=evidence,
            last_verified_at=last_verified_at,
            valid_from=valid_from,
            valid_until=valid_until,
            node_id=target_nid,
        )
        raw = self._store.get_node(nid)
        return self._to_kg_node(raw) if raw else KGNode(id=nid, name=name_val, entity_type=etype)

    @hybridmethod
    def get_node(self_or_cls, node_id: str) -> Any:
        """Retrieve a node by node_id."""
        if isinstance(self_or_cls, type):
            inst = self_or_cls.get_instance()
            return inst.get_node(node_id)

        self = self_or_cls
        raw = self._store.get_node(node_id)
        if not raw:
            return None
        return {
            "id": raw.get("id"),
            "type": raw.get("entity_type").lower() if raw.get("entity_type") else None,
            "properties": json.loads(raw.get("properties") or "{}") if isinstance(raw.get("properties"), str) else (raw.get("properties") or {}),
            "confidence": raw.get("confidence", 1.0),
            "belief_state": raw.get("belief_state", "BELIEVED"),
            "evidence": json.loads(raw.get("evidence") or "[]") if isinstance(raw.get("evidence"), str) else (raw.get("evidence") or []),
            "source_layer": raw.get("source_layer"),
            "name": raw.get("name")
        }



    @hybridmethod
    def add_edge(
        self_or_cls,
        source_name: str = "",
        target_name: str = "",
        relation_type: str | RelationType = "",
        weight: float = 1.0,
        confidence: float = 1.0,
        evidence: Optional[List[str]] = None,
        source_layer: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        *args,
        **kwargs,
    ) -> Any:
        """Add a directed edge between two entities."""
        src_name = source_name or source_id
        tgt_name = target_name or target_id
        rel_type = relation_type

        if "source_id" in kwargs:
            src_name = kwargs["source_id"]
        if "target_id" in kwargs:
            tgt_name = kwargs["target_id"]
        if "relation_type" in kwargs:
            rel_type = kwargs["relation_type"]

        if isinstance(self_or_cls, type):
            inst = self_or_cls.get_instance()
            return inst.add_edge(
                source_name=src_name,
                target_name=tgt_name,
                relation_type=rel_type,
                properties=properties,
            )

        self = self_or_cls
        rel = RelationType.coerce(rel_type).value if isinstance(rel_type, str) else rel_type.value
        src = self._resolve_name(src_name)
        tgt = self._resolve_name(tgt_name)
        if not src:
            self.add_node(name=src_name, entity_type=EntityType.CONCEPT, node_id=src_name)
            src = self._resolve_name(src_name)
        if not tgt:
            self.add_node(name=tgt_name, entity_type=EntityType.CONCEPT, node_id=tgt_name)
            tgt = self._resolve_name(tgt_name)

        eid = self._store.insert_edge(
            source_id=src["id"],
            target_id=tgt["id"],
            relation_type=rel,
            weight=weight,
            confidence=confidence,
            evidence=evidence,
            source_layer=source_layer,
            valid_from=valid_from,
            valid_until=valid_until,
        )
        edges = self._store.get_edges_from(src["id"], relation_type=rel)
        for e in edges:
            if e["id"] == eid:
                return self._to_kg_edge(e)
        return KGEdge(id=eid, source_id=src["id"], target_id=tgt["id"], relation_type=rel)

    @hybridmethod
    def query_neighbors(
        self_or_cls,
        node_id: str,
        direction: str = "both",
        relation_type: Optional[str] = None,
        *args,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Query neighbor nodes and return legacy relation formats."""
        rel_type = relation_type or kwargs.get("relation_type")

        if isinstance(self_or_cls, type):
            inst = self_or_cls.get_instance()
            return inst.query_neighbors(node_id, direction=direction, relation_type=rel_type)

        self = self_or_cls
        edges = []
        if direction in {"out", "both"}:
            edges.extend(self._store.get_edges_from(node_id))
        if direction in {"in", "both"}:
            edges.extend(self._store.get_edges_to(node_id))

        results = []
        for e in edges:
            if rel_type and e["relation_type"] != rel_type:
                continue

            other_id = e["target_id"] if e["source_id"] == node_id else e["source_id"]
            other_node = self._store.get_node(other_id)
            node_type_val = other_node.get("entity_type").lower() if (other_node and other_node.get("entity_type")) else None

            results.append({
                "node_id": other_id,
                "type": node_type_val,
                "relation": e["relation_type"],
                "relation_type": e["relation_type"],
            })
        return results

    @hybridmethod
    def find_shortest_path(
        self_or_cls,
        source_id: str = "",
        target_id: str = "",
        *args,
        **kwargs,
    ) -> Optional[List[str]]:
        """Find the shortest node ID path between source and target."""
        src_id = source_id
        tgt_id = target_id
        if args:
            if len(args) >= 1:
                src_id = args[0]
            if len(args) >= 2:
                tgt_id = args[1]

        if not src_id:
            src_id = kwargs.get("source") or kwargs.get("start_name") or ""
        if not tgt_id:
            tgt_id = kwargs.get("target") or kwargs.get("end_name") or ""

        if isinstance(self_or_cls, type):
            inst = self_or_cls.get_instance()
            return inst.find_shortest_path(source_id=src_id, target_id=tgt_id)

        self = self_or_cls
        queue = [[src_id]]
        visited = {src_id}
        while queue:
            path = queue.pop(0)
            node = path[-1]
            if node == tgt_id:
                return path
            neighbors = self.query_neighbors(node, direction="out")
            for n in neighbors:
                nid = n["node_id"]
                if nid not in visited:
                    visited.add(nid)
                    new_path = list(path)
                    new_path.append(nid)
                    queue.append(new_path)
        return None

    @hybridmethod
    def find_top_k_paths(
        self_or_cls,
        source_id: str,
        target_id: str,
        k: int = 5,
        max_depth: int = 6,
        *args,
        **kwargs
    ) -> List[Any]:
        """Finds top-k highest probability paths using Best-First Search (Dijkstra-style)."""
        if isinstance(self_or_cls, type):
            inst = self_or_cls.get_instance()
            return inst.find_top_k_paths(source_id, target_id, k=k, max_depth=max_depth)
        self = self_or_cls
        return self._pkg.find_top_k_paths(source_id, target_id, k=k, max_depth=max_depth)

    @hybridmethod
    def query_probabilistic(
        self_or_cls,
        source_id: str,
        target_id: str,
        max_depth: int = 6,
        *args,
        **kwargs
    ) -> Any:
        """Queries the PKG using exact joint probability calculations."""
        if isinstance(self_or_cls, type):
            inst = self_or_cls.get_instance()
            return inst.query_probabilistic(source_id, target_id, max_depth=max_depth)
        self = self_or_cls
        return self._pkg.query(source_id, target_id, max_depth=max_depth)


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

    @hybridmethod
    def get_subgraph(
        self_or_cls,
        center_name_or_ids: str | List[str] = "",
        radius_or_depth: int = 2,
        *args,
        **kwargs,
    ) -> Dict[str, Any]:
        """Extract a subgraph around node(s) with fallback parameter support."""
        node_ids = center_name_or_ids
        depth_val = radius_or_depth

        if args:
            if len(args) >= 1:
                depth_val = args[0]

        if "node_ids" in kwargs:
            node_ids = kwargs["node_ids"]
        if "depth" in kwargs:
            depth_val = kwargs["depth"]
        if "radius" in kwargs:
            depth_val = kwargs["radius"]

        if isinstance(node_ids, str):
            node_ids = [node_ids]

        if isinstance(self_or_cls, type):
            inst = self_or_cls.get_instance()
            visited_nodes = set(node_ids)
            edges = []
            current_layer = list(node_ids)
            for _ in range(depth_val):
                next_layer = []
                for nid in current_layer:
                    adj = inst._store.get_edges_from(nid) + inst._store.get_edges_to(nid)
                    for e in adj:
                        edge_key = (e["source_id"], e["target_id"], e["relation_type"])
                        if edge_key not in [(x["source_id"], x["target_id"], x["relation_type"]) for x in edges]:
                            edges.append({
                                "source_id": e.get("source_id"),
                                "target_id": e.get("target_id"),
                                "relation_type": e.get("relation_type"),
                                "properties": json.loads(e.get("properties") or "{}") if isinstance(e.get("properties"), str) else (e.get("properties") or {}),
                            })
                        neighbor = e["target_id"] if e["source_id"] == nid else e["source_id"]
                        if neighbor not in visited_nodes:
                            visited_nodes.add(neighbor)
                            next_layer.append(neighbor)
                current_layer = next_layer

            nodes = []
            for nid in visited_nodes:
                n = inst._store.get_node(nid)
                if n:
                    nodes.append({
                        "id": n.get("id"),
                        "type": n.get("entity_type").lower() if n.get("entity_type") else None,
                        "properties": json.loads(n.get("properties") or "{}") if isinstance(n.get("properties"), str) else (n.get("properties") or {}),
                    })
            return {"nodes": nodes, "edges": edges}

        self = self_or_cls
        center_name = node_ids[0] if node_ids else ""
        node = self._resolve_name(center_name)
        if not node:
            return {"nodes": [], "edges": []}
        raw = self._query.get_subgraph(node["id"], radius=depth_val)
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

    def decay_unrefreshed_nodes(self, decay_rate: float, now: Optional[float] = None) -> int:
        """Decay confidence of unrefreshed facts over time.
        
        Formula: C_new = C_old * e^(-lambda * dt)
        """
        import math
        current_time = now or datetime.now(timezone.utc).timestamp()
        
        decayed_count = 0
        with self._store._lock:
            conn = self._store._get_conn()
            try:
                rows = conn.execute(
                    "SELECT id, confidence, belief_state, updated_at FROM kg_nodes WHERE belief_state != 'REFUTED' AND entity_type != 'GOAL'"
                ).fetchall()
                
                for row in rows:
                    node_id = row["id"]
                    old_conf = row["confidence"]
                    updated_at_str = row["updated_at"]
                    
                    try:
                        clean_iso = updated_at_str.replace("Z", "+00:00")
                        updated_ts = datetime.fromisoformat(clean_iso).timestamp()
                    except Exception:
                        updated_ts = current_time
                    
                    dt = current_time - updated_ts
                    if dt <= 0:
                        continue
                    
                    new_conf = old_conf * math.exp(-decay_rate * dt)
                    new_conf = max(0.0, min(1.0, new_conf))
                    
                    if abs(old_conf - new_conf) >= 0.01:
                        belief = row["belief_state"]
                        if new_conf < 0.20 and belief == "BELIEVED":
                            belief = "HYPOTHETICAL"
                        
                        conn.execute(
                            "UPDATE kg_nodes SET confidence = ?, belief_state = ?, updated_at = ? WHERE id = ?",
                            (new_conf, belief, datetime.fromtimestamp(current_time, timezone.utc).isoformat(), node_id)
                        )
                        decayed_count += 1
                        
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error("decay_unrefreshed_nodes failed: %s", e)
            finally:
                conn.close()
        return decayed_count

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
        """Resolve *name* to a raw node dict (ID -> alias -> name match)."""
        node_by_id = self._store.get_node(name)
        if node_by_id:
            return node_by_id
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
            belief_state=raw.get("belief_state", "BELIEVED"),
            evidence=raw.get("evidence", []),
            last_verified_at=raw.get("last_verified_at"),
            valid_from=raw.get("valid_from"),
            valid_until=raw.get("valid_until"),
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
            valid_from=raw.get("valid_from"),
            valid_until=raw.get("valid_until"),
            created_at=raw.get("created_at", ""),
        )
