from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.config import load_config
from backend.core.logger import log_event


class KnowledgeGraph:
    """Knowledge Graph Subsystem (Layer 8 - Step 8.3).

    Maintains a semantic network linking agents, tools, tasks, and code resources.
    Enables relationship-based reasoning and contextual queries across the ecosystem.
    """

    _lock = threading.RLock()
    _schema_ensured = False

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        with cls._lock:
            if not cls._schema_ensured:
                cls._ensure_schema(conn)
                cls._schema_ensured = True
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS hm_knowledge_graph_nodes (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL, -- 'tool', 'agent', 'artifact', 'concept', 'constraint'
                    properties TEXT NOT NULL DEFAULT '{}' -- JSON properties
                );
                CREATE INDEX IF NOT EXISTS idx_kg_nodes_type ON hm_knowledge_graph_nodes(type);

                CREATE TABLE IF NOT EXISTS hm_knowledge_graph_edges (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL, -- 'DEPENDS_ON', 'EXECUTED_BY', 'WRITES', 'READS'
                    properties TEXT NOT NULL DEFAULT '{}', -- JSON properties
                    PRIMARY KEY (source_id, target_id, relation_type),
                    FOREIGN KEY (source_id) REFERENCES hm_knowledge_graph_nodes(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES hm_knowledge_graph_nodes(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_kg_edges_source ON hm_knowledge_graph_edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_kg_edges_target ON hm_knowledge_graph_edges(target_id);
                """
            )
            conn.commit()

    @classmethod
    def add_node(cls, node_id: str, node_type: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """Adds or updates a node in the knowledge graph."""
        props = properties or {}
        props_str = json.dumps(props)
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_knowledge_graph_nodes (id, type, properties)
                    VALUES (?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        type = excluded.type,
                        properties = excluded.properties
                    """,
                    (node_id.strip(), node_type.strip().lower(), props_str)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def add_edge(
        cls,
        source_id: str,
        target_id: str,
        relation_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Adds or updates a directed edge in the knowledge graph. Requires both nodes to exist first."""
        props = properties or {}
        props_str = json.dumps(props)
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Ensure nodes exist
                src = conn.execute("SELECT id FROM hm_knowledge_graph_nodes WHERE id = ?", (source_id,)).fetchone()
                tgt = conn.execute("SELECT id FROM hm_knowledge_graph_nodes WHERE id = ?", (target_id,)).fetchone()
                if not src:
                    raise ValueError(f"Source node '{source_id}' does not exist.")
                if not tgt:
                    raise ValueError(f"Target node '{target_id}' does not exist.")

                conn.execute(
                    """
                    INSERT INTO hm_knowledge_graph_edges (source_id, target_id, relation_type, properties)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                        properties = excluded.properties
                    """,
                    (source_id.strip(), target_id.strip(), relation_type.strip().upper(), props_str)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_node(cls, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single node's details."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM hm_knowledge_graph_nodes WHERE id = ?", (node_id,)).fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "type": row["type"],
                "properties": json.loads(row["properties"]),
            }
        finally:
            conn.close()

    @classmethod
    def query_neighbors(
        cls,
        node_id: str,
        direction: str = "both",
        relation_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Queries incoming, outgoing, or bidirectional neighboring nodes and relationships."""
        conn = cls._get_sqlite_conn()
        try:
            results = []
            rel_filter = "AND relation_type = ?" if relation_type else ""
            params = []

            # 1. Outgoing neighbors (source_id -> target_id)
            if direction in {"out", "both"}:
                query = f"""
                    SELECT e.*, n.type as target_type, n.properties as target_properties
                    FROM hm_knowledge_graph_edges e
                    JOIN hm_knowledge_graph_nodes n ON e.target_id = n.id
                    WHERE e.source_id = ? {rel_filter}
                """
                params = [node_id]
                if relation_type:
                    params.append(relation_type.upper())
                rows = conn.execute(query, params).fetchall()
                for r in rows:
                    results.append({
                        "node_id": r["target_id"],
                        "type": r["target_type"],
                        "properties": json.loads(r["target_properties"]),
                        "relation": r["relation_type"],
                        "relation_properties": json.loads(r["properties"]),
                        "direction": "out",
                    })

            # 2. Incoming neighbors (target_id -> source_id)
            if direction in {"in", "both"}:
                query = f"""
                    SELECT e.*, n.type as source_type, n.properties as source_properties
                    FROM hm_knowledge_graph_edges e
                    JOIN hm_knowledge_graph_nodes n ON e.source_id = n.id
                    WHERE e.target_id = ? {rel_filter}
                """
                params = [node_id]
                if relation_type:
                    params.append(relation_type.upper())
                rows = conn.execute(query, params).fetchall()
                for r in rows:
                    results.append({
                        "node_id": r["source_id"],
                        "type": r["source_type"],
                        "properties": json.loads(r["source_properties"]),
                        "relation": r["relation_type"],
                        "relation_properties": json.loads(r["properties"]),
                        "direction": "in",
                    })

            return results
        finally:
            conn.close()

    @classmethod
    def find_shortest_path(cls, source_id: str, target_id: str) -> Optional[List[str]]:
        """Breadth-First Search (BFS) implementation to find the shortest path between two nodes."""
        if source_id == target_id:
            return [source_id]

        conn = cls._get_sqlite_conn()
        try:
            # Quick existence check
            src = conn.execute("SELECT id FROM hm_knowledge_graph_nodes WHERE id = ?", (source_id,)).fetchone()
            tgt = conn.execute("SELECT id FROM hm_knowledge_graph_nodes WHERE id = ?", (target_id,)).fetchone()
            if not src or not tgt:
                return None

            # Load adjacency list (directed)
            edges = conn.execute("SELECT source_id, target_id FROM hm_knowledge_graph_edges").fetchall()
            adj: Dict[str, List[str]] = {}
            for e in edges:
                adj.setdefault(e["source_id"], []).append(e["target_id"])

            queue = [[source_id]]
            visited: Set[str] = {source_id}

            while queue:
                path = queue.pop(0)
                node = path[-1]

                if node == target_id:
                    return path

                for neighbor in adj.get(node, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        new_path = list(path)
                        new_path.append(neighbor)
                        queue.append(new_path)

            return None
        finally:
            conn.close()

    @classmethod
    def get_subgraph(cls, node_ids: List[str], depth: int = 1) -> Dict[str, Any]:
        """Traverses the graph up to depth levels from initial node_ids to extract a local subgraph."""
        conn = cls._get_sqlite_conn()
        try:
            visited_nodes: Set[str] = set(node_ids)
            current_frontier = set(node_ids)

            for _ in range(depth):
                if not current_frontier:
                    break
                placeholders = ", ".join("?" for _ in current_frontier)
                query = f"""
                    SELECT source_id, target_id FROM hm_knowledge_graph_edges
                    WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})
                """
                params = list(current_frontier) + list(current_frontier)
                edges = conn.execute(query, params).fetchall()

                next_frontier = set()
                for e in edges:
                    src, tgt = e["source_id"], e["target_id"]
                    if src not in visited_nodes:
                        next_frontier.add(src)
                        visited_nodes.add(src)
                    if tgt not in visited_nodes:
                        next_frontier.add(tgt)
                        visited_nodes.add(tgt)
                current_frontier = next_frontier

            if not visited_nodes:
                return {"nodes": [], "edges": []}

            # Fetch node details
            placeholders = ", ".join("?" for _ in visited_nodes)
            nodes_rows = conn.execute(
                f"SELECT * FROM hm_knowledge_graph_nodes WHERE id IN ({placeholders})",
                list(visited_nodes)
            ).fetchall()

            # Fetch edge details
            edges_rows = conn.execute(
                f"""SELECT * FROM hm_knowledge_graph_edges
                    WHERE source_id IN ({placeholders}) AND target_id IN ({placeholders})""",
                list(visited_nodes) + list(visited_nodes)
            ).fetchall()

            nodes_list = [
                {"id": r["id"], "type": r["type"], "properties": json.loads(r["properties"])}
                for r in nodes_rows
            ]
            edges_list = [
                {
                    "source_id": r["source_id"],
                    "target_id": r["target_id"],
                    "relation_type": r["relation_type"],
                    "properties": json.loads(r["properties"]),
                }
                for r in edges_rows
            ]

            return {"nodes": nodes_list, "edges": edges_list}
        finally:
            conn.close()
