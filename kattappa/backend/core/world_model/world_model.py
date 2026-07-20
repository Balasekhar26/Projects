"""World Model (Tier 2) — Step 19 Upgrade.

Kattappa's internal map of reality: a persistent graph of entities (projects,
components, devices, people, resources, goals) and their relationships
(contains / depends_on / affects). With it, Kattappa can reason about
consequences rather than just plan:

    Changing RF Module -> affects Antenna -> affects Range -> affects Battery Life

Deterministic and persistent. It models reality; it never executes.
Backed by SQLite to support causal graphs, snapshots, and predictions.

Step 19 additions:
- Belief confidence states (STATED / OBSERVED / INFERRED / CONFIRMED) on each
  entity attribute, consistent with Semantic and Relationship Memory layers.
- Append-only causal change log cross-linked to episodic evidence.
- Belief conflict detection: contradicting state updates are queued, not
  silently overwritten (same discipline as Relationship Memory Conflict Queue).
- query_world_context() retrieval API for MemoryAssembler integration.
- impact_of() enriched with per-entity confidence from belief states.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from backend.core.config import load_config


class EntityType(str, Enum):
    PROJECT = "project"
    COMPONENT = "component"
    DEVICE = "device"
    PERSON = "person"
    RESOURCE = "resource"
    GOAL = "goal"
    OTHER = "other"

    @classmethod
    def coerce(cls, value: "EntityType | str") -> "EntityType":
        try:
            return value if isinstance(value, cls) else cls(str(value).strip().lower())
        except ValueError:
            return cls.OTHER


class RelationType(str, Enum):
    CONTAINS = "contains"
    DEPENDS_ON = "depends_on"
    AFFECTS = "affects"
    RELATED = "related"

    @classmethod
    def coerce(cls, value: "RelationType | str") -> "RelationType":
        try:
            return value if isinstance(value, cls) else cls(str(value).strip().lower())
        except ValueError:
            return cls.RELATED


# Valid confidence states — consistent with Semantic and Relationship Memory
_VALID_CONFIDENCE_STATES = {"STATED", "OBSERVED", "INFERRED", "CONFIRMED"}

# Confidence state ordering for conflict resolution (higher index = stronger evidence)
_CONFIDENCE_STATE_ORDER = {"INFERRED": 0, "OBSERVED": 1, "STATED": 2, "CONFIRMED": 3}


class WorldModel:
    _lock = threading.RLock()
    _max_depth = 25
    _schema_ensured = False

    # -- persistence via SQLite -------------------------------------------
    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        with cls._lock:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='world_state_nodes'")
            if not cursor.fetchone():
                cls._ensure_schema(conn)
            else:
                cls._apply_migrations(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            conn.executescript(
                """
                -- Core entity graph
                CREATE TABLE IF NOT EXISTS world_state_nodes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT,
                    attributes TEXT,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_world_nodes_type ON world_state_nodes(type);

                CREATE TABLE IF NOT EXISTS world_state_edges (
                    src TEXT NOT NULL,
                    dst TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    PRIMARY KEY (src, dst, relation),
                    FOREIGN KEY(src) REFERENCES world_state_nodes(id) ON DELETE CASCADE,
                    FOREIGN KEY(dst) REFERENCES world_state_nodes(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS world_state_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    state_data TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS world_state_predictions (
                    prediction_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    predicted_success REAL NOT NULL,
                    predicted_cost REAL NOT NULL,
                    predicted_time TEXT NOT NULL,
                    confidence_interval TEXT NOT NULL,
                    risk_score REAL NOT NULL,
                    timestamp REAL NOT NULL
                );

                -- Step 19: Belief confidence tracking per entity attribute
                CREATE TABLE IF NOT EXISTS world_belief_states (
                    belief_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES world_state_nodes(id) ON DELETE CASCADE,
                    attribute TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
                    confidence_state TEXT NOT NULL DEFAULT 'INFERRED'
                        CHECK (confidence_state IN ('STATED', 'OBSERVED', 'INFERRED', 'CONFIRMED')),
                    source_episode_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(entity_id, attribute)
                );
                CREATE INDEX IF NOT EXISTS idx_world_beliefs_entity ON world_belief_states(entity_id);

                -- Step 19: Append-only causal change log
                CREATE TABLE IF NOT EXISTS world_causal_log (
                    log_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    change_type TEXT NOT NULL CHECK (change_type IN (
                        'ENTITY_ADDED', 'ENTITY_UPDATED', 'RELATION_ADDED',
                        'RELATION_REMOVED', 'STATUS_CHANGED', 'BELIEF_UPDATED'
                    )),
                    description TEXT NOT NULL,
                    source_episode_id TEXT,
                    changed_by TEXT NOT NULL DEFAULT 'agent',
                    timestamp REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_world_causal_entity ON world_causal_log(entity_id);
                CREATE INDEX IF NOT EXISTS idx_world_causal_time ON world_causal_log(timestamp DESC);

                -- Step 19: Belief conflict queue (contradictions are queued, not overwritten)
                CREATE TABLE IF NOT EXISTS world_belief_conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    attribute TEXT NOT NULL,
                    old_value TEXT NOT NULL,
                    new_value TEXT NOT NULL,
                    old_confidence REAL NOT NULL,
                    new_confidence REAL NOT NULL,
                    resolution_state TEXT DEFAULT 'PENDING'
                        CHECK (resolution_state IN ('PENDING', 'RESOLVED_NEW', 'RESOLVED_OLD', 'DISCARDED')),
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_world_conflicts_entity ON world_belief_conflicts(entity_id);
                CREATE INDEX IF NOT EXISTS idx_world_conflicts_state ON world_belief_conflicts(resolution_state);
                """
            )
            conn.commit()

    @classmethod
    def _apply_migrations(cls, conn: sqlite3.Connection) -> None:
        """Dynamically apply Step 19 schema additions to existing database instances."""
        with cls._lock:
            existing_tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

            if "world_belief_states" not in existing_tables:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS world_belief_states (
                        belief_id TEXT PRIMARY KEY,
                        entity_id TEXT NOT NULL REFERENCES world_state_nodes(id) ON DELETE CASCADE,
                        attribute TEXT NOT NULL,
                        value TEXT NOT NULL,
                        confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
                        confidence_state TEXT NOT NULL DEFAULT 'INFERRED'
                            CHECK (confidence_state IN ('STATED', 'OBSERVED', 'INFERRED', 'CONFIRMED')),
                        source_episode_id TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        UNIQUE(entity_id, attribute)
                    );
                    CREATE INDEX IF NOT EXISTS idx_world_beliefs_entity ON world_belief_states(entity_id);
                    """
                )

            if "world_causal_log" not in existing_tables:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS world_causal_log (
                        log_id TEXT PRIMARY KEY,
                        entity_id TEXT NOT NULL,
                        change_type TEXT NOT NULL CHECK (change_type IN (
                            'ENTITY_ADDED', 'ENTITY_UPDATED', 'RELATION_ADDED',
                            'RELATION_REMOVED', 'STATUS_CHANGED', 'BELIEF_UPDATED'
                        )),
                        description TEXT NOT NULL,
                        source_episode_id TEXT,
                        changed_by TEXT NOT NULL DEFAULT 'agent',
                        timestamp REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_world_causal_entity ON world_causal_log(entity_id);
                    CREATE INDEX IF NOT EXISTS idx_world_causal_time ON world_causal_log(timestamp DESC);
                    """
                )

            if "world_belief_conflicts" not in existing_tables:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS world_belief_conflicts (
                        conflict_id TEXT PRIMARY KEY,
                        entity_id TEXT NOT NULL,
                        attribute TEXT NOT NULL,
                        old_value TEXT NOT NULL,
                        new_value TEXT NOT NULL,
                        old_confidence REAL NOT NULL,
                        new_confidence REAL NOT NULL,
                        resolution_state TEXT DEFAULT 'PENDING'
                            CHECK (resolution_state IN ('PENDING', 'RESOLVED_NEW', 'RESOLVED_OLD', 'DISCARDED')),
                        created_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_world_conflicts_entity ON world_belief_conflicts(entity_id);
                    CREATE INDEX IF NOT EXISTS idx_world_conflicts_state ON world_belief_conflicts(resolution_state);
                    """
                )

            conn.commit()

    @staticmethod
    def _key(name: str) -> str:
        return name.strip().lower()

    # -- internal helpers --------------------------------------------------

    @classmethod
    def _log_causal_change(
        cls,
        conn: sqlite3.Connection,
        entity_id: str,
        change_type: str,
        description: str,
        source_episode_id: Optional[str] = None,
        changed_by: str = "agent",
    ) -> None:
        """Append a record to the causal change log (never deleted)."""
        conn.execute(
            """
            INSERT INTO world_causal_log
                (log_id, entity_id, change_type, description, source_episode_id, changed_by, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), entity_id, change_type, description,
             source_episode_id, changed_by, time.time()),
        )

    @classmethod
    def _write_belief_state(
        cls,
        conn: sqlite3.Connection,
        entity_id: str,
        attribute: str,
        value: str,
        confidence: float,
        confidence_state: str,
        source_episode_id: Optional[str],
    ) -> None:
        """Upsert a belief state for entity+attribute.

        Implements conflict detection: if the existing belief has a *different*
        value and the new evidence is not strictly stronger, route to the
        conflict queue instead of silently overwriting.
        """
        now = time.time()
        confidence = max(0.0, min(1.0, confidence))
        if confidence_state not in _VALID_CONFIDENCE_STATES:
            confidence_state = "INFERRED"

        existing = conn.execute(
            "SELECT belief_id, value, confidence, confidence_state FROM world_belief_states "
            "WHERE entity_id = ? AND attribute = ?",
            (entity_id, attribute),
        ).fetchone()

        if existing and existing["value"] != value:
            old_order = _CONFIDENCE_STATE_ORDER.get(existing["confidence_state"], 0)
            new_order = _CONFIDENCE_STATE_ORDER.get(confidence_state, 0)

            if new_order < old_order or (new_order == old_order and confidence <= existing["confidence"]):
                # Weaker or equal evidence contradicts current belief — queue the conflict
                conn.execute(
                    """
                    INSERT INTO world_belief_conflicts
                        (conflict_id, entity_id, attribute, old_value, new_value,
                         old_confidence, new_confidence, resolution_state, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                    """,
                    (str(uuid.uuid4()), entity_id, attribute,
                     existing["value"], value,
                     existing["confidence"], confidence, now),
                )
                return  # Do NOT overwrite

        # Stronger evidence or first-time write → upsert
        if existing:
            conn.execute(
                """
                UPDATE world_belief_states
                SET value = ?, confidence = ?, confidence_state = ?,
                    source_episode_id = ?, updated_at = ?
                WHERE entity_id = ? AND attribute = ?
                """,
                (value, confidence, confidence_state, source_episode_id, now,
                 entity_id, attribute),
            )
        else:
            conn.execute(
                """
                INSERT INTO world_belief_states
                    (belief_id, entity_id, attribute, value, confidence,
                     confidence_state, source_episode_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), entity_id, attribute, value, confidence,
                 confidence_state, source_episode_id, now, now),
            )

    # -- entities & relations ---------------------------------------------
    @classmethod
    def add_entity(
        cls,
        name: str,
        entity_type: "EntityType | str" = EntityType.OTHER,
        *,
        status: str = "",
        attributes: dict[str, Any] | None = None,
        # Step 19 additions
        confidence: float = 0.7,
        confidence_state: str = "INFERRED",
        source_episode_id: Optional[str] = None,
        changed_by: str = "agent",
    ) -> dict[str, Any]:
        """Add or update an entity in the world graph.

        Step 19: also writes a belief state record for the entity's status
        attribute and appends an ENTITY_ADDED / ENTITY_UPDATED entry to the
        causal change log.
        """
        name = name.strip()
        if not name:
            raise ValueError("Entity name cannot be empty")

        entity_id = cls._key(name)
        etype = EntityType.coerce(entity_type).value
        attrs_str = json.dumps(dict(attributes or {}))
        now = time.time()

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                existing_row = conn.execute(
                    "SELECT id FROM world_state_nodes WHERE id = ?", (entity_id,)
                ).fetchone()
                change_type = "ENTITY_UPDATED" if existing_row else "ENTITY_ADDED"

                conn.execute(
                    """
                    INSERT INTO world_state_nodes (id, name, type, status, attributes, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        type=excluded.type,
                        status=excluded.status,
                        attributes=excluded.attributes,
                        updated_at=excluded.updated_at
                    """,
                    (entity_id, name, etype, status, attrs_str, now),
                )

                # Write belief state for entity status
                if status:
                    cls._write_belief_state(
                        conn, entity_id, "status", status,
                        confidence, confidence_state, source_episode_id,
                    )

                # Write belief states for any provided attributes
                for attr_key, attr_val in (attributes or {}).items():
                    cls._write_belief_state(
                        conn, entity_id, attr_key, str(attr_val),
                        confidence, confidence_state, source_episode_id,
                    )

                # Append causal change log
                desc = f"Entity '{name}' ({etype}) {'updated' if change_type == 'ENTITY_UPDATED' else 'added'}"
                if status:
                    desc += f" with status='{status}'"
                cls._log_causal_change(
                    conn, entity_id, change_type, desc,
                    source_episode_id, changed_by,
                )

                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        return {
            "name": name,
            "type": etype,
            "status": status,
            "attributes": dict(attributes or {}),
            "confidence": confidence,
            "confidence_state": confidence_state,
            "updated_at": now,
        }

    @classmethod
    def update_entity_status(
        cls,
        name: str,
        new_status: str,
        *,
        confidence: float = 0.7,
        confidence_state: str = "OBSERVED",
        source_episode_id: Optional[str] = None,
        changed_by: str = "agent",
    ) -> bool:
        """Update an entity's status field with conflict detection.

        If the new status contradicts an existing belief with equal or stronger
        confidence, the change is routed to the conflict queue instead of
        being applied. Returns True if the status was actually updated.
        """
        entity_id = cls._key(name)
        now = time.time()

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute(
                    "SELECT id, status FROM world_state_nodes WHERE id = ?",
                    (entity_id,),
                ).fetchone()
                if not row:
                    raise KeyError(f"No entity {name!r}")

                old_status = row["status"] or ""

                # Write belief state (with conflict detection inside)
                existing_belief = conn.execute(
                    "SELECT value FROM world_belief_states WHERE entity_id = ? AND attribute = 'status'",
                    (entity_id,),
                ).fetchone()
                prev_belief_value = existing_belief["value"] if existing_belief else None

                cls._write_belief_state(
                    conn, entity_id, "status", new_status,
                    confidence, confidence_state, source_episode_id,
                )

                # Check if belief was written or queued as conflict
                post_belief = conn.execute(
                    "SELECT value FROM world_belief_states WHERE entity_id = ? AND attribute = 'status'",
                    (entity_id,),
                ).fetchone()
                belief_was_written = (post_belief and post_belief["value"] == new_status)

                if belief_was_written:
                    conn.execute(
                        "UPDATE world_state_nodes SET status = ?, updated_at = ? WHERE id = ?",
                        (new_status, now, entity_id),
                    )
                    cls._log_causal_change(
                        conn, entity_id, "STATUS_CHANGED",
                        f"Status changed from '{old_status}' to '{new_status}'",
                        source_episode_id, changed_by,
                    )

                conn.commit()
                return belief_was_written
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def add_relation(
        cls,
        src: str,
        dst: str,
        relation: "RelationType | str" = RelationType.RELATED,
        *,
        source_episode_id: Optional[str] = None,
        changed_by: str = "agent",
    ) -> dict[str, Any]:
        """Add a directional edge between two entities.

        Step 19: logs the relation addition to the causal change log.
        """
        src_id = cls._key(src)
        dst_id = cls._key(dst)
        rel_type = RelationType.coerce(relation).value

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cursor = conn.execute("SELECT 1 FROM world_state_nodes WHERE id = ?", (src_id,))
                if not cursor.fetchone():
                    raise ValueError(f"Unknown entity {src!r}")

                cursor = conn.execute("SELECT 1 FROM world_state_nodes WHERE id = ?", (dst_id,))
                if not cursor.fetchone():
                    raise ValueError(f"Unknown entity {dst!r}")

                conn.execute(
                    "INSERT OR IGNORE INTO world_state_edges (src, dst, relation) VALUES (?, ?, ?)",
                    (src_id, dst_id, rel_type),
                )

                cls._log_causal_change(
                    conn, src_id, "RELATION_ADDED",
                    f"Relation '{rel_type}' added from '{src_id}' to '{dst_id}'",
                    source_episode_id, changed_by,
                )

                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        return {"src": src_id, "dst": dst_id, "relation": rel_type}

    @classmethod
    def get_entity(cls, name: str) -> dict[str, Any] | None:
        entity_id = cls._key(name)
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM world_state_nodes WHERE id = ?", (entity_id,)
                ).fetchone()
                if row:
                    return {
                        "name": row["name"],
                        "type": row["type"],
                        "status": row["status"] or "",
                        "attributes": json.loads(row["attributes"]) if row["attributes"] else {},
                        "updated_at": row["updated_at"],
                    }
            finally:
                conn.close()
        return None

    @classmethod
    def entities(cls) -> list[dict[str, Any]]:
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                rows = conn.execute("SELECT * FROM world_state_nodes").fetchall()
                return [
                    {
                        "name": r["name"],
                        "type": r["type"],
                        "status": r["status"] or "",
                        "attributes": json.loads(r["attributes"]) if r["attributes"] else {},
                        "updated_at": r["updated_at"],
                    }
                    for r in rows
                ]
            finally:
                conn.close()

    @classmethod
    def relations(cls) -> list[dict[str, Any]]:
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                rows = conn.execute("SELECT * FROM world_state_edges").fetchall()
                return [{"src": r["src"], "dst": r["dst"], "relation": r["relation"]} for r in rows]
            finally:
                conn.close()

    @classmethod
    def neighbors(
        cls,
        name: str,
        relation: "RelationType | str | None" = None,
        *,
        direction: str = "out",
    ) -> list[str]:
        key = cls._key(name)
        rel = RelationType.coerce(relation).value if relation is not None else None

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                node_rows = conn.execute("SELECT id, name FROM world_state_nodes").fetchall()
                id_to_name = {r["id"]: r["name"] for r in node_rows}

                query = "SELECT src, dst, relation FROM world_state_edges"
                params: list[Any] = []
                if rel is not None:
                    query += " WHERE relation = ?"
                    params.append(rel)

                rows = conn.execute(query, params).fetchall()

                out: list[str] = []
                for r in rows:
                    if direction == "out" and r["src"] == key:
                        out.append(id_to_name.get(r["dst"], r["dst"]))
                    elif direction == "in" and r["dst"] == key:
                        out.append(id_to_name.get(r["src"], r["src"]))
                return out
            finally:
                conn.close()

    # -- Step 19: Belief State Retrieval ----------------------------------

    @classmethod
    def get_belief_state(cls, name: str) -> list[dict[str, Any]]:
        """Return all known belief states (attribute-level confidence records) for an entity.

        Each belief includes: attribute, value, confidence, confidence_state,
        source_episode_id, created_at, updated_at.
        """
        entity_id = cls._key(name)
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                rows = conn.execute(
                    """
                    SELECT belief_id, attribute, value, confidence, confidence_state,
                           source_episode_id, created_at, updated_at
                    FROM world_belief_states
                    WHERE entity_id = ?
                    ORDER BY updated_at DESC
                    """,
                    (entity_id,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    @classmethod
    def get_causal_log(cls, name: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return the causal change history for an entity, newest first.

        Each entry includes: change_type, description, source_episode_id,
        changed_by, timestamp.
        """
        entity_id = cls._key(name)
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                rows = conn.execute(
                    """
                    SELECT log_id, entity_id, change_type, description,
                           source_episode_id, changed_by, timestamp
                    FROM world_causal_log
                    WHERE entity_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (entity_id, limit),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    # -- Step 19: Conflict Management -------------------------------------

    @classmethod
    def list_conflicts(
        cls,
        resolution_state: str = "PENDING",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List belief conflicts filtered by resolution state."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                rows = conn.execute(
                    """
                    SELECT conflict_id, entity_id, attribute, old_value, new_value,
                           old_confidence, new_confidence, resolution_state, created_at
                    FROM world_belief_conflicts
                    WHERE resolution_state = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (resolution_state, limit),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    @classmethod
    def resolve_conflict(
        cls,
        conflict_id: str,
        resolution: str,
    ) -> bool:
        """Resolve a queued belief conflict.

        resolution must be one of: 'RESOLVED_NEW', 'RESOLVED_OLD', 'DISCARDED'.
        If RESOLVED_NEW, the conflict's new_value is applied to the world graph.
        """
        valid_resolutions = {"RESOLVED_NEW", "RESOLVED_OLD", "DISCARDED"}
        if resolution not in valid_resolutions:
            raise ValueError(f"Invalid resolution: {resolution!r}. Must be one of {valid_resolutions}")

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM world_belief_conflicts WHERE conflict_id = ?",
                    (conflict_id,),
                ).fetchone()
                if not row:
                    return False

                conflict = dict(row)

                conn.execute(
                    "UPDATE world_belief_conflicts SET resolution_state = ? WHERE conflict_id = ?",
                    (resolution, conflict_id),
                )

                if resolution == "RESOLVED_NEW":
                    # Apply the new value to the belief state and world node
                    now = time.time()
                    conn.execute(
                        """
                        UPDATE world_belief_states
                        SET value = ?, updated_at = ?
                        WHERE entity_id = ? AND attribute = ?
                        """,
                        (conflict["new_value"], now,
                         conflict["entity_id"], conflict["attribute"]),
                    )
                    # If attribute is "status", sync to world_state_nodes
                    if conflict["attribute"] == "status":
                        conn.execute(
                            "UPDATE world_state_nodes SET status = ?, updated_at = ? WHERE id = ?",
                            (conflict["new_value"], now, conflict["entity_id"]),
                        )
                    cls._log_causal_change(
                        conn, conflict["entity_id"], "BELIEF_UPDATED",
                        f"Conflict resolved (RESOLVED_NEW): attribute '{conflict['attribute']}' "
                        f"updated to '{conflict['new_value']}'",
                        changed_by="conflict_resolution",
                    )

                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    # -- Step 19: World Context Query -------------------------------------

    @classmethod
    def query_world_context(
        cls,
        query_text: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve world entities relevant to a query string.

        Matching strategy:
        1. Keyword match on entity name and status (case-insensitive substring)
        2. 1-hop expansion: also include direct neighbors of matched entities
           along AFFECTS and DEPENDS_ON edges (causal neighbours)

        Each result includes:
        - entity name, type, status, attributes
        - belief_states: all confidence records for this entity
        - causal_log: up to 3 most recent change records with episode links
        - confidence: maximum confidence across all belief states (or 0.5 default)
        - confidence_state: highest confidence_state across belief states
        """
        if not query_text or not query_text.strip():
            return []

        tokens = [t.lower() for t in query_text.strip().split() if len(t) > 2]
        if not tokens:
            return []

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # 1. Primary keyword match
                all_nodes = conn.execute(
                    "SELECT id, name, type, status, attributes FROM world_state_nodes"
                ).fetchall()

                matched_ids: set[str] = set()
                for node in all_nodes:
                    searchable = f"{node['name']} {node['status'] or ''}".lower()
                    if any(tok in searchable for tok in tokens):
                        matched_ids.add(node["id"])

                # 2. 1-hop causal neighbor expansion
                causal_edges = conn.execute(
                    "SELECT src, dst, relation FROM world_state_edges WHERE relation IN (?, ?)",
                    (RelationType.AFFECTS.value, RelationType.DEPENDS_ON.value),
                ).fetchall()

                neighbor_ids: set[str] = set()
                for edge in causal_edges:
                    if edge["src"] in matched_ids:
                        neighbor_ids.add(edge["dst"])
                    if edge["dst"] in matched_ids:
                        neighbor_ids.add(edge["src"])

                # Combine: direct matches first, then 1-hop neighbors
                candidate_ids = list(matched_ids) + [
                    nid for nid in neighbor_ids if nid not in matched_ids
                ]
                candidate_ids = candidate_ids[:limit]

                if not candidate_ids:
                    return []

                # 3. Build enriched results
                id_to_node = {n["id"]: dict(n) for n in all_nodes}
                results: list[dict[str, Any]] = []

                for eid in candidate_ids:
                    node = id_to_node.get(eid)
                    if not node:
                        continue

                    # Fetch belief states
                    belief_rows = conn.execute(
                        """
                        SELECT attribute, value, confidence, confidence_state,
                               source_episode_id, updated_at
                        FROM world_belief_states
                        WHERE entity_id = ?
                        ORDER BY updated_at DESC
                        """,
                        (eid,),
                    ).fetchall()
                    belief_states = [dict(b) for b in belief_rows]

                    # Fetch most recent 3 causal log entries
                    log_rows = conn.execute(
                        """
                        SELECT change_type, description, source_episode_id,
                               changed_by, timestamp
                        FROM world_causal_log
                        WHERE entity_id = ?
                        ORDER BY timestamp DESC
                        LIMIT 3
                        """,
                        (eid,),
                    ).fetchall()
                    causal_log = [dict(l) for l in log_rows]

                    # Aggregate confidence
                    max_conf = max((b["confidence"] for b in belief_states), default=0.5)
                    best_state = max(
                        belief_states,
                        key=lambda b: _CONFIDENCE_STATE_ORDER.get(b["confidence_state"], 0),
                        default=None,
                    )
                    best_conf_state = best_state["confidence_state"] if best_state else "INFERRED"

                    results.append({
                        "entity_id": eid,
                        "name": node["name"],
                        "type": node["type"],
                        "status": node["status"] or "",
                        "attributes": json.loads(node["attributes"]) if node["attributes"] else {},
                        "confidence": max_conf,
                        "confidence_state": best_conf_state,
                        "belief_states": belief_states,
                        "causal_log": causal_log,
                        "is_direct_match": eid in matched_ids,
                    })

                return results
            finally:
                conn.close()

    # -- impact reasoning --------------------------------------------------
    @classmethod
    def impact_of(cls, name: str) -> dict[str, Any]:
        """What a change to ``name`` propagates to.

        Propagates along outgoing AFFECTS edges and to entities that DEPEND_ON
        this one (incoming depends_on). Returns affected entities with path.

        Step 19: each affected entry now includes ``confidence`` and
        ``confidence_state`` from the entity's belief states.
        """
        start = cls._key(name)
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute(
                    "SELECT name FROM world_state_nodes WHERE id = ?", (start,)
                ).fetchone()
                if not row:
                    raise KeyError(f"No entity {name!r}")
                start_name = row["name"]

                node_rows = conn.execute("SELECT id, name FROM world_state_nodes").fetchall()
                id_to_name = {r["id"]: r["name"] for r in node_rows}

                edges = conn.execute(
                    "SELECT src, dst, relation FROM world_state_edges"
                ).fetchall()

                # Load belief confidence for all nodes
                belief_rows = conn.execute(
                    "SELECT entity_id, confidence, confidence_state FROM world_belief_states"
                ).fetchall()
                entity_confidence: dict[str, float] = {}
                entity_conf_state: dict[str, str] = {}
                for br in belief_rows:
                    eid = br["entity_id"]
                    curr = entity_confidence.get(eid, 0.0)
                    if br["confidence"] > curr:
                        entity_confidence[eid] = br["confidence"]
                        entity_conf_state[eid] = br["confidence_state"]
            finally:
                conn.close()

        # adjacency: change in X reaches Y if X --affects--> Y or Y --depends_on--> X
        adj: dict[str, list[str]] = {}
        for r in edges:
            if r["relation"] == RelationType.AFFECTS.value:
                adj.setdefault(r["src"], []).append(r["dst"])
            elif r["relation"] == RelationType.DEPENDS_ON.value:
                adj.setdefault(r["dst"], []).append(r["src"])

        affected: list[dict[str, Any]] = []
        seen = {start}
        queue: list[tuple[str, list[str]]] = [(start, [start_name])]
        depth = 0
        while queue and depth < cls._max_depth:
            depth += 1
            nxt: list[tuple[str, list[str]]] = []
            for node, path in queue:
                for child in adj.get(node, []):
                    if child in seen:
                        continue
                    seen.add(child)
                    child_name = id_to_name.get(child, child)
                    new_path = path + [child_name]
                    affected.append({
                        "entity": child_name,
                        "depth": depth,
                        "path": new_path,
                        "confidence": entity_confidence.get(child, 0.5),
                        "confidence_state": entity_conf_state.get(child, "INFERRED"),
                    })
                    nxt.append((child, new_path))
            queue = nxt

        return {
            "entity": start_name,
            "affected": affected,
            "affected_names": [a["entity"] for a in affected],
        }

    @classmethod
    def subtree(cls, name: str) -> dict[str, Any]:
        """Hierarchy under ``name`` following CONTAINS edges."""
        key = cls._key(name)
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute(
                    "SELECT name FROM world_state_nodes WHERE id = ?", (key,)
                ).fetchone()
                if not row:
                    raise KeyError(f"No entity {name!r}")
                start_name = row["name"]

                node_rows = conn.execute("SELECT id, name FROM world_state_nodes").fetchall()
                id_to_name = {r["id"]: r["name"] for r in node_rows}

                edges = conn.execute(
                    "SELECT src, dst FROM world_state_edges WHERE relation = ?",
                    (RelationType.CONTAINS.value,),
                ).fetchall()
            finally:
                conn.close()

        children_map: dict[str, list[str]] = {}
        for r in edges:
            children_map.setdefault(r["src"], []).append(r["dst"])

        def build(node: str, seen: set[str]) -> dict[str, Any]:
            seen = seen | {node}
            return {
                "name": id_to_name.get(node, node),
                "children": [build(c, seen) for c in children_map.get(node, []) if c not in seen],
            }

        return build(key, set())

    @classmethod
    def status(cls) -> dict[str, Any]:
        ents = cls.entities()
        by_type: dict[str, int] = {t.value: 0 for t in EntityType}
        for e in ents:
            by_type[e.get("type", "other")] = by_type.get(e.get("type", "other"), 0) + 1
        return {"entities": len(ents), "relations": len(cls.relations()), "by_type": by_type}

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute("DELETE FROM world_belief_conflicts")
                conn.execute("DELETE FROM world_causal_log")
                conn.execute("DELETE FROM world_belief_states")
                conn.execute("DELETE FROM world_state_edges")
                conn.execute("DELETE FROM world_state_nodes")
                conn.execute("DELETE FROM world_state_snapshots")
                conn.execute("DELETE FROM world_state_predictions")
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    # -- snapshots --------------------------------------------------------
    @classmethod
    def create_snapshot(cls, snapshot_id: str) -> None:
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                nodes = conn.execute("SELECT * FROM world_state_nodes").fetchall()
                edges = conn.execute("SELECT * FROM world_state_edges").fetchall()
                beliefs = conn.execute("SELECT * FROM world_belief_states").fetchall()

                state_data = {
                    "nodes": [dict(n) for n in nodes],
                    "edges": [dict(e) for e in edges],
                    "beliefs": [dict(b) for b in beliefs],
                }

                conn.execute(
                    """
                    INSERT INTO world_state_snapshots (snapshot_id, timestamp, state_data)
                    VALUES (?, ?, ?)
                    ON CONFLICT(snapshot_id) DO UPDATE SET
                        timestamp=excluded.timestamp,
                        state_data=excluded.state_data
                    """,
                    (snapshot_id, time.time(), json.dumps(state_data)),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def restore_snapshot(cls, snapshot_id: str) -> None:
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute(
                    "SELECT state_data FROM world_state_snapshots WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchone()
                if not row:
                    raise KeyError(f"Snapshot '{snapshot_id}' not found")

                state_data = json.loads(row["state_data"])

                conn.execute("DELETE FROM world_belief_states")
                conn.execute("DELETE FROM world_state_edges")
                conn.execute("DELETE FROM world_state_nodes")

                for node in state_data.get("nodes", []):
                    conn.execute(
                        """
                        INSERT INTO world_state_nodes (id, name, type, status, attributes, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (node["id"], node["name"], node["type"],
                         node["status"], node["attributes"], node["updated_at"]),
                    )
                for edge in state_data.get("edges", []):
                    conn.execute(
                        "INSERT INTO world_state_edges (src, dst, relation) VALUES (?, ?, ?)",
                        (edge["src"], edge["dst"], edge["relation"]),
                    )
                for belief in state_data.get("beliefs", []):
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO world_belief_states
                            (belief_id, entity_id, attribute, value, confidence,
                             confidence_state, source_episode_id, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (belief["belief_id"], belief["entity_id"], belief["attribute"],
                         belief["value"], belief["confidence"], belief["confidence_state"],
                         belief.get("source_episode_id"), belief["created_at"], belief["updated_at"]),
                    )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def list_snapshots(cls) -> list[dict[str, Any]]:
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                rows = conn.execute(
                    "SELECT snapshot_id, timestamp FROM world_state_snapshots ORDER BY timestamp DESC"
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    @classmethod
    def delete_snapshot(cls, snapshot_id: str) -> None:
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    "DELETE FROM world_state_snapshots WHERE snapshot_id = ?", (snapshot_id,)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    # -- state predictions ------------------------------------------------
    @classmethod
    def record_prediction(
        cls,
        prediction_id: str,
        action: str,
        predicted_success: float,
        predicted_cost: float,
        predicted_time: str,
        confidence_interval: tuple[float, float],
        risk_score: float,
    ) -> None:
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO world_state_predictions (
                        prediction_id, action, predicted_success, predicted_cost,
                        predicted_time, confidence_interval, risk_score, timestamp
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(prediction_id) DO UPDATE SET
                        action=excluded.action,
                        predicted_success=excluded.predicted_success,
                        predicted_cost=excluded.predicted_cost,
                        predicted_time=excluded.predicted_time,
                        confidence_interval=excluded.confidence_interval,
                        risk_score=excluded.risk_score,
                        timestamp=excluded.timestamp
                    """,
                    (
                        prediction_id,
                        action.upper().strip(),
                        max(0.0, min(1.0, predicted_success)),
                        max(0.0, predicted_cost),
                        predicted_time.strip(),
                        json.dumps(list(confidence_interval)),
                        max(0.0, min(1.0, risk_score)),
                        time.time(),
                    ),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_prediction(cls, prediction_id: str) -> dict[str, Any] | None:
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM world_state_predictions WHERE prediction_id = ?",
                    (prediction_id,),
                ).fetchone()
                if row:
                    return {
                        "prediction_id": row["prediction_id"],
                        "action": row["action"],
                        "predicted_success": row["predicted_success"],
                        "predicted_cost": row["predicted_cost"],
                        "predicted_time": row["predicted_time"],
                        "confidence_interval": tuple(json.loads(row["confidence_interval"])),
                        "risk_score": row["risk_score"],
                        "timestamp": row["timestamp"],
                    }
            finally:
                conn.close()
        return None

    @classmethod
    def list_predictions(cls) -> list[dict[str, Any]]:
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM world_state_predictions ORDER BY timestamp DESC"
                ).fetchall()
                return [
                    {
                        "prediction_id": r["prediction_id"],
                        "action": r["action"],
                        "predicted_success": r["predicted_success"],
                        "predicted_cost": r["predicted_cost"],
                        "predicted_time": r["predicted_time"],
                        "confidence_interval": tuple(json.loads(r["confidence_interval"])),
                        "risk_score": r["risk_score"],
                        "timestamp": r["timestamp"],
                    }
                    for r in rows
                ]
            finally:
                conn.close()
