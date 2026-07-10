"""
backend/core/memory/working_memory_store.py

Phase 1B: WorkingMemoryStore — concrete IMemoryStore implementation for MemoryType.WORKING.

This is the system's active scratchpad: the whiteboard where planners, agents,
executive controllers, and tool runners leave transient footprints before those
traces crystallize into episodic memory.

Design:
  - SQLite backend with WAL mode and NORMAL synchronization for durability + speed.
  - Instance-level RLock for thread safety (no class-level globals).
  - All records carry a TTL-derived expires_at column for lazy and active expiry.
  - Priority-based retrieval: lower integer = higher priority (0 = critical).
  - Session isolation via session_id indexing.
  - IMemoryStore compliance: save(), retrieve(), forget(), health_check().
  - Extended Working Memory API: put(), get(), delete(), expire(),
    get_active_context(), get_goal_context(), clear_session(), consolidate().

Schema columns extracted from MemoryRecord.payload (with defaults):
  session_id  <- payload.get("session_id", "default")
  goal_id     <- payload.get("goal_id", "")
  key         <- payload.get("key", "")
  priority    <- payload.get("priority", 5)  # 0=critical … 10=low
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Generator, Iterator, List, Optional

from .schemas import MemoryRecord, MemoryType, DEFAULT_TTL
from .memory_manager import IMemoryStore


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_SESSION = "default"
_DEFAULT_PRIORITY = 5          # mid-scale (0 = highest)
_CONSOLIDATE_MIN_IMPORTANCE = 0.6
_CONSOLIDATE_MIN_CONFIDENCE = 0.5


# ---------------------------------------------------------------------------
# Table / index DDL
# ---------------------------------------------------------------------------
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS working_memories (
    memory_id     TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL DEFAULT 'default',
    goal_id       TEXT NOT NULL DEFAULT '',
    key           TEXT NOT NULL DEFAULT '',
    value         TEXT NOT NULL DEFAULT '{}',
    priority      INTEGER NOT NULL DEFAULT 5,
    source_agent  TEXT NOT NULL DEFAULT '',
    confidence    REAL NOT NULL DEFAULT 1.0,
    importance    REAL NOT NULL DEFAULT 0.5,
    tags          TEXT NOT NULL DEFAULT '[]',
    embedding_id  TEXT,
    created_at    REAL NOT NULL,
    expires_at    REAL,
    last_accessed REAL NOT NULL,
    access_count  INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_wm_session  ON working_memories(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_wm_goal     ON working_memories(goal_id);",
    "CREATE INDEX IF NOT EXISTS idx_wm_expires  ON working_memories(expires_at);",
    "CREATE INDEX IF NOT EXISTS idx_wm_priority ON working_memories(priority);",
    "CREATE INDEX IF NOT EXISTS idx_wm_key      ON working_memories(key);",
]


class WorkingMemoryStore(IMemoryStore):
    """SQLite-backed IMemoryStore for MemoryType.WORKING.

    Instantiate once per process (or once per test) and register with a MemoryManager:

    .. code-block:: python

        store = WorkingMemoryStore()                # uses in-memory DB
        store = WorkingMemoryStore("/path/to/db")  # persistent DB

        manager = MemoryManager()
        manager.register(store)
    """

    # IMemoryStore contract marker
    memory_type: MemoryType = MemoryType.WORKING

    def __init__(self, db_path: str = ":memory:") -> None:
        """
        Args:
            db_path: Path to the SQLite file, or ``:memory:`` for in-process testing.
        """
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def _get_conn(self) -> sqlite3.Connection:
        """Return the shared connection, creating it on first call.

        A single shared connection is used (with check_same_thread=False)
        because concurrent access is serialized through the RLock.
        """
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
            for idx_sql in _CREATE_INDEXES:
                conn.execute(idx_sql)
            conn.commit()

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager that acquires the lock and commits or rolls back."""
        with self._lock:
            conn = self._get_conn()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def close(self) -> None:
        """Close the underlying SQLite connection. Safe to call multiple times."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _expires_at(timestamp: float) -> float:
        ttl = DEFAULT_TTL[MemoryType.WORKING]
        return timestamp + ttl  # type: ignore[operator]  # WORKING TTL is not None

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        payload = json.loads(row["value"])
        # Re-inject indexed columns into payload so callers can read them
        payload.setdefault("session_id", row["session_id"])
        payload.setdefault("goal_id", row["goal_id"])
        payload.setdefault("key", row["key"])
        payload.setdefault("priority", row["priority"])
        return MemoryRecord(
            memory_id=row["memory_id"],
            memory_type=MemoryType.WORKING,
            timestamp=row["created_at"],
            source_agent=row["source_agent"],
            confidence=row["confidence"],
            importance_score=row["importance"],
            tags=json.loads(row["tags"]),
            embedding_id=row["embedding_id"],
            payload=payload,
        )

    @staticmethod
    def _record_to_row(record: MemoryRecord) -> Dict[str, Any]:
        payload = dict(record.payload)
        return {
            "memory_id":    record.memory_id,
            "session_id":   str(payload.pop("session_id", _DEFAULT_SESSION)).strip() or _DEFAULT_SESSION,
            "goal_id":      str(payload.pop("goal_id", "")),
            "key":          str(payload.pop("key", "")),
            "priority":     int(payload.pop("priority", _DEFAULT_PRIORITY)),
            "value":        json.dumps(payload, ensure_ascii=False),
            "source_agent": record.source_agent,
            "confidence":   record.confidence,
            "importance":   record.importance_score,
            "tags":         json.dumps(record.tags, ensure_ascii=False),
            "embedding_id": record.embedding_id,
            "created_at":   record.timestamp,
            "expires_at":   WorkingMemoryStore._expires_at(record.timestamp),
            "last_accessed": record.timestamp,
            "access_count": 0,
        }

    def _prune_expired(self, conn: sqlite3.Connection) -> int:
        """Delete all records whose expires_at is in the past. Returns count deleted."""
        now = time.time()
        cur = conn.execute("DELETE FROM working_memories WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,))
        return cur.rowcount

    # ------------------------------------------------------------------
    # IMemoryStore: save
    # ------------------------------------------------------------------
    def save(self, record: MemoryRecord) -> None:
        """Insert or replace a MemoryRecord.

        Raises:
            TypeError: If record is not MemoryType.WORKING.
        """
        if not isinstance(record, MemoryRecord):
            raise TypeError(f"Expected MemoryRecord; got {type(record)!r}")
        if record.memory_type is not MemoryType.WORKING:
            raise TypeError(
                f"WorkingMemoryStore only accepts MemoryType.WORKING; "
                f"got {record.memory_type.value!r}"
            )
        row = self._record_to_row(record)
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO working_memories (
                    memory_id, session_id, goal_id, key, value, priority,
                    source_agent, confidence, importance, tags, embedding_id,
                    created_at, expires_at, last_accessed, access_count
                ) VALUES (
                    :memory_id, :session_id, :goal_id, :key, :value, :priority,
                    :source_agent, :confidence, :importance, :tags, :embedding_id,
                    :created_at, :expires_at, :last_accessed, :access_count
                )
                ON CONFLICT(memory_id) DO UPDATE SET
                    session_id    = excluded.session_id,
                    goal_id       = excluded.goal_id,
                    key           = excluded.key,
                    value         = excluded.value,
                    priority      = excluded.priority,
                    confidence    = excluded.confidence,
                    importance    = excluded.importance,
                    tags          = excluded.tags,
                    embedding_id  = excluded.embedding_id,
                    expires_at    = excluded.expires_at,
                    last_accessed = excluded.last_accessed
                """,
                row,
            )

    # ------------------------------------------------------------------
    # IMemoryStore: retrieve
    # ------------------------------------------------------------------
    def retrieve(self, query: Dict[str, Any], limit: int = 20) -> List[MemoryRecord]:
        """Query working memory records.

        Supported filter keys:
            session_id     str   — exact match
            goal_id        str   — exact match
            key            str   — exact match
            source_agent   str   — exact match
            min_importance float — lower bound on importance
            min_confidence float — lower bound on confidence
            priority_max   int   — upper bound on priority integer (inclusive)
            since          float — Unix epoch lower bound on created_at
            until          float — Unix epoch upper bound on created_at
            tags           list  — any-match on stored tags JSON
            include_expired bool — if True, skip expiry filtering (default False)

        Returns:
            Matching records, ordered by priority ASC then created_at DESC (newest first).
        """
        conditions: List[str] = []
        params: List[Any] = []

        if not query.get("include_expired"):
            conditions.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(time.time())

        for col in ("session_id", "goal_id", "key", "source_agent"):
            if col in query:
                conditions.append(f"{col} = ?")
                params.append(query[col])

        if "min_importance" in query:
            conditions.append("importance >= ?")
            params.append(float(query["min_importance"]))

        if "min_confidence" in query:
            conditions.append("confidence >= ?")
            params.append(float(query["min_confidence"]))

        if "priority_max" in query:
            conditions.append("priority <= ?")
            params.append(int(query["priority_max"]))

        if "since" in query:
            conditions.append("created_at >= ?")
            params.append(float(query["since"]))

        if "until" in query:
            conditions.append("created_at <= ?")
            params.append(float(query["until"]))

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT * FROM working_memories
            {where}
            ORDER BY priority ASC, created_at DESC
            LIMIT ?
        """
        params.append(limit)

        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(sql, params).fetchall()
            # Bump access counters in a single batch
            if rows:
                ids = [r["memory_id"] for r in rows]
                ph = ",".join("?" for _ in ids)
                now = time.time()
                conn.execute(
                    f"UPDATE working_memories SET last_accessed=?, access_count=access_count+1 WHERE memory_id IN ({ph})",
                    [now, *ids],
                )
                conn.commit()

        return [self._row_to_record(r) for r in rows]

    # ------------------------------------------------------------------
    # IMemoryStore: forget
    # ------------------------------------------------------------------
    def forget(self, retention_threshold: float = 0.0) -> int:
        """Prune expired records and records whose retention_score <= threshold.

        Since computing Python-side retention_score requires loading every row,
        this method:
          1. Always deletes all expired (past expires_at) records.
          2. If threshold > 0, additionally deletes records with low
             importance × confidence product (a storage-efficient proxy).

        Args:
            retention_threshold: Records with proxy score <= threshold are removed.

        Returns:
            Total number of records deleted.
        """
        with self._tx() as conn:
            deleted = self._prune_expired(conn)

            if retention_threshold > 0.0:
                # Proxy: importance × confidence ≤ threshold (ignores recency,
                # conservative — errs toward keeping rather than over-deleting)
                cur = conn.execute(
                    "DELETE FROM working_memories WHERE (importance * confidence) <= ?",
                    (retention_threshold,),
                )
                deleted += cur.rowcount

        return deleted

    # ------------------------------------------------------------------
    # IMemoryStore: health_check
    # ------------------------------------------------------------------
    def health_check(self) -> Dict[str, Any]:
        with self._lock:
            conn = self._get_conn()
            now = time.time()
            row = conn.execute(
                "SELECT COUNT(*) AS total, "
                "COALESCE(SUM(CASE WHEN expires_at IS NOT NULL AND expires_at <= ? THEN 1 ELSE 0 END), 0) AS expired "
                "FROM working_memories",
                (now,),
            ).fetchone()
        return {
            "status": "ok",
            "memory_type": MemoryType.WORKING.value,
            "total_records": row["total"],
            "expired_records": row["expired"],
            "db_path": self._db_path,
        }

    # ------------------------------------------------------------------
    # Extended Working Memory API
    # ------------------------------------------------------------------
    def put(
        self,
        payload: Dict[str, Any],
        *,
        session_id: str = _DEFAULT_SESSION,
        goal_id: str = "",
        key: str = "",
        priority: int = _DEFAULT_PRIORITY,
        source_agent: str = "system",
        importance_score: float = 0.5,
        confidence: float = 1.0,
        tags: Optional[List[str]] = None,
        memory_id: Optional[str] = None,
    ) -> str:
        """Convenience wrapper: create and save a working memory record.

        Returns the memory_id of the saved record.
        """
        full_payload = dict(payload)
        full_payload["session_id"] = session_id
        full_payload["goal_id"] = goal_id
        full_payload["key"] = key
        full_payload["priority"] = priority

        record = MemoryRecord(
            memory_id=memory_id or str(uuid.uuid4()),
            memory_type=MemoryType.WORKING,
            source_agent=source_agent,
            payload=full_payload,
            importance_score=importance_score,
            confidence=confidence,
            tags=tags or [],
        )
        self.save(record)
        return record.memory_id

    def get(self, memory_id: str) -> Optional[MemoryRecord]:
        """Retrieve a single record by its memory_id (None if expired or missing)."""
        with self._lock:
            conn = self._get_conn()
            now = time.time()
            row = conn.execute(
                "SELECT * FROM working_memories "
                "WHERE memory_id = ? AND (expires_at IS NULL OR expires_at > ?)",
                (memory_id, now),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE working_memories SET last_accessed=?, access_count=access_count+1 WHERE memory_id=?",
                (now, memory_id),
            )
            conn.commit()
        return self._row_to_record(row)

    def delete(self, memory_id: str) -> bool:
        """Hard-delete a record by its memory_id. Returns True if a row was removed."""
        with self._tx() as conn:
            cur = conn.execute("DELETE FROM working_memories WHERE memory_id = ?", (memory_id,))
            return cur.rowcount > 0

    def expire(self, memory_id: str) -> bool:
        """Manually mark a record as expired (sets expires_at to now).

        The record remains queryable via ``include_expired=True`` until the
        next ``forget()`` call physically removes it.

        Returns True if the record was found and updated.
        """
        with self._tx() as conn:
            cur = conn.execute(
                "UPDATE working_memories SET expires_at = ? WHERE memory_id = ?",
                (time.time(), memory_id),
            )
            return cur.rowcount > 0

    def get_active_context(
        self,
        session_id: str,
        priority_max: int = 10,
        limit: int = 50,
    ) -> List[MemoryRecord]:
        """Return all non-expired records for a session, ordered by priority then recency."""
        return self.retrieve(
            {"session_id": session_id, "priority_max": priority_max},
            limit=limit,
        )

    def get_goal_context(self, goal_id: str, limit: int = 30) -> List[MemoryRecord]:
        """Return all non-expired records associated with a specific goal."""
        return self.retrieve({"goal_id": goal_id}, limit=limit)

    def clear_session(self, session_id: str) -> int:
        """Hard-delete all working memory records for a session.

        Returns:
            Number of records deleted.
        """
        with self._tx() as conn:
            cur = conn.execute(
                "DELETE FROM working_memories WHERE session_id = ?", (session_id,)
            )
            return cur.rowcount

    def consolidate(
        self,
        session_id: str = _DEFAULT_SESSION,
        min_importance: float = _CONSOLIDATE_MIN_IMPORTANCE,
        min_confidence: float = _CONSOLIDATE_MIN_CONFIDENCE,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        """Return records that are mature enough to be promoted to episodic memory.

        Selection criteria:
          - Belongs to the given session.
          - Not yet expired.
          - importance_score >= min_importance AND confidence >= min_confidence.
          - Ordered by importance DESC, confidence DESC.

        The caller (typically the ConsolidationEngine) is responsible for:
          1. Writing the returned records to EpisodicMemoryStore.
          2. Calling clear_session() or delete() to retire them from working memory.

        Returns:
            List of MemoryRecord instances ready for promotion.
        """
        with self._lock:
            conn = self._get_conn()
            now = time.time()
            rows = conn.execute(
                """
                SELECT * FROM working_memories
                WHERE session_id = ?
                  AND (expires_at IS NULL OR expires_at > ?)
                  AND importance >= ?
                  AND confidence >= ?
                ORDER BY importance DESC, confidence DESC
                LIMIT ?
                """,
                (session_id, now, min_importance, min_confidence, limit),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def __repr__(self) -> str:
        return f"WorkingMemoryStore(db={self._db_path!r})"
