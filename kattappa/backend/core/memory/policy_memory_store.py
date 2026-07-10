"""
backend/core/memory/policy_memory_store.py

Phase 3B: PolicyMemoryStore — Concrete IMemoryStore implementation for MemoryType.POLICY.

Provides storage for permanent safety, alignment, guardrails, and compliance rules:
  - SQLite backend with WAL mode.
  - FTS5 virtual table for lexical searches.
  - Thread-safe RLock access.
  - Protected from memory decay/forgetting (forget returns 0).
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Tuple

from .schemas import MemoryRecord, MemoryType
from .memory_manager import IMemoryStore


# FTS5 tables & Triggers DDL
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS policy_memories (
    memory_id     TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL DEFAULT 'default',
    goal_id       TEXT NOT NULL DEFAULT '',
    rule_name     TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    value         TEXT NOT NULL DEFAULT '{}',
    source_agent  TEXT NOT NULL DEFAULT '',
    priority      REAL NOT NULL DEFAULT 1.0,
    active        INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    last_accessed REAL NOT NULL,
    access_count  INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_FTS_VIRTUAL = """
CREATE VIRTUAL TABLE IF NOT EXISTS policy_memories_fts USING fts5(
    rule_name,
    description,
    content='policy_memories'
);
"""

_TRIGGERS = [
    # After Insert Sync FTS
    """
    CREATE TRIGGER IF NOT EXISTS trg_policy_memories_ai AFTER INSERT ON policy_memories BEGIN
        INSERT INTO policy_memories_fts(rowid, rule_name, description)
        VALUES (new.rowid, new.rule_name, new.description);
    END;
    """,
    # After Delete Sync FTS
    """
    CREATE TRIGGER IF NOT EXISTS trg_policy_memories_ad AFTER DELETE ON policy_memories BEGIN
        INSERT INTO policy_memories_fts(policy_memories_fts, rowid, rule_name, description)
        VALUES ('delete', old.rowid, old.rule_name, old.description);
    END;
    """,
    # After Update Sync FTS
    """
    CREATE TRIGGER IF NOT EXISTS trg_policy_memories_au AFTER UPDATE OF rule_name, description ON policy_memories BEGIN
        INSERT INTO policy_memories_fts(policy_memories_fts, rowid, rule_name, description)
        VALUES ('delete', old.rowid, old.rule_name, old.description);
        INSERT INTO policy_memories_fts(rowid, rule_name, description)
        VALUES (new.rowid, new.rule_name, new.description);
    END;
    """
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_pm_session ON policy_memories(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_pm_active ON policy_memories(active);",
]


class PolicyMemoryStore(IMemoryStore):
    """SQLite + FTS5 backed policy memory store."""

    memory_type: MemoryType = MemoryType.POLICY

    def __init__(self, db_path: str = ":memory:") -> None:
        """
        Args:
            db_path: SQLite DB path (or ':memory:')
        """
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._conn = conn
        return self._conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.execute(_CREATE_TABLE)
            conn.execute(_CREATE_FTS_VIRTUAL)
            for trigger_sql in _TRIGGERS:
                conn.execute(trigger_sql)
            for idx_sql in _INDEXES:
                conn.execute(idx_sql)
            conn.commit()

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Connection, None, None]:
        with self._lock:
            conn = self._get_conn()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ------------------------------------------------------------------
    # Conversion Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        payload = json.loads(row["value"])
        payload.setdefault("session_id", row["session_id"])
        payload.setdefault("goal_id", row["goal_id"])
        payload.setdefault("rule_name", row["rule_name"])
        payload.setdefault("description", row["description"])
        payload.setdefault("active", bool(row["active"]))
        payload.setdefault("priority", row["priority"])

        return MemoryRecord(
            memory_id=row["memory_id"],
            memory_type=MemoryType.POLICY,
            timestamp=row["created_at"],
            source_agent=row["source_agent"],
            confidence=1.0,
            importance_score=1.0,
            tags=[],
            payload=payload,
        )

    def _record_to_row(self, record: MemoryRecord) -> Dict[str, Any]:
        payload = dict(record.payload)
        session_id = str(payload.pop("session_id", "default")).strip()
        goal_id = str(payload.pop("goal_id", ""))
        rule_name = str(payload.pop("rule_name") or payload.get("title") or "").strip()
        description = str(payload.pop("description") or payload.get("content") or "").strip()
        active = 1 if payload.pop("active", True) else 0
        priority = float(payload.pop("priority", 1.0))

        return {
            "memory_id":    record.memory_id,
            "session_id":   session_id,
            "goal_id":      goal_id,
            "rule_name":    rule_name,
            "description":  description,
            "value":        json.dumps(payload, ensure_ascii=False),
            "source_agent": record.source_agent,
            "priority":     priority,
            "active":       active,
            "created_at":   record.timestamp,
            "updated_at":   time.time(),
            "last_accessed": record.timestamp,
        }

    # ------------------------------------------------------------------
    # IMemoryStore: save
    # ------------------------------------------------------------------
    def save(self, record: MemoryRecord) -> None:
        if not isinstance(record, MemoryRecord):
            raise TypeError(f"Expected MemoryRecord; got {type(record)!r}")
        if record.memory_type is not MemoryType.POLICY:
            raise TypeError(
                f"PolicyMemoryStore only accepts MemoryType.POLICY; "
                f"got {record.memory_type.value!r}"
            )
        row = self._record_to_row(record)
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO policy_memories (
                    memory_id, session_id, goal_id, rule_name, description, value,
                    source_agent, priority, active, created_at, updated_at, last_accessed
                ) VALUES (
                    :memory_id, :session_id, :goal_id, :rule_name, :description, :value,
                    :source_agent, :priority, :active, :created_at, :updated_at, :last_accessed
                )
                ON CONFLICT(memory_id) DO UPDATE SET
                    session_id    = excluded.session_id,
                    goal_id       = excluded.goal_id,
                    rule_name     = excluded.rule_name,
                    description   = excluded.description,
                    value         = excluded.value,
                    priority      = excluded.priority,
                    active        = excluded.active,
                    updated_at    = excluded.updated_at,
                    last_accessed = excluded.last_accessed
                """,
                row,
            )

    # ------------------------------------------------------------------
    # IMemoryStore: retrieve
    # ------------------------------------------------------------------
    def retrieve(self, query: Dict[str, Any], limit: int = 20) -> List[MemoryRecord]:
        text_query = query.get("text") or query.get("query")
        conditions: List[str] = []
        params: List[Any] = []

        for col in ("session_id", "goal_id", "active"):
            if col in query:
                conditions.append(f"{col} = ?")
                val = query[col]
                if col == "active":
                    val = 1 if val else 0
                params.append(val)

        if text_query:
            sanitized = self._sanitize_fts_query(text_query)
            if sanitized:
                conditions.append("rowid IN (SELECT rowid FROM policy_memories_fts WHERE policy_memories_fts MATCH ?)")
                params.append(sanitized)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT * FROM policy_memories
            {where}
            ORDER BY priority DESC, created_at DESC
            LIMIT ?
        """
        params.append(limit)

        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(sql, params).fetchall()
            self._bump_access(conn, [r["memory_id"] for r in rows])

        return [self._row_to_record(r) for r in rows]

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        words = [w for w in re.findall(r"\w+", query) if w]
        if not words:
            return ""
        return " AND ".join(f'"{w}"*' for w in words)

    def _bump_access(self, conn: sqlite3.Connection, ids: List[str]) -> None:
        if not ids:
            return
        ph = ",".join("?" for _ in ids)
        now = time.time()
        conn.execute(
            f"UPDATE policy_memories SET last_accessed = ?, access_count = access_count + 1 "
            f"WHERE memory_id IN ({ph})",
            [now, *ids]
        )
        conn.commit()

    # ------------------------------------------------------------------
    # IMemoryStore: forget
    # ------------------------------------------------------------------
    def forget(self, retention_threshold: float = 0.0) -> int:
        # Policy rules represent permanent compliance and safety guardrails,
        # which are exempt from memory decay/forgetting processes.
        return 0

    # ------------------------------------------------------------------
    # IMemoryStore: health_check
    # ------------------------------------------------------------------
    def health_check(self) -> Dict[str, Any]:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT COUNT(*) AS total, "
                "COALESCE(SUM(CASE WHEN active = 1 THEN 1 ELSE 0 END), 0) AS active "
                "FROM policy_memories"
            ).fetchone()
        return {
            "status": "ok",
            "memory_type": MemoryType.POLICY.value,
            "total_policies": row["total"],
            "active_policies": row["active"],
        }

    # ------------------------------------------------------------------
    # Policy-Specific APIs
    # ------------------------------------------------------------------
    def delete(self, memory_id: str) -> bool:
        with self._tx() as conn:
            cur = conn.execute("DELETE FROM policy_memories WHERE memory_id = ?", (memory_id,))
            deleted = cur.rowcount > 0
        return deleted

    def get(self, memory_id: str) -> Optional[MemoryRecord]:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute("SELECT * FROM policy_memories WHERE memory_id = ?", (memory_id,)).fetchone()
            if row is not None:
                self._bump_access(conn, [memory_id])
                return self._row_to_record(row)
        return None

    def deactivate(self, memory_id: str) -> bool:
        with self._tx() as conn:
            cur = conn.execute("UPDATE policy_memories SET active = 0, updated_at = ? WHERE memory_id = ?", (time.time(), memory_id))
            updated = cur.rowcount > 0
        return updated

    def __repr__(self) -> str:
        return f"PolicyMemoryStore(db={self._db_path!r})"
