"""Step 29: Knowledge Graph persistence layer.

SQLite-backed storage for typed nodes, weighted edges, aliases, and FTS5
full-text search.  Follows the same conventions as semantic_memory.py,
world_model.py and working_memory.py (WAL journal, RLock, Row factory).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


class GraphStore:
    """SQLite persistence layer for the Knowledge Graph.

    Parameters
    ----------
    db_path:
        Full path to the SQLite database file.  Parent directories are
        created automatically.
    """

    _schema_ensured = False

    def __init__(self, db_path: str) -> None:
        self._db_path = str(db_path)
        self._lock = threading.RLock()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    # -- connection management -------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Return a new connection with WAL mode and schema ensured."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        with self._lock:
            if not GraphStore._schema_ensured:
                self._ensure_schema(conn)
                GraphStore._schema_ensured = True
        return conn

    # -- schema ----------------------------------------------------------

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Create tables, indexes, FTS5 virtual table and sync triggers."""
        with self._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kg_nodes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    properties TEXT DEFAULT '{}',
                    confidence REAL DEFAULT 1.0,
                    source_layer TEXT,
                    belief_state TEXT DEFAULT 'BELIEVED',
                    evidence TEXT DEFAULT '[]',
                    last_verified_at TEXT,
                    valid_from TEXT,
                    valid_until TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kg_edges (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
                    target_id TEXT NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
                    relation_type TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    confidence REAL DEFAULT 1.0,
                    evidence TEXT DEFAULT '[]',
                    source_layer TEXT,
                    valid_from TEXT,
                    valid_until TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kg_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_id TEXT NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
                    alias_name TEXT NOT NULL,
                    alias_type TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_kg_edges_src_rel
                    ON kg_edges(source_id, relation_type);
                CREATE INDEX IF NOT EXISTS idx_kg_edges_tgt_rel
                    ON kg_edges(target_id, relation_type);
                CREATE INDEX IF NOT EXISTS idx_kg_nodes_name_type
                    ON kg_nodes(name, entity_type);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_kg_aliases_unique
                    ON kg_aliases(alias_name, alias_type);
                CREATE INDEX IF NOT EXISTS idx_kg_aliases_canonical
                    ON kg_aliases(canonical_id);

                CREATE VIRTUAL TABLE IF NOT EXISTS kg_nodes_fts USING fts5(
                    name,
                    properties,
                    content='kg_nodes'
                );

                DROP TRIGGER IF EXISTS trg_kg_nodes_ai;
                DROP TRIGGER IF EXISTS trg_kg_nodes_ad;
                DROP TRIGGER IF EXISTS trg_kg_nodes_au;

                CREATE TRIGGER trg_kg_nodes_ai AFTER INSERT ON kg_nodes BEGIN
                    INSERT INTO kg_nodes_fts(rowid, name, properties)
                    VALUES (new.rowid, new.name, new.properties);
                END;

                CREATE TRIGGER trg_kg_nodes_ad AFTER DELETE ON kg_nodes BEGIN
                    INSERT INTO kg_nodes_fts(kg_nodes_fts, rowid, name, properties)
                    VALUES ('delete', old.rowid, old.name, old.properties);
                END;

                CREATE TRIGGER trg_kg_nodes_au AFTER UPDATE OF name, properties ON kg_nodes BEGIN
                    INSERT INTO kg_nodes_fts(kg_nodes_fts, rowid, name, properties)
                    VALUES ('delete', old.rowid, old.name, old.properties);
                    INSERT INTO kg_nodes_fts(rowid, name, properties)
                    VALUES (new.rowid, new.name, new.properties);
                END;
                """
            )
            # Add columns if they do not exist (to support migration/existing DBs)
            for col, col_type, col_default in [
                ("belief_state", "TEXT", "'BELIEVED'"),
                ("evidence", "TEXT", "'[]'"),
                ("last_verified_at", "TEXT", "NULL"),
                ("valid_from", "TEXT", "NULL"),
                ("valid_until", "TEXT", "NULL"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE kg_nodes ADD COLUMN {col} {col_type} DEFAULT {col_default}")
                    conn.commit()
                except sqlite3.OperationalError:
                    pass

            for col, col_type, col_default in [
                ("valid_from", "TEXT", "NULL"),
                ("valid_until", "TEXT", "NULL"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE kg_edges ADD COLUMN {col} {col_type} DEFAULT {col_default}")
                    conn.commit()
                except sqlite3.OperationalError:
                    pass

            fts_count = conn.execute("SELECT COUNT(*) AS c FROM kg_nodes_fts").fetchone()["c"]
            core_count = conn.execute("SELECT COUNT(*) AS c FROM kg_nodes").fetchone()["c"]
            if fts_count == 0 and core_count > 0:
                conn.execute(
                    "INSERT INTO kg_nodes_fts(rowid, name, properties) "
                    "SELECT rowid, name, properties FROM kg_nodes"
                )
            conn.commit()

    # -- node CRUD -------------------------------------------------------

    def insert_node(
        self,
        name: str,
        entity_type: str,
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
        source_layer: Optional[str] = None,
        node_id: Optional[str] = None,
        belief_state: str = "BELIEVED",
        evidence: Optional[List[str]] = None,
        last_verified_at: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> str:
        """Insert a new node and return its id."""
        nid = node_id or str(uuid.uuid4())
        now = _utcnow_iso()
        props_json = json.dumps(properties or {})
        ev_json = json.dumps(evidence or [])
        val_from = valid_from or now
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO kg_nodes
                        (id, name, entity_type, properties, confidence, source_layer, belief_state, evidence, last_verified_at, valid_from, valid_until, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (nid, name.strip(), entity_type, props_json, confidence, source_layer, belief_state, ev_json, last_verified_at, val_from, valid_until, now, now),
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                logger.error("graph_store: insert_node failed: %s", exc)
                raise
            finally:
                conn.close()
        return nid

    def update_node(
        self,
        node_id: str,
        *,
        name: Optional[str] = None,
        entity_type: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        confidence: Optional[float] = None,
        source_layer: Optional[str] = None,
        belief_state: Optional[str] = None,
        evidence: Optional[List[str]] = None,
        last_verified_at: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> bool:
        """Update an existing node. Returns True if a row was modified."""
        sets: list[str] = []
        params: list[Any] = []
        if name is not None:
            sets.append("name = ?")
            params.append(name.strip())
        if entity_type is not None:
            sets.append("entity_type = ?")
            params.append(entity_type)
        if properties is not None:
            sets.append("properties = ?")
            params.append(json.dumps(properties))
        if confidence is not None:
            sets.append("confidence = ?")
            params.append(confidence)
        if source_layer is not None:
            sets.append("source_layer = ?")
            params.append(source_layer)
        if belief_state is not None:
            sets.append("belief_state = ?")
            params.append(belief_state)
        if evidence is not None:
            sets.append("evidence = ?")
            params.append(json.dumps(evidence))
        if last_verified_at is not None:
            sets.append("last_verified_at = ?")
            params.append(last_verified_at)
        if valid_from is not None:
            sets.append("valid_from = ?")
            params.append(valid_from)
        if valid_until is not None:
            sets.append("valid_until = ?")
            params.append(valid_until)
        if not sets:
            return False
        sets.append("updated_at = ?")
        params.append(_utcnow_iso())
        params.append(node_id)
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    f"UPDATE kg_nodes SET {', '.join(sets)} WHERE id = ?", params
                )
                conn.commit()
                return cur.rowcount > 0
            except Exception as exc:
                conn.rollback()
                logger.error("graph_store: update_node failed: %s", exc)
                raise
            finally:
                conn.close()

    def delete_node(self, node_id: str) -> bool:
        """Delete a node (cascades to edges and aliases)."""
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute("DELETE FROM kg_nodes WHERE id = ?", (node_id,))
                conn.commit()
                return cur.rowcount > 0
            except Exception as exc:
                conn.rollback()
                logger.error("graph_store: delete_node failed: %s", exc)
                raise
            finally:
                conn.close()

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single node by id."""
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM kg_nodes WHERE id = ?", (node_id,)).fetchone()
            return self._row_to_node(row) if row else None
        finally:
            conn.close()

    def get_node_by_name(self, name: str, entity_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve the first node matching *name* (case-insensitive)."""
        conn = self._get_conn()
        try:
            if entity_type:
                row = conn.execute(
                    "SELECT * FROM kg_nodes WHERE LOWER(name) = LOWER(?) AND entity_type = ? LIMIT 1",
                    (name.strip(), entity_type),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM kg_nodes WHERE LOWER(name) = LOWER(?) LIMIT 1",
                    (name.strip(),),
                ).fetchone()
            return self._row_to_node(row) if row else None
        finally:
            conn.close()

    def batch_insert_nodes(self, nodes: List[Dict[str, Any]]) -> List[str]:
        """Bulk-insert nodes. Each dict must have *name* and *entity_type*."""
        ids: list[str] = []
        now = _utcnow_iso()
        with self._lock:
            conn = self._get_conn()
            try:
                for n in nodes:
                    nid = n.get("id") or str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO kg_nodes
                            (id, name, entity_type, properties, confidence, source_layer, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            nid, n["name"].strip(), n["entity_type"],
                            json.dumps(n.get("properties", {})),
                            n.get("confidence", 1.0), n.get("source_layer"),
                            n.get("created_at", now), n.get("updated_at", now),
                        ),
                    )
                    ids.append(nid)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                logger.error("graph_store: batch_insert_nodes failed: %s", exc)
                raise
            finally:
                conn.close()
        return ids

    # -- edge CRUD -------------------------------------------------------

    def insert_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        weight: float = 1.0,
        confidence: float = 1.0,
        evidence: Optional[List[str]] = None,
        source_layer: Optional[str] = None,
        edge_id: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> str:
        """Insert a directed edge and return its id."""
        eid = edge_id or str(uuid.uuid4())
        now = _utcnow_iso()
        val_from = valid_from or now
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO kg_edges
                        (id, source_id, target_id, relation_type, weight, confidence, evidence, source_layer, valid_from, valid_until, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (eid, source_id, target_id, relation_type, weight, confidence,
                     json.dumps(evidence or []), source_layer, val_from, valid_until, now),
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                logger.error("graph_store: insert_edge failed: %s", exc)
                raise
            finally:
                conn.close()
        return eid

    def delete_edge(self, edge_id: str) -> bool:
        """Delete an edge by id."""
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute("DELETE FROM kg_edges WHERE id = ?", (edge_id,))
                conn.commit()
                return cur.rowcount > 0
            except Exception as exc:
                conn.rollback()
                logger.error("graph_store: delete_edge failed: %s", exc)
                raise
            finally:
                conn.close()

    def update_edge(
        self,
        edge_id: str,
        *,
        weight: Optional[float] = None,
        confidence: Optional[float] = None,
        evidence: Optional[List[str]] = None,
        source_layer: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> bool:
        """Update an existing edge. Returns True if a row was modified."""
        sets: list[str] = []
        params: list[Any] = []
        if weight is not None:
            sets.append("weight = ?")
            params.append(weight)
        if confidence is not None:
            sets.append("confidence = ?")
            params.append(confidence)
        if evidence is not None:
            sets.append("evidence = ?")
            params.append(json.dumps(evidence))
        if source_layer is not None:
            sets.append("source_layer = ?")
            params.append(source_layer)
        if valid_from is not None:
            sets.append("valid_from = ?")
            params.append(valid_from)
        if valid_until is not None:
            sets.append("valid_until = ?")
            params.append(valid_until)
        if not sets:
            return False
        params.append(edge_id)
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    f"UPDATE kg_edges SET {', '.join(sets)} WHERE id = ?", params
                )
                conn.commit()
                return cur.rowcount > 0
            except Exception as exc:
                conn.rollback()
                logger.error("graph_store: update_edge failed: %s", exc)
                raise
            finally:
                conn.close()

    def get_edges_from(self, node_id: str, relation_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return edges originating from *node_id*."""
        conn = self._get_conn()
        try:
            if relation_type:
                rows = conn.execute(
                    "SELECT * FROM kg_edges WHERE source_id = ? AND relation_type = ?",
                    (node_id, relation_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM kg_edges WHERE source_id = ?", (node_id,)
                ).fetchall()
            return [self._row_to_edge(r) for r in rows]
        finally:
            conn.close()

    def get_edges_to(self, node_id: str, relation_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return edges targeting *node_id*."""
        conn = self._get_conn()
        try:
            if relation_type:
                rows = conn.execute(
                    "SELECT * FROM kg_edges WHERE target_id = ? AND relation_type = ?",
                    (node_id, relation_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM kg_edges WHERE target_id = ?", (node_id,)
                ).fetchall()
            return [self._row_to_edge(r) for r in rows]
        finally:
            conn.close()

    def batch_insert_edges(self, edges: List[Dict[str, Any]]) -> List[str]:
        """Bulk-insert edges."""
        ids: list[str] = []
        now = _utcnow_iso()
        with self._lock:
            conn = self._get_conn()
            try:
                for e in edges:
                    eid = e.get("id") or str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO kg_edges
                            (id, source_id, target_id, relation_type, weight, confidence, evidence, source_layer, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            eid, e["source_id"], e["target_id"], e["relation_type"],
                            e.get("weight", 1.0), e.get("confidence", 1.0),
                            json.dumps(e.get("evidence", [])),
                            e.get("source_layer"), e.get("created_at", now),
                        ),
                    )
                    ids.append(eid)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                logger.error("graph_store: batch_insert_edges failed: %s", exc)
                raise
            finally:
                conn.close()
        return ids

    # -- FTS search ------------------------------------------------------

    def search_nodes_fts(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Full-text search across node names and properties."""
        sanitized = self._sanitize_fts(query)
        if not sanitized:
            return []
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT n.* FROM kg_nodes n
                JOIN kg_nodes_fts f ON n.rowid = f.rowid
                WHERE kg_nodes_fts MATCH ?
                ORDER BY f.rank
                LIMIT ?
                """,
                (sanitized, limit),
            ).fetchall()
            return [self._row_to_node(r) for r in rows]
        except Exception as exc:
            logger.error("graph_store: FTS search failed: %s", exc)
            return []
        finally:
            conn.close()

    # -- alias management ------------------------------------------------

    def insert_alias(self, canonical_id: str, alias_name: str, alias_type: Optional[str] = None) -> None:
        """Register an alias pointing to *canonical_id*."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO kg_aliases (canonical_id, alias_name, alias_type)
                    VALUES (?, ?, ?)
                    ON CONFLICT(alias_name, alias_type) DO UPDATE SET
                        canonical_id = excluded.canonical_id
                    """,
                    (canonical_id, alias_name.strip(), alias_type),
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                logger.error("graph_store: insert_alias failed: %s", exc)
                raise
            finally:
                conn.close()

    def get_aliases(self, canonical_id: str) -> List[Dict[str, Any]]:
        """Return all aliases for a canonical node."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM kg_aliases WHERE canonical_id = ?", (canonical_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def resolve_alias(self, alias_name: str, alias_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Resolve an alias to its canonical node, returning the node dict or None."""
        conn = self._get_conn()
        try:
            if alias_type:
                row = conn.execute(
                    "SELECT canonical_id FROM kg_aliases WHERE LOWER(alias_name) = LOWER(?) AND alias_type = ?",
                    (alias_name.strip(), alias_type),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT canonical_id FROM kg_aliases WHERE LOWER(alias_name) = LOWER(?)",
                    (alias_name.strip(),),
                ).fetchone()
            if not row:
                return None
            node_row = conn.execute(
                "SELECT * FROM kg_nodes WHERE id = ?", (row["canonical_id"],)
            ).fetchone()
            return self._row_to_node(node_row) if node_row else None
        finally:
            conn.close()

    # -- internal helpers ------------------------------------------------

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a SQLite row to a node dict with parsed JSON fields."""
        d = dict(row)
        d["properties"] = json.loads(d.get("properties") or "{}")
        d["evidence"] = json.loads(d.get("evidence") or "[]")
        return d

    @staticmethod
    def _row_to_edge(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a SQLite row to an edge dict with parsed JSON fields."""
        d = dict(row)
        d["evidence"] = json.loads(d.get("evidence") or "[]")
        return d

    @staticmethod
    def _sanitize_fts(query: str) -> str:
        """Build a safe FTS5 match expression from free-text *query*."""
        words = re.findall(r"\w+", query)
        if not words:
            return ""
        return " AND ".join(f'"{w}"*' for w in words)
