"""
backend/core/memory/episodic_memory_store.py

Phase 1C: EpisodicMemoryStore — concrete IMemoryStore implementation for MemoryType.EPISODIC.

Provides a permanent narrative memory log of agent experiences:
  - SQLite backend for metadata and content.
  - FTS5 virtual table for lexical searches.
  - Thread-safe RLock access.
  - EventBus-driven asynchronous embedding updates (loosely coupled).
  - Reciprocal Rank Fusion (RRF) hybrid search merging FTS5 and ChromaDB.
  - Graceful degradation: falls back to FTS5 lexical search if ChromaDB is missing.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Tuple

from .schemas import MemoryRecord, MemoryType, DEFAULT_TTL
from .memory_manager import IMemoryStore
from backend.core.event_bus import EventBus, Event


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_SESSION = "default"
_EVENT_NAME_EPISODE_CREATED = "EpisodeCreated"

# FTS5 tables & Triggers DDL
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS episodic_memories (
    memory_id           TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL DEFAULT 'default',
    goal_id             TEXT NOT NULL DEFAULT '',
    episode_type        TEXT NOT NULL DEFAULT 'general',
    outcome             TEXT NOT NULL DEFAULT 'unknown',
    consolidation_state TEXT NOT NULL DEFAULT 'ACTIVE',
    title               TEXT NOT NULL DEFAULT '',
    content             TEXT NOT NULL DEFAULT '',
    value               TEXT NOT NULL DEFAULT '{}',
    source_agent        TEXT NOT NULL DEFAULT '',
    confidence          REAL NOT NULL DEFAULT 1.0,
    importance          REAL NOT NULL DEFAULT 0.5,
    tags                TEXT NOT NULL DEFAULT '[]',
    embedding_id        TEXT,
    created_at          REAL NOT NULL,
    expires_at          REAL,
    last_accessed       REAL NOT NULL,
    access_count        INTEGER NOT NULL DEFAULT 0
);
"""
# ... (rest remains unchanged)

# ... (rest remains unchanged)


_CREATE_FTS_VIRTUAL = """
CREATE VIRTUAL TABLE IF NOT EXISTS episodic_memories_fts USING fts5(
    title,
    content,
    content='episodic_memories'
);
"""

