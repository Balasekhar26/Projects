"""
GraphStore — thread-safe JSONL persistence for the Knowledge Graph
===================================================================

Storage layout:
  <store_dir>/
      nodes.jsonl   — one Node JSON per line
      edges.jsonl   — one Edge JSON per line

Both files are append-only for new records.
Updates trigger a full rewrite of the affected file (same pattern as PlannerStore).

The in-memory index is:
  _nodes: Dict[node_id → Node]
  _edges: Dict[edge_id → Edge]
  _by_canonical: Dict[(canonical_name, entity_type) → node_id]  ← dedup key

Deduplication
-------------
On add_node(), if a node with the same (canonical_name, entity_type) already
exists, the existing node's mention_count is incremented and the description
is updated if richer. No duplicate node is created.

On add_edge(), if an edge with the same (source_id, target_id, relationship)
already exists, the weight is updated to max(existing, new) and evidence
is appended. No duplicate edge is created.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List, Optional, Set, Tuple

from kattappa_runtime.knowledge_graph.schema import (
    Node, Edge, EntityType, RelationshipType, GraphStats
)

_NODES_FILE = "kg_nodes.jsonl"
_EDGES_FILE = "kg_edges.jsonl"


class GraphStore:
    """
    Thread-safe JSONL persistence for the Knowledge Graph.

    Parameters
    ----------
    store_dir : str
        Directory where nodes.jsonl and edges.jsonl are stored.
        Created if it does not exist.
    """

    def __init__(self, store_dir: str):
        self._dir  = store_dir
        self._lock = Lock()
        os.makedirs(store_dir, exist_ok=True)

        self._nodes:        Dict[str, Node] = {}   # node_id → Node
        self._edges:        Dict[str, Edge] = {}   # edge_id → Edge
        self._by_canonical: Dict[Tuple[str, str], str] = {}  # (name, type) → node_id

        # Adjacency indices for fast traversal
        self._out_edges: Dict[str, Set[str]] = {}  # node_id → set of edge_ids (outgoing)
        self._in_edges:  Dict[str, Set[str]] = {}  # node_id → set of edge_ids (incoming)

        self._load()

    # ------------------------------------------------------------------
    # Write — Nodes
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> Node:
        """
        Add a node. If a node with the same canonical form already exists,
        increment its mention_count and return the existing node.

        Returns the node that is now in the graph (existing or new).
        """
        with self._lock:
            key = (node.canonical_name, node.entity_type.value)
            if key in self._by_canonical:
                existing = self._nodes[self._by_canonical[key]]
                existing.mention_count += 1
                if node.description and len(node.description) > len(existing.description):
                    existing.description = node.description
                existing.updated_at = datetime.now(timezone.utc).isoformat()
                # Merge properties
                existing.properties.update(node.properties)
                self._rewrite_nodes()
                return existing

            self._nodes[node.node_id] = node
            self._by_canonical[key]   = node.node_id
            self._out_edges[node.node_id] = set()
            self._in_edges[node.node_id]  = set()
            self._append_node(node)
            return node

    def update_node(self, node_id: str, **kwargs) -> Optional[Node]:
        """Update arbitrary fields on an existing node."""
        with self._lock:
            node = self._nodes.get(node_id)
            if not node:
                return None
            for k, v in kwargs.items():
                if hasattr(node, k):
                    setattr(node, k, v)
            node.updated_at = datetime.now(timezone.utc).isoformat()
            self._rewrite_nodes()
            return node

    # ------------------------------------------------------------------
    # Write — Edges
    # ------------------------------------------------------------------

    def add_edge(self, edge: Edge) -> Edge:
        """
        Add an edge. If a duplicate (source, target, relationship) already
        exists, update its weight to max(existing, new) and return existing.
        """
        with self._lock:
            # Find existing edge with same triple
            dup = self._find_edge(edge.source_id, edge.target_id, edge.relationship)
            if dup:
                dup.weight = max(dup.weight, edge.weight)
                if edge.evidence:
                    dup.evidence = (dup.evidence + "; " + edge.evidence).strip("; ")
                self._rewrite_edges()
                return dup

            self._edges[edge.edge_id] = edge
            self._out_edges.setdefault(edge.source_id, set()).add(edge.edge_id)
            self._in_edges.setdefault(edge.target_id,  set()).add(edge.edge_id)
            self._append_edge(edge)
            return edge

    def remove_edge(self, edge_id: str) -> bool:
        with self._lock:
            edge = self._edges.pop(edge_id, None)
            if not edge:
                return False
            self._out_edges.get(edge.source_id, set()).discard(edge_id)
            self._in_edges.get(edge.target_id,  set()).discard(edge_id)
            self._rewrite_edges()
            return True

    # ------------------------------------------------------------------
    # Read — Nodes
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> Optional[Node]:
        with self._lock:
            return self._nodes.get(node_id)

    def find_by_name(self, name: str,
                     entity_type: Optional[EntityType] = None) -> Optional[Node]:
        canonical = name.lower().strip()
        with self._lock:
            if entity_type:
                key = (canonical, entity_type.value)
                nid = self._by_canonical.get(key)
                return self._nodes.get(nid) if nid else None
            # Search all types
            for (cname, _), nid in self._by_canonical.items():
                if cname == canonical:
                    return self._nodes[nid]
        return None

    def all_nodes(self) -> List[Node]:
        with self._lock:
            return list(self._nodes.values())

    def nodes_by_type(self, entity_type: EntityType) -> List[Node]:
        with self._lock:
            return [n for n in self._nodes.values()
                    if n.entity_type == entity_type]

    def node_count(self) -> int:
        with self._lock:
            return len(self._nodes)

    # ------------------------------------------------------------------
    # Read — Edges
    # ------------------------------------------------------------------

    def get_edges_from(self, node_id: str,
                       relationship: Optional[RelationshipType] = None) -> List[Edge]:
        """Return all outgoing edges from a node, optionally filtered by type."""
        with self._lock:
            edge_ids = self._out_edges.get(node_id, set())
            edges    = [self._edges[eid] for eid in edge_ids if eid in self._edges]
            if relationship:
                edges = [e for e in edges if e.relationship == relationship]
            return sorted(edges, key=lambda e: -e.weight)

    def get_edges_to(self, node_id: str,
                     relationship: Optional[RelationshipType] = None) -> List[Edge]:
        """Return all incoming edges to a node, optionally filtered by type."""
        with self._lock:
            edge_ids = self._in_edges.get(node_id, set())
            edges    = [self._edges[eid] for eid in edge_ids if eid in self._edges]
            if relationship:
                edges = [e for e in edges if e.relationship == relationship]
            return sorted(edges, key=lambda e: -e.weight)

    def all_edges(self) -> List[Edge]:
        with self._lock:
            return list(self._edges.values())

    def edge_count(self) -> int:
        with self._lock:
            return len(self._edges)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> GraphStats:
        with self._lock:
            entity_counts: Dict[str, int] = {}
            for n in self._nodes.values():
                entity_counts[n.entity_type.value] = \
                    entity_counts.get(n.entity_type.value, 0) + 1

            rel_counts: Dict[str, int] = {}
            for e in self._edges.values():
                rel_counts[e.relationship.value] = \
                    rel_counts.get(e.relationship.value, 0) + 1

            top_nodes = sorted(
                self._nodes.values(),
                key=lambda n: -n.mention_count
            )[:10]

            return GraphStats(
                node_count    = len(self._nodes),
                edge_count    = len(self._edges),
                entity_counts = entity_counts,
                rel_counts    = rel_counts,
                top_nodes     = [n.name for n in top_nodes],
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_edge(
        self, source_id: str, target_id: str, relationship: RelationshipType
    ) -> Optional[Edge]:
        """Find an existing edge by (source, target, rel) without locking."""
        for eid in self._out_edges.get(source_id, set()):
            edge = self._edges.get(eid)
            if (edge and edge.target_id == target_id
                    and edge.relationship == relationship):
                return edge
        return None

    def _append_node(self, node: Node) -> None:
        path = os.path.join(self._dir, _NODES_FILE)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(node.to_dict(), ensure_ascii=False) + "\n")

    def _append_edge(self, edge: Edge) -> None:
        path = os.path.join(self._dir, _EDGES_FILE)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(edge.to_dict(), ensure_ascii=False) + "\n")

    def _rewrite_nodes(self) -> None:
        path = os.path.join(self._dir, _NODES_FILE)
        with open(path, "w", encoding="utf-8") as f:
            for n in self._nodes.values():
                f.write(json.dumps(n.to_dict(), ensure_ascii=False) + "\n")

    def _rewrite_edges(self) -> None:
        path = os.path.join(self._dir, _EDGES_FILE)
        with open(path, "w", encoding="utf-8") as f:
            for e in self._edges.values():
                f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")

    def _load(self) -> None:
        """Load both files from disk on startup."""
        self._load_nodes()
        self._load_edges()

    def _load_nodes(self) -> None:
        path = os.path.join(self._dir, _NODES_FILE)
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    node = Node.from_dict(json.loads(line))
                    self._nodes[node.node_id] = node
                    key = (node.canonical_name, node.entity_type.value)
                    self._by_canonical[key] = node.node_id
                    self._out_edges.setdefault(node.node_id, set())
                    self._in_edges.setdefault(node.node_id,  set())
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

    def _load_edges(self) -> None:
        path = os.path.join(self._dir, _EDGES_FILE)
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    edge = Edge.from_dict(json.loads(line))
                    self._edges[edge.edge_id] = edge
                    self._out_edges.setdefault(edge.source_id, set()).add(edge.edge_id)
                    self._in_edges.setdefault(edge.target_id,  set()).add(edge.edge_id)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
