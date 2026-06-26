"""Step 29: Knowledge Graph query algorithms.

Provides BFS/DFS traversal, shortest-path (Dijkstra), subgraph extraction,
pattern matching, hub detection, connected-component clustering, and
knowledge-gap analysis on top of :class:`GraphStore`.
"""

from __future__ import annotations

import heapq
import logging
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class GraphQueryEngine:
    """Graph query algorithms operating on a :class:`GraphStore` instance.

    Parameters
    ----------
    store:
        A :class:`GraphStore` used for all database access.
    """

    def __init__(self, store: Any) -> None:
        self._store = store

    # ------------------------------------------------------------------ #
    #  Traversal                                                          #
    # ------------------------------------------------------------------ #

    def bfs_traverse(
        self,
        start_id: str,
        max_depth: int = 3,
        min_confidence: float = 0.0,
        relation_filter: Optional[str] = None,
    ) -> List[Tuple[Dict[str, Any], int, List[str]]]:
        """Breadth-first traversal from *start_id*.

        Returns a list of ``(node_dict, depth, edge_id_path)`` tuples.
        """
        start_node = self._store.get_node(start_id)
        if not start_node:
            return []

        results: list[Tuple[Dict[str, Any], int, List[str]]] = []
        visited: set[str] = {start_id}
        queue: deque[Tuple[str, int, List[str]]] = deque()
        queue.append((start_id, 0, []))
        results.append((start_node, 0, []))

        while queue:
            current_id, depth, path = queue.popleft()
            if depth >= max_depth:
                continue

            edges = self._store.get_edges_from(current_id, relation_type=relation_filter)
            for edge in edges:
                if edge["confidence"] < min_confidence:
                    continue
                target_id = edge["target_id"]
                if target_id in visited:
                    continue
                target_node = self._store.get_node(target_id)
                if not target_node:
                    continue
                visited.add(target_id)
                new_path = path + [edge["id"]]
                results.append((target_node, depth + 1, new_path))
                queue.append((target_id, depth + 1, new_path))

        return results

    def dfs_traverse(
        self,
        start_id: str,
        max_depth: int = 3,
        min_confidence: float = 0.0,
        relation_filter: Optional[str] = None,
    ) -> List[Tuple[Dict[str, Any], int, List[str]]]:
        """Depth-first traversal from *start_id*.

        Returns a list of ``(node_dict, depth, edge_id_path)`` tuples.
        """
        start_node = self._store.get_node(start_id)
        if not start_node:
            return []

        results: list[Tuple[Dict[str, Any], int, List[str]]] = []
        visited: set[str] = set()

        stack: list[Tuple[str, int, List[str]]] = [(start_id, 0, [])]
        while stack:
            current_id, depth, path = stack.pop()
            if current_id in visited:
                continue
            visited.add(current_id)

            current_node = self._store.get_node(current_id)
            if not current_node:
                continue
            results.append((current_node, depth, path))

            if depth >= max_depth:
                continue

            edges = self._store.get_edges_from(current_id, relation_type=relation_filter)
            for edge in reversed(edges):
                if edge["confidence"] < min_confidence:
                    continue
                target_id = edge["target_id"]
                if target_id not in visited:
                    stack.append((target_id, depth + 1, path + [edge["id"]]))

        return results

    # ------------------------------------------------------------------ #
    #  Shortest Path (Dijkstra)                                           #
    # ------------------------------------------------------------------ #

    def find_shortest_path(
        self,
        start_id: str,
        end_id: str,
        max_depth: int = 5,
    ) -> List[Dict[str, Any]]:
        """Find the shortest path between two nodes using Dijkstra's algorithm.

        Edge cost is ``1 / confidence`` (higher confidence = lower cost).
        Returns the list of edge dicts forming the path, or an empty list
        if no path is found within *max_depth* hops.
        """
        dist: dict[str, float] = {start_id: 0.0}
        prev_edge: dict[str, Dict[str, Any]] = {}
        prev_node: dict[str, str] = {}
        heap: list[Tuple[float, str]] = [(0.0, start_id)]
        hops: dict[str, int] = {start_id: 0}

        while heap:
            cost, u = heapq.heappop(heap)
            if u == end_id:
                break
            if cost > dist.get(u, float("inf")):
                continue
            if hops.get(u, 0) >= max_depth:
                continue

            edges = self._store.get_edges_from(u)
            for edge in edges:
                v = edge["target_id"]
                conf = edge.get("confidence", 1.0)
                edge_cost = 1.0 / max(conf, 0.01)
                new_cost = cost + edge_cost
                if new_cost < dist.get(v, float("inf")):
                    dist[v] = new_cost
                    prev_edge[v] = edge
                    prev_node[v] = u
                    hops[v] = hops[u] + 1
                    heapq.heappush(heap, (new_cost, v))

        if end_id not in prev_edge:
            return []

        path: list[Dict[str, Any]] = []
        cur = end_id
        while cur in prev_edge:
            path.append(prev_edge[cur])
            cur = prev_node[cur]
        path.reverse()
        return path

    # ------------------------------------------------------------------ #
    #  Subgraph Extraction                                                #
    # ------------------------------------------------------------------ #

    def get_subgraph(
        self,
        center_id: str,
        radius: int = 2,
        min_confidence: float = 0.0,
    ) -> Dict[str, Any]:
        """Extract a subgraph centred on *center_id* within *radius* hops.

        Returns ``{"nodes": [...], "edges": [...]}``.
        """
        nodes: dict[str, Dict[str, Any]] = {}
        edges: list[Dict[str, Any]] = []
        visited: set[str] = {center_id}
        queue: deque[Tuple[str, int]] = deque([(center_id, 0)])

        center_node = self._store.get_node(center_id)
        if center_node:
            nodes[center_id] = center_node

        while queue:
            current_id, depth = queue.popleft()
            if depth >= radius:
                continue

            out_edges = self._store.get_edges_from(current_id)
            in_edges = self._store.get_edges_to(current_id)
            for edge in out_edges + in_edges:
                if edge["confidence"] < min_confidence:
                    continue
                edges.append(edge)
                for nid in (edge["source_id"], edge["target_id"]):
                    if nid not in visited:
                        visited.add(nid)
                        node = self._store.get_node(nid)
                        if node:
                            nodes[nid] = node
                        queue.append((nid, depth + 1))

        return {"nodes": list(nodes.values()), "edges": edges}

    # ------------------------------------------------------------------ #
    #  Pattern Matching                                                   #
    # ------------------------------------------------------------------ #

    def find_pattern(
        self,
        entity_type: Optional[str] = None,
        relation_type: Optional[str] = None,
        properties_match: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Find nodes matching the given structural / property pattern.

        At least one of *entity_type* or *relation_type* should be provided.
        When *properties_match* is given, nodes are further filtered to only
        those whose ``properties`` dict contains all specified key-value pairs.
        """
        candidates: list[Dict[str, Any]] = []

        if entity_type:
            conn = self._store._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM kg_nodes WHERE entity_type = ?", (entity_type,)
                ).fetchall()
                candidates = [self._store._row_to_node(r) for r in rows]
            finally:
                conn.close()
        else:
            conn = self._store._get_conn()
            try:
                rows = conn.execute("SELECT * FROM kg_nodes").fetchall()
                candidates = [self._store._row_to_node(r) for r in rows]
            finally:
                conn.close()

        if relation_type:
            connected_ids: set[str] = set()
            conn = self._store._get_conn()
            try:
                rows = conn.execute(
                    "SELECT source_id, target_id FROM kg_edges WHERE relation_type = ?",
                    (relation_type,),
                ).fetchall()
                for r in rows:
                    connected_ids.add(r["source_id"])
                    connected_ids.add(r["target_id"])
            finally:
                conn.close()
            candidates = [n for n in candidates if n["id"] in connected_ids]

        if properties_match:
            filtered: list[Dict[str, Any]] = []
            for n in candidates:
                props = n.get("properties", {})
                if all(props.get(k) == v for k, v in properties_match.items()):
                    filtered.append(n)
            candidates = filtered

        return candidates

    # ------------------------------------------------------------------ #
    #  Relation Counting                                                  #
    # ------------------------------------------------------------------ #

    def count_relations(self, node_id: str) -> Dict[str, int]:
        """Return a mapping of ``relation_type -> count`` for all edges of *node_id*."""
        conn = self._store._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT relation_type, COUNT(*) AS cnt FROM kg_edges
                WHERE source_id = ? OR target_id = ?
                GROUP BY relation_type
                """,
                (node_id, node_id),
            ).fetchall()
            return {r["relation_type"]: r["cnt"] for r in rows}
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    #  Hub Detection                                                      #
    # ------------------------------------------------------------------ #

    def find_hubs(self, top_n: int = 10) -> List[Tuple[Dict[str, Any], int]]:
        """Find the *top_n* nodes with the highest degree (in + out edges)."""
        conn = self._store._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT node_id, COUNT(*) AS degree FROM (
                    SELECT source_id AS node_id FROM kg_edges
                    UNION ALL
                    SELECT target_id AS node_id FROM kg_edges
                ) GROUP BY node_id
                ORDER BY degree DESC
                LIMIT ?
                """,
                (top_n,),
            ).fetchall()
            results: list[Tuple[Dict[str, Any], int]] = []
            for r in rows:
                node = self._store.get_node(r["node_id"])
                if node:
                    results.append((node, r["degree"]))
            return results
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    #  Connected Components (Clusters)                                    #
    # ------------------------------------------------------------------ #

    def find_clusters(self, min_size: int = 3) -> List[List[Dict[str, Any]]]:
        """Find connected components (ignoring edge direction) with at least *min_size* nodes."""
        conn = self._store._get_conn()
        try:
            node_rows = conn.execute("SELECT id FROM kg_nodes").fetchall()
            edge_rows = conn.execute("SELECT source_id, target_id FROM kg_edges").fetchall()
        finally:
            conn.close()

        all_ids = {r["id"] for r in node_rows}
        adj: dict[str, set[str]] = defaultdict(set)
        for e in edge_rows:
            adj[e["source_id"]].add(e["target_id"])
            adj[e["target_id"]].add(e["source_id"])

        visited: set[str] = set()
        clusters: list[list[str]] = []
        for nid in all_ids:
            if nid in visited:
                continue
            component: list[str] = []
            stack = [nid]
            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                component.append(cur)
                for neighbor in adj.get(cur, set()):
                    if neighbor not in visited and neighbor in all_ids:
                        stack.append(neighbor)
            if len(component) >= min_size:
                clusters.append(component)

        result: list[list[Dict[str, Any]]] = []
        for cluster_ids in clusters:
            nodes = []
            for cid in cluster_ids:
                node = self._store.get_node(cid)
                if node:
                    nodes.append(node)
            if nodes:
                result.append(nodes)
        return result

    # ------------------------------------------------------------------ #
    #  Knowledge Gap Detection                                            #
    # ------------------------------------------------------------------ #

    def find_knowledge_gaps(self, goal_id: str) -> List[Dict[str, Any]]:
        """Identify missing prerequisite nodes needed to reach *goal_id*.

        Walks backwards along PREREQUISITE_OF and DEPENDS_ON edges from the
        goal.  Any referenced node that does **not** exist in the graph, or
        has confidence below 0.3, is considered a knowledge gap.
        """
        goal_node = self._store.get_node(goal_id)
        if not goal_node:
            return []

        gap_names: set[str] = set()
        gaps: list[Dict[str, Any]] = []
        visited: set[str] = set()
        queue: deque[str] = deque([goal_id])

        while queue:
            current_id = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)

            incoming = self._store.get_edges_to(current_id)
            for edge in incoming:
                if edge["relation_type"] not in ("PREREQUISITE_OF", "DEPENDS_ON"):
                    continue
                prereq_id = edge["source_id"]
                prereq_node = self._store.get_node(prereq_id)
                if prereq_node is None or prereq_node.get("confidence", 0) < 0.3:
                    key = prereq_id if prereq_node is None else prereq_node.get("name", prereq_id)
                    if key not in gap_names:
                        gap_names.add(key)
                        gaps.append({
                            "missing_node_id": prereq_id,
                            "name": prereq_node["name"] if prereq_node else prereq_id,
                            "needed_by": current_id,
                            "relation": edge["relation_type"],
                        })
                elif prereq_id not in visited:
                    queue.append(prereq_id)

        return gaps