_TRIGGERS = [
    # After Insert Sync FTS
    """
    CREATE TRIGGER IF NOT EXISTS trg_episodic_memories_ai AFTER INSERT ON episodic_memories BEGIN
        INSERT INTO episodic_memories_fts(rowid, title, content)
        VALUES (new.rowid, new.title, new.content);
    END;
    """,
    # After Delete Sync FTS
    """
    CREATE TRIGGER IF NOT EXISTS trg_episodic_memories_ad AFTER DELETE ON episodic_memories BEGIN
        INSERT INTO episodic_memories_fts(episodic_memories_fts, rowid, title, content)
        VALUES ('delete', old.rowid, old.title, old.content);
    END;
    """,
    # After Update Sync FTS
    """
    CREATE TRIGGER IF NOT EXISTS trg_episodic_memories_au AFTER UPDATE OF title, content ON episodic_memories BEGIN
        INSERT INTO episodic_memories_fts(episodic_memories_fts, rowid, title, content)
        VALUES ('delete', old.rowid, old.title, old.content);
        INSERT INTO episodic_memories_fts(rowid, title, content)
        VALUES (new.rowid, new.title, new.content);
    END;
    """
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_em_session ON episodic_memories(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_em_goal ON episodic_memories(goal_id);",
    "CREATE INDEX IF NOT EXISTS idx_em_expires ON episodic_memories(expires_at);",
    "CREATE INDEX IF NOT EXISTS idx_em_type ON episodic_memories(episode_type);",
    "CREATE INDEX IF NOT EXISTS idx_em_outcome ON episodic_memories(outcome);",
    "CREATE INDEX IF NOT EXISTS idx_em_consolidation ON episodic_memories(consolidation_state);",
]


class EpisodicMemoryStore(IMemoryStore):
    """SQLite + FTS5 + ChromaDB backed episodic memory store."""

    memory_type: MemoryType = MemoryType.EPISODIC

    def __init__(
        self,
        db_path: str = ":memory:",
        chroma_path: Optional[str] = None,
        collection_name: str = "episodic_memory_store_vectors",
    ) -> None:
        """
        Args:
            db_path: SQLite DB path (or ':memory:')
            chroma_path: ChromaDB persistent directory path (optional)
            collection_name: Vector collection name
        """
        self._db_path = db_path
        self._chroma_path = chroma_path
        self._collection_name = collection_name
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None

        # ChromaDB lazily loaded client & collection
        self._chroma_client: Any = None
        self._collection: Any = None
        self._chroma_available = True

        self._closed = False
        self._init_db()
        self._setup_event_listener()

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
            self._closed = True
            try:
                EventBus.unsubscribe(_EVENT_NAME_EPISODE_CREATED, self._handle_episode_created)
            except Exception:
                pass
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ------------------------------------------------------------------
    # ChromaDB integration
    # ------------------------------------------------------------------
    def _get_chroma_collection(self) -> Optional[Any]:
        if not self._chroma_available:
            return None
        if self._collection is not None:
            return self._collection

        if self._chroma_path is None:
            from backend.core.config import load_config
            try:
                config = load_config()
                self._chroma_path = str(config.chroma_path)
            except Exception:
                self._chroma_path = None

        if self._chroma_path is None:
            self._chroma_available = False
            return None

        try:
            import chromadb
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
            from pathlib import Path

            Path(self._chroma_path).mkdir(parents=True, exist_ok=True)
            self._chroma_client = chromadb.PersistentClient(
                path=self._chroma_path,
                settings=chromadb.config.Settings(anonymized_telemetry=False)
            )
            self._collection = self._chroma_client.get_or_create_collection(
                name=self._collection_name,
                embedding_function=DefaultEmbeddingFunction()
            )
            return self._collection
        except Exception as e:
            # Degrade gracefully
            from backend.core.logger import log_event
            log_event(f"EpisodicMemoryStore: ChromaDB init failed (falling back to FTS5): {e}")
            self._chroma_available = False
            return None

    # ------------------------------------------------------------------
    # EventBus Listener (Asynchronous indexing)
    # ------------------------------------------------------------------
    def _setup_event_listener(self) -> None:
        # Subscribe to EpisodeCreated event
        EventBus.subscribe(_EVENT_NAME_EPISODE_CREATED, self._handle_episode_created)

    def _handle_episode_created(self, event: Event) -> None:
        if self._closed:
            return
        payload = event.payload
        memory_id = payload.get("memory_id")
        content = payload.get("content", "")
        store_db_path = payload.get("store_db_path")

        # Session/instance filtering: only index if it matches our DB path
        if not memory_id or store_db_path != self._db_path:
            return

        collection = self._get_chroma_collection()
        if collection is None:
            return

        try:
            # 1. Upsert vector to Chroma
            collection.add(ids=[memory_id], documents=[content])

            # 2. Update sqlite to set embedding_id
            with self._tx() as conn:
                conn.execute(
                    "UPDATE episodic_memories SET embedding_id = ? WHERE memory_id = ?",
                    (memory_id, memory_id)
                )
        except Exception as e:
            from backend.core.logger import log_event
            log_event(f"EpisodicMemoryStore: Async embedding failed for {memory_id}: {e}")

    # ------------------------------------------------------------------
    # Conversion Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _expires_at(timestamp: float) -> Optional[float]:
        ttl = DEFAULT_TTL[MemoryType.EPISODIC]
        return timestamp + ttl if ttl is not None else None

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        payload = json.loads(row["value"])
        # Re-inject indexed columns into payload so callers can read them
        payload.setdefault("session_id", row["session_id"])
        payload.setdefault("goal_id", row["goal_id"])
        payload.setdefault("episode_type", row["episode_type"])
        payload.setdefault("outcome", row["outcome"])
        payload.setdefault("consolidation_state", row["consolidation_state"])
        payload.setdefault("title", row["title"])
        payload.setdefault("content", row["content"])
        return MemoryRecord(
            memory_id=row["memory_id"],
            memory_type=MemoryType.EPISODIC,
            timestamp=row["created_at"],
            source_agent=row["source_agent"],
            confidence=row["confidence"],
            importance_score=row["importance"],
            tags=json.loads(row["tags"]),
            embedding_id=row["embedding_id"],
            payload=payload,
        )

    def _record_to_row(self, record: MemoryRecord) -> Dict[str, Any]:
        payload = dict(record.payload)
        session_id = str(payload.pop("session_id", _DEFAULT_SESSION)).strip() or _DEFAULT_SESSION
        goal_id = str(payload.pop("goal_id", ""))
        episode_type = str(payload.pop("episode_type", "general"))
        outcome = str(payload.pop("outcome", "unknown"))
        consolidation_state = str(payload.pop("consolidation_state", "ACTIVE"))
        title = str(payload.pop("title", ""))

        # Ensure content is extracted
        content = payload.pop("content", None) or payload.pop("text", None) or title
        if not content:
            content = title or ""

        return {
            "memory_id":           record.memory_id,
            "session_id":          session_id,
            "goal_id":             goal_id,
            "episode_type":        episode_type,
            "outcome":             outcome,
            "consolidation_state": consolidation_state,
            "title":               title,
            "content":             content,
            "value":               json.dumps(payload, ensure_ascii=False),
            "source_agent":        record.source_agent,
            "confidence":          record.confidence,
            "importance":          record.importance_score,
            "tags":                json.dumps(record.tags, ensure_ascii=False),
            "embedding_id":        record.embedding_id,
            "created_at":          record.timestamp,
            "expires_at":          self._expires_at(record.timestamp),
            "last_accessed":       record.timestamp,
            "access_count":        0,
        }

    # ------------------------------------------------------------------
    # IMemoryStore: save
    # ------------------------------------------------------------------
    def save(self, record: MemoryRecord) -> None:
        if not isinstance(record, MemoryRecord):
            raise TypeError(f"Expected MemoryRecord; got {type(record)!r}")
        if record.memory_type is not MemoryType.EPISODIC:
            raise TypeError(
                f"EpisodicMemoryStore only accepts MemoryType.EPISODIC; "
                f"got {record.memory_type.value!r}"
            )
        row = self._record_to_row(record)
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO episodic_memories (
                    memory_id, session_id, goal_id, episode_type, outcome, consolidation_state,
                    title, content, value, source_agent, confidence, importance, tags, embedding_id,
                    created_at, expires_at, last_accessed, access_count
                ) VALUES (
                    :memory_id, :session_id, :goal_id, :episode_type, :outcome, :consolidation_state,
                    :title, :content, :value, :source_agent, :confidence, :importance, :tags, :embedding_id,
                    :created_at, :expires_at, :last_accessed, :access_count
                )
                ON CONFLICT(memory_id) DO UPDATE SET
                    session_id          = excluded.session_id,
                    goal_id             = excluded.goal_id,
                    episode_type        = excluded.episode_type,
                    outcome             = excluded.outcome,
                    consolidation_state = excluded.consolidation_state,
                    title               = excluded.title,
                    content             = excluded.content,
                    value               = excluded.value,
                    confidence          = excluded.confidence,
                    importance          = excluded.importance,
                    tags                = excluded.tags,
                    embedding_id        = excluded.embedding_id,
                    expires_at          = excluded.expires_at,
                    last_accessed       = excluded.last_accessed
                """,
                row,
            )

        # Trigger async embedding via EventBus
        EventBus.publish(
            _EVENT_NAME_EPISODE_CREATED,
            {
                "memory_id": record.memory_id,
                "content": row["content"],
                "store_db_path": self._db_path,
            },
            source="EpisodicMemoryStore",
        )

    # ------------------------------------------------------------------
    # IMemoryStore: retrieve & Hybrid Search
    # ------------------------------------------------------------------
    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        words = re.findall(r"\w+", query)
        if not words:
            return ""
        return " AND ".join(f'"{w}"*' for w in words)

    def retrieve(self, query: Dict[str, Any], limit: int = 20) -> List[MemoryRecord]:
        text_query = query.get("text") or query.get("query")
        if text_query:
            return self._retrieve_hybrid(query, text_query, limit)
        return self._retrieve_standard(query, limit)

    def _retrieve_standard(self, query: Dict[str, Any], limit: int = 20) -> List[MemoryRecord]:
        conditions, params = self._build_where_clause(query)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT * FROM episodic_memories
            {where}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)

        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(sql, params).fetchall()
            self._bump_access(conn, [r["memory_id"] for r in rows])

        return [self._row_to_record(r) for r in rows]

    def _retrieve_hybrid(self, query: Dict[str, Any], text_query: str, limit: int = 20) -> List[MemoryRecord]:
        # 1. Lexical retrieval via FTS5
        sanitized = self._sanitize_fts_query(text_query)
        fts_ids: List[str] = []
        if sanitized:
            with self._lock:
                conn = self._get_conn()
                try:
                    rows = conn.execute(
                        """
                        SELECT memory_id FROM episodic_memories
                        JOIN episodic_memories_fts f ON f.rowid = episodic_memories.rowid
                        WHERE f.episodic_memories_fts MATCH ?
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (sanitized, limit * 2)
                    ).fetchall()
                    fts_ids = [r["memory_id"] for r in rows]
                except Exception as e:
                    from backend.core.logger import log_event
                    log_event(f"EpisodicMemoryStore: FTS5 MATCH failed: {e}")

        # 2. Vector retrieval via ChromaDB
        vec_ids: List[str] = []
        collection = self._get_chroma_collection()
        if collection is not None:
            try:
                res = collection.query(query_texts=[text_query], n_results=limit * 2)
                if res and "ids" in res and res["ids"]:
                    vec_ids = res["ids"][0]
            except Exception as e:
                from backend.core.logger import log_event
                log_event(f"EpisodicMemoryStore: ChromaDB query failed: {e}")

        # 3. Reciprocal Rank Fusion (RRF) Merge
        rrf_scores: Dict[str, float] = {}
        for rank, mid in enumerate(fts_ids):
            rrf_scores[mid] = rrf_scores.get(mid, 0.0) + (1.0 / (60.0 + rank))
        for rank, mid in enumerate(vec_ids):
            rrf_scores[mid] = rrf_scores.get(mid, 0.0) + (1.0 / (60.0 + rank))

        merged_ids = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)[:limit]
        if not merged_ids:
            return []

        # Hydrate matching records
        placeholders = ",".join("?" for _ in merged_ids)
        conditions, params = self._build_where_clause(query)
        # Skip empty matching ids
        conditions.append(f"memory_id IN ({placeholders})")
        params.extend(merged_ids)

        where = "WHERE " + " AND ".join(conditions)
        sql = f"SELECT * FROM episodic_memories {where}"

        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(sql, params).fetchall()
            self._bump_access(conn, [r["memory_id"] for r in rows])

        # Restore RRF sort order
        row_map = {r["memory_id"]: r for r in rows}
        sorted_rows = [row_map[mid] for mid in merged_ids if mid in row_map]

        return [self._row_to_record(r) for r in sorted_rows]

    def _build_where_clause(self, query: Dict[str, Any]) -> Tuple[List[str], List[Any]]:
        conditions: List[str] = []
        params: List[Any] = []

        if not query.get("include_expired"):
            conditions.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(time.time())

        for col in ("session_id", "goal_id", "episode_type", "outcome", "source_agent", "consolidation_state"):
            if col in query:
                conditions.append(f"{col} = ?")
                params.append(query[col])

        if "min_importance" in query:
            conditions.append("importance >= ?")
            params.append(float(query["min_importance"]))

        if "min_confidence" in query:
            conditions.append("confidence >= ?")
            params.append(float(query["min_confidence"]))

        if "since" in query:
            conditions.append("created_at >= ?")
            params.append(float(query["since"]))

        if "until" in query:
            conditions.append("created_at <= ?")
            params.append(float(query["until"]))

        return conditions, params

    def _bump_access(self, conn: sqlite3.Connection, ids: List[str]) -> None:
        if not ids:
            return
        ph = ",".join("?" for _ in ids)
        now = time.time()
        conn.execute(
            f"UPDATE episodic_memories SET last_accessed = ?, access_count = access_count + 1 "
            f"WHERE memory_id IN ({ph})",
            [now, *ids]
        )
        conn.commit()

    # ------------------------------------------------------------------
    # IMemoryStore: forget
    # ------------------------------------------------------------------
    def forget(self, retention_threshold: float = 0.0) -> int:
        deleted = 0
        with self._tx() as conn:
            # 1. Prune TTL expired records
            now = time.time()
            cur = conn.execute("DELETE FROM episodic_memories WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,))
            deleted += cur.rowcount

            # 2. Prune low retention proxy score
            if retention_threshold > 0.0:
                cur = conn.execute(
                    "DELETE FROM episodic_memories WHERE (importance * confidence) <= ?",
                    (retention_threshold,)
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
                "FROM episodic_memories",
                (now,),
            ).fetchone()
        return {
            "status": "ok",
            "memory_type": MemoryType.EPISODIC.value,
            "total_records": row["total"],
            "expired_records": row["expired"],
            "db_path": self._db_path,
            "chroma_available": self._chroma_available,
        }

    # ------------------------------------------------------------------
    # Episodic-Specific APIs
    # ------------------------------------------------------------------
    def delete(self, memory_id: str) -> bool:
        """Hard delete a record from SQLite and ChromaDB."""
        with self._tx() as conn:
            cur = conn.execute("DELETE FROM episodic_memories WHERE memory_id = ?", (memory_id,))
            sqlite_deleted = cur.rowcount > 0

        # Sync deletion to Chroma
        collection = self._get_chroma_collection()
        if collection is not None and sqlite_deleted:
            try:
                collection.delete(ids=[memory_id])
            except Exception:
                pass

        return sqlite_deleted

    def get(self, memory_id: str) -> Optional[MemoryRecord]:
        with self._lock:
            conn = self._get_conn()
            now = time.time()
            row = conn.execute(
                "SELECT * FROM episodic_memories WHERE memory_id = ? AND (expires_at IS NULL OR expires_at > ?)",
                (memory_id, now)
            ).fetchone()
            if row is not None:
                self._bump_access(conn, [memory_id])
                return self._row_to_record(row)
        return None

    def get_by_session(self, session_id: str, limit: int = 50) -> List[MemoryRecord]:
        return self.retrieve({"session_id": session_id}, limit=limit)

    def get_by_goal(self, goal_id: str, limit: int = 50) -> List[MemoryRecord]:
        return self.retrieve({"goal_id": goal_id}, limit=limit)

    def get_by_type(self, episode_type: str, limit: int = 50) -> List[MemoryRecord]:
        return self.retrieve({"episode_type": episode_type}, limit=limit)

    def __repr__(self) -> str:
        return f"EpisodicMemoryStore(db={self._db_path!r})"
