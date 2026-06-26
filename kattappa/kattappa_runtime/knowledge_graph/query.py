"""
GraphQuery — traversal and query algorithms for the Knowledge Graph
====================================================================

All queries operate on a live GraphStore and return ranked results.

Query methods (user-specified API)
-----------------------------------
find_related(name, relation_type=None, max_depth=2)
    → nodes reachable from `name` within `max_depth` hops

find_dependencies(name)
    → nodes that `name` DEPENDS_ON (direct + transitive)

find_prerequisites(name)
    → nodes with PREREQUISITE_OF or DEPENDS_ON pointing toward `name`

find_tools_for_skill(skill_name)
    → Tool nodes connected to a Skill via USES or APPLIES_TO

find_knowledge_gaps(topic_name)
    → prerequisites of `topic_name` that Kattappa hasn't learned yet
       (nodes with no LEARNED_FROM edge from any PERSON node)

Additional graph algorithms
---------------------------
traverse(start_id, max_depth, min_weight, relation_filter)
    BFS from start node with optional filters.

find_path(source_name, target_name)
    Shortest path between two named entities.

get_subgraph(center_name, radius)
    All nodes within `radius` hops of center, both directions.

get_hubs(n, entity_type)
    Top-N highest mention_count nodes, optionally filtered by type.

search_nodes(query_text, entity_type)
    Simple substring search over node names and descriptions.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from kattappa_runtime.knowledge_graph.schema import (
    Node, Edge, EntityType, RelationshipType
)
from kattappa_runtime.knowledge_graph.store import GraphStore


@dataclass
class TraversalResult:
    """One node found during graph traversal."""
    node:      Node
    depth:     int
    path:      List[str]   # List of node_ids from start to this node
    via_edge:  Optional[Edge] = None  # Edge that brought us here

    @property
    def path_str(self) -> str:
        return " → ".join(self.path)


@dataclass
class PathResult:
    """Result of a find_path query."""
    found:       bool
    source_name: str
    target_name: str
    nodes:       List[Node]  = field(default_factory=list)
    edges:       List[Edge]  = field(default_factory=list)
    length:      int         = 0

    def path_str(self) -> str:
        if not self.found:
            return f"No path: {self.source_name} → {self.target_name}"
        names = [n.name for n in self.nodes]
        return " → ".join(names)


class GraphQuery:
    """
    Query engine that operates on a GraphStore.

    Parameters
    ----------
    store : GraphStore
        The underlying node/edge storage.
    """

    def __init__(self, store: GraphStore):
        self._store = store

    # ------------------------------------------------------------------
    # User-facing Query API
    # ------------------------------------------------------------------

    def find_related(
        self,
        name:          str,
        entity_type:   Optional[EntityType]       = None,
        relation_type: Optional[RelationshipType] = None,
        max_depth:     int                        = 2,
        min_weight:    float                      = 0.0,
    ) -> List[TraversalResult]:
        """
        Find all nodes related to `name` within `max_depth` hops.

        Parameters
        ----------
        name : str
            Entity name to start from.
        entity_type : EntityType | None
            If provided, only match entities of this type as the start node.
        relation_type : RelationshipType | None
            If provided, only follow edges of this type.
        max_depth : int
            Maximum traversal depth.
        min_weight : float
            Minimum edge weight to follow [0.0, 1.0].

        Returns
        -------
        List[TraversalResult]
            Sorted by depth then descending edge weight.
        """
        start = self._store.find_by_name(name, entity_type)
        if not start:
            return []
        return self.traverse(
            start_id      = start.node_id,
            max_depth     = max_depth,
            min_weight    = min_weight,
            relation_filter = relation_type,
        )

    def find_dependencies(
        self,
        name:       str,
        max_depth:  int = 3,
    ) -> List[TraversalResult]:
        """
        Find what `name` depends on (direct + transitive).
        Follows DEPENDS_ON and PREREQUISITE_OF edges outward.
        """
        start = self._store.find_by_name(name)
        if not start:
            return []
        dep_types = {RelationshipType.DEPENDS_ON, RelationshipType.PREREQUISITE_OF}
        return self._bfs_filtered(
            start_id     = start.node_id,
            max_depth    = max_depth,
            edge_types   = dep_types,
            direction    = "outgoing",
        )

    def find_prerequisites(
        self,
        name:      str,
        max_depth: int = 3,
    ) -> List[TraversalResult]:
        """
        Find nodes that must be mastered before `name`.
        Traverses PREREQUISITE_OF edges INCOMING to `name`.
        Also includes anything that `name` DEPENDS_ON.
        """
        start = self._store.find_by_name(name)
        if not start:
            return []

        # Both: what depends on this (incoming PREREQUISITE_OF)
        # and what this depends on (outgoing DEPENDS_ON)
        prereq_incoming = self._bfs_filtered(
            start_id   = start.node_id,
            max_depth  = max_depth,
            edge_types = {RelationshipType.PREREQUISITE_OF},
            direction  = "incoming",
        )
        prereq_outgoing = self._bfs_filtered(
            start_id   = start.node_id,
            max_depth  = max_depth,
            edge_types = {RelationshipType.DEPENDS_ON, RelationshipType.PREREQUISITE_OF},
            direction  = "outgoing",
        )

        # Merge, dedup by node_id
        seen: Set[str] = set()
        results: List[TraversalResult] = []
        for r in prereq_outgoing + prereq_incoming:
            if r.node.node_id not in seen:
                seen.add(r.node.node_id)
                results.append(r)
        return results

    def find_tools_for_skill(self, skill_name: str) -> List[Node]:
        """
        Find Tool nodes associated with a Skill.
        Looks for TOOL entities connected via USES or APPLIES_TO.
        """
        start = self._store.find_by_name(skill_name)
        if not start:
            return []

        # Outgoing: skill USES tool  /  skill APPLIES_TO tool
        outgoing_use = self._store.get_edges_from(
            start.node_id, RelationshipType.USES
        )
        outgoing_app = self._store.get_edges_from(
            start.node_id, RelationshipType.APPLIES_TO
        )

        # Incoming: tool USES skill  (less common, but supported)
        incoming_use = self._store.get_edges_to(
            start.node_id, RelationshipType.USES
        )

        tool_ids: Set[str] = set()
        for edge in outgoing_use + outgoing_app:
            tool_ids.add(edge.target_id)
        for edge in incoming_use:
            tool_ids.add(edge.source_id)

        tools: List[Node] = []
        for nid in tool_ids:
            node = self._store.get_node(nid)
            if node and node.entity_type == EntityType.TOOL:
                tools.append(node)

        return sorted(tools, key=lambda n: -n.mention_count)

    def find_knowledge_gaps(
        self,
        topic_name: str,
        learner_name: str = "kattappa",
    ) -> List[Node]:
        """
        Find prerequisites of `topic_name` that haven't been learned yet.

        "Learned" means there is a LEARNED_FROM edge from the learner to that node,
        or the learner has worked on / studied that topic (WORKED_ON, STUDIED_BY).

        Parameters
        ----------
        topic_name : str
            The goal concept to analyse.
        learner_name : str
            The learner entity name (default: "kattappa").

        Returns
        -------
        List[Node]
            Prerequisite nodes with no evidence of learning.
        """
        # Get all prerequisites for this topic
        prereqs = self.find_prerequisites(topic_name)
        if not prereqs:
            return []

        # Get what the learner already knows
        learner = self._store.find_by_name(learner_name)
        learned_ids: Set[str] = set()
        if learner:
            # Outgoing learned_from edges
            for edge in self._store.get_edges_from(learner.node_id,
                                                    RelationshipType.LEARNED_FROM):
                learned_ids.add(edge.target_id)
            for edge in self._store.get_edges_from(learner.node_id,
                                                    RelationshipType.WORKED_ON):
                learned_ids.add(edge.target_id)
            # Incoming: things that were "learned_from" this person (mark as known)
            for edge in self._store.get_edges_to(learner.node_id,
                                                   RelationshipType.LEARNED_FROM):
                learned_ids.add(edge.source_id)

        # Gaps = prerequisites not in learned set
        gaps: List[Node] = []
        for r in prereqs:
            if r.node.node_id not in learned_ids:
                gaps.append(r.node)

        return gaps

    # ------------------------------------------------------------------
    # Graph Traversal
    # ------------------------------------------------------------------

    def traverse(
        self,
        start_id:       str,
        max_depth:      int                        = 2,
        min_weight:     float                      = 0.0,
        relation_filter: Optional[RelationshipType] = None,
        direction:      str                        = "outgoing",  # "outgoing" | "incoming" | "both"
    ) -> List[TraversalResult]:
        """
        BFS traversal from start_id.

        Returns all reachable nodes (excluding the start node itself)
        sorted by depth then descending weight.
        """
        results:  List[TraversalResult] = []
        visited:  Set[str] = {start_id}
        queue:    deque = deque()

        # Queue entry: (node_id, depth, path_so_far, via_edge)
        queue.append((start_id, 0, [start_id], None))

        while queue:
            current_id, depth, path, via = queue.popleft()

            if depth > 0:
                node = self._store.get_node(current_id)
                if node:
                    results.append(TraversalResult(
                        node=node, depth=depth, path=path, via_edge=via
                    ))

            if depth >= max_depth:
                continue

            # Expand neighbours
            edges: List[Edge] = []
            if direction in ("outgoing", "both"):
                edges += self._store.get_edges_from(
                    current_id,
                    relation_filter if relation_filter else None
                )
            if direction in ("incoming", "both"):
                edges += self._store.get_edges_to(
                    current_id,
                    relation_filter if relation_filter else None
                )

            for edge in edges:
                if edge.weight < min_weight:
                    continue
                neighbour_id = (edge.target_id
                                if direction in ("outgoing", "both") and edge.source_id == current_id
                                else edge.source_id)
                if direction == "incoming":
                    neighbour_id = edge.source_id
                if neighbour_id not in visited:
                    visited.add(neighbour_id)
                    queue.append((neighbour_id, depth + 1,
                                  path + [neighbour_id], edge))

        # Sort: primary depth ascending, secondary weight descending
        results.sort(key=lambda r: (r.depth,
                                     -(r.via_edge.weight if r.via_edge else 0)))
        return results

    def find_path(
        self,
        source_name: str,
        target_name: str,
        max_depth:   int = 5,
    ) -> PathResult:
        """
        Find the shortest path between two named entities using BFS.
        Traverses outgoing + incoming edges (undirected path search).
        """
        source = self._store.find_by_name(source_name)
        target = self._store.find_by_name(target_name)

        if not source or not target:
            return PathResult(found=False,
                              source_name=source_name,
                              target_name=target_name)

        if source.node_id == target.node_id:
            return PathResult(found=True, source_name=source_name,
                              target_name=target_name,
                              nodes=[source], edges=[], length=0)

        # BFS: (node_id, path_node_ids, path_edges)
        visited = {source.node_id}
        queue: deque = deque([(source.node_id, [source.node_id], [])])

        while queue:
            current_id, node_path, edge_path = queue.popleft()

            if len(node_path) > max_depth + 1:
                continue

            all_edges = (
                self._store.get_edges_from(current_id) +
                self._store.get_edges_to(current_id)
            )

            for edge in all_edges:
                neighbour_id = (edge.target_id
                                if edge.source_id == current_id
                                else edge.source_id)

                if neighbour_id in visited:
                    continue
                visited.add(neighbour_id)

                new_node_path = node_path + [neighbour_id]
                new_edge_path = edge_path + [edge]

                if neighbour_id == target.node_id:
                    nodes = [self._store.get_node(nid) for nid in new_node_path]
                    nodes = [n for n in nodes if n]
                    return PathResult(
                        found=True,
                        source_name=source_name,
                        target_name=target_name,
                        nodes=nodes,
                        edges=new_edge_path,
                        length=len(new_edge_path),
                    )

                queue.append((neighbour_id, new_node_path, new_edge_path))

        return PathResult(found=False, source_name=source_name,
                          target_name=target_name)

    def get_subgraph(
        self,
        center_name: str,
        radius:      int = 2,
    ) -> Tuple[List[Node], List[Edge]]:
        """
        Return all nodes and edges within `radius` hops of `center_name`
        in both directions.
        """
        center = self._store.find_by_name(center_name)
        if not center:
            return [], []

        results = self.traverse(
            start_id  = center.node_id,
            max_depth = radius,
            direction = "both",
        )
        node_ids = {center.node_id} | {r.node.node_id for r in results}
        nodes = [self._store.get_node(nid) for nid in node_ids]
        nodes = [n for n in nodes if n]

        # Only edges where both endpoints are in subgraph
        all_edges = self._store.all_edges()
        edges = [e for e in all_edges
                 if e.source_id in node_ids and e.target_id in node_ids]

        return nodes, edges

    def get_hubs(
        self,
        n:           int                       = 10,
        entity_type: Optional[EntityType]      = None,
    ) -> List[Node]:
        """Return top-N nodes by mention_count (graph hubs)."""
        nodes = (self._store.nodes_by_type(entity_type)
                 if entity_type else self._store.all_nodes())
        return sorted(nodes, key=lambda n: -n.mention_count)[:n]

    def search_nodes(
        self,
        query_text:  str,
        entity_type: Optional[EntityType] = None,
    ) -> List[Node]:
        """
        Case-insensitive substring search over node names and descriptions.
        """
        q = query_text.lower()
        nodes = (self._store.nodes_by_type(entity_type)
                 if entity_type else self._store.all_nodes())
        results = [
            n for n in nodes
            if q in n.name.lower() or q in n.description.lower()
        ]
        return sorted(results, key=lambda n: -n.mention_count)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _bfs_filtered(
        self,
        start_id:   str,
        max_depth:  int,
        edge_types: Set[RelationshipType],
        direction:  str,
    ) -> List[TraversalResult]:
        """BFS with a set of allowed edge types."""
        results:  List[TraversalResult] = []
        visited:  Set[str] = {start_id}
        queue:    deque    = deque([(start_id, 0, [start_id], None)])

        while queue:
            current_id, depth, path, via = queue.popleft()

            if depth > 0:
                node = self._store.get_node(current_id)
                if node:
                    results.append(TraversalResult(
                        node=node, depth=depth, path=path, via_edge=via
                    ))

            if depth >= max_depth:
                continue

            edges: List[Edge] = []
            for etype in edge_types:
                if direction == "outgoing":
                    edges += self._store.get_edges_from(current_id, etype)
                else:
                    edges += self._store.get_edges_to(current_id, etype)

            for edge in edges:
                nid = (edge.target_id if direction == "outgoing" else edge.source_id)
                if nid not in visited:
                    visited.add(nid)
                    queue.append((nid, depth + 1, path + [nid], edge))

        return results
