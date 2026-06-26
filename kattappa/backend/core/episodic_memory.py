"""Episodic Memory Subsystem (Layer 3 - Spec v2.0).

Authoritative storage is in SQLite with dynamic, read-only query-time strength calculations.
Vector search uses ChromaDB for semantic retrieval.
Features:
- Verbatim trace and Gist separation.
- Source reality tags (DID, READ, HEARD, SIMULATED, INFERRED).
- Relevance floor firewall.
- Access-log based reinforcement (no overwrites to event records on query).
- Zeigarnik effect (boost for unresolved OPEN episodes).
- Exponential decay combined with interference checks.
"""

from __future__ import annotations

import json
import math
import queue
import re
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from backend.core.config import load_config
from backend.core.logger import log_event


class EpisodicMemory:
    """Episodic Memory Subsystem representing the chronological autobiographical narrative of experiences."""
    
    _lock = threading.RLock()
    _embed_queue: queue.Queue[Tuple[str, str]] = queue.Queue()
    _worker_thread: threading.Thread | None = None
    _gc_thread: threading.Thread | None = None
    _stop_event = threading.Event()
    _chroma_client: Any | None = None
    _collection: Any | None = None
    _query_cache: dict[str, Any] = {}
    _emb_fn: Any | None = None
    _schema_ensured = False

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        with cls._lock:
            if not cls._schema_ensured:
                cls._ensure_schema(conn)
                cls._schema_ensured = True
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            # 1. Legacy tables & FTS5 (for full backward compatibility)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS hm_episodes (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL NOT NULL,
                    category TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_recalled_at REAL NOT NULL,
                    recall_count INTEGER DEFAULT 0,
                    pinned INTEGER DEFAULT 0,
                    tags TEXT DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS idx_hm_episodes_session ON hm_episodes(session_id);
                CREATE INDEX IF NOT EXISTS idx_hm_episodes_category ON hm_episodes(category);

                CREATE TABLE IF NOT EXISTS hm_episodes_archive (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL NOT NULL,
                    category TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    archived_at REAL NOT NULL,
                    tags TEXT DEFAULT '[]'
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS hm_episodes_fts USING fts5(
                    content,
                    content='hm_episodes'
                );
                """
            )

            # 2. Episodic Memory v2.0 Schema
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS episodic_episodes (
                    id TEXT PRIMARY KEY,
                    project_identifier TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary_gist TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('OPEN', 'RESOLVED', 'ABANDONED', 'FAILED')),
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS episodic_events (
                    event_id TEXT PRIMARY KEY,
                    episode_id TEXT REFERENCES episodic_episodes(id) ON DELETE SET NULL,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL CHECK (event_type IN ('PLANNING', 'IMPLEMENTATION', 'TESTING', 'BENCHMARK', 'INCIDENT', 'CRITICAL_RECOVERY')),
                    source_type TEXT NOT NULL CHECK (source_type IN ('DID', 'READ', 'HEARD', 'SIMULATED', 'INFERRED')),
                    title TEXT NOT NULL,
                    verbatim_trace TEXT NOT NULL,
                    gist_summary TEXT NOT NULL,
                    outcome TEXT NOT NULL CHECK (outcome IN ('SUCCESS', 'FAILURE', 'ANOMALY', 'CORRECTED')),
                    lesson_learned TEXT NOT NULL,
                    base_importance REAL NOT NULL CHECK (base_importance BETWEEN 0.0 AND 1.0),
                    operational_salience REAL NOT NULL CHECK (operational_salience BETWEEN 0.0 AND 1.0),
                    conversation_lineage_json TEXT NOT NULL,
                    created_by TEXT NOT NULL DEFAULT 'AGENT',
                    decision_state_json TEXT,
                    verbatim_trace_hash TEXT,
                    confidence REAL DEFAULT 1.0 CHECK (confidence BETWEEN 0.0 AND 1.0)
                );
                CREATE INDEX IF NOT EXISTS idx_ep_event_time ON episodic_events(timestamp DESC);

                CREATE TABLE IF NOT EXISTS episodic_people (
                    person_id TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL UNIQUE,
                    relationship_role TEXT NOT NULL CHECK (relationship_role IN ('USER', 'ENGINEER', 'REVIEWER', 'EXTERNAL_SYSTEM')),
                    last_seen_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS episodic_event_people (
                    event_id TEXT REFERENCES episodic_events(event_id) ON DELETE CASCADE,
                    person_id REFERENCES episodic_people(person_id) ON DELETE CASCADE,
                    PRIMARY KEY (event_id, person_id)
                );

                CREATE TABLE IF NOT EXISTS episodic_links (
                    source_event_id TEXT REFERENCES episodic_events(event_id) ON DELETE CASCADE,
                    target_event_id TEXT REFERENCES episodic_events(event_id) ON DELETE CASCADE,
                    link_type TEXT NOT NULL CHECK (link_type IN ('CAUSED_BY', 'RELATED_TO', 'SAME_PROJECT', 'FOLLOW_UP_TO')),
                    PRIMARY KEY (source_event_id, target_event_id, link_type)
                );

                CREATE TABLE IF NOT EXISTS episodic_reinforcement (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT REFERENCES episodic_events(event_id) ON DELETE CASCADE,
                    access_timestamp REAL NOT NULL,
                    retrieval_reason TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ep_reinforce_lookup ON episodic_reinforcement(event_id);

                CREATE TABLE IF NOT EXISTS episodic_contradictions (
                    source_event_id TEXT REFERENCES episodic_events(event_id) ON DELETE CASCADE,
                    contradicting_event_id TEXT REFERENCES episodic_events(event_id) ON DELETE CASCADE,
                    contradiction_type TEXT NOT NULL,
                    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
                    PRIMARY KEY (source_event_id, contradicting_event_id)
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS episodic_events_fts USING fts5(
                    gist_summary,
                    verbatim_trace,
                    content='episodic_events'
                );
                """
            )

            # 3. Trigger setup to keep legacy FTS and new FTS tables updated
            conn.executescript(
                """
                DROP TRIGGER IF EXISTS trg_hm_episodes_ai;
                DROP TRIGGER IF EXISTS trg_hm_episodes_ad;
                DROP TRIGGER IF EXISTS trg_hm_episodes_au;

                CREATE TRIGGER trg_hm_episodes_ai AFTER INSERT ON hm_episodes BEGIN
                    INSERT INTO hm_episodes_fts(rowid, content) VALUES (new.rowid, new.content);
                END;

                CREATE TRIGGER trg_hm_episodes_ad AFTER DELETE ON hm_episodes BEGIN
                    INSERT INTO hm_episodes_fts(hm_episodes_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
                END;

                CREATE TRIGGER trg_hm_episodes_au AFTER UPDATE OF content ON hm_episodes BEGIN
                    INSERT INTO hm_episodes_fts(hm_episodes_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
                    INSERT INTO hm_episodes_fts(rowid, content) VALUES (new.rowid, new.content);
                END;

                DROP TRIGGER IF EXISTS trg_episodic_events_ai;
                DROP TRIGGER IF EXISTS trg_episodic_events_ad;
                DROP TRIGGER IF EXISTS trg_episodic_events_au;

                CREATE TRIGGER trg_episodic_events_ai AFTER INSERT ON episodic_events BEGIN
                    INSERT INTO episodic_events_fts(rowid, gist_summary, verbatim_trace)
                    VALUES (new.rowid, new.gist_summary, new.verbatim_trace);
                END;

                CREATE TRIGGER trg_episodic_events_ad AFTER DELETE ON episodic_events BEGIN
                    INSERT INTO episodic_events_fts(episodic_events_fts, rowid, gist_summary, verbatim_trace)
                    VALUES ('delete', old.rowid, old.gist_summary, old.verbatim_trace);
                END;

                CREATE TRIGGER trg_episodic_events_au AFTER UPDATE OF gist_summary, verbatim_trace ON episodic_events BEGIN
                    INSERT INTO episodic_events_fts(episodic_events_fts, rowid, gist_summary, verbatim_trace)
                    VALUES ('delete', old.rowid, old.gist_summary, old.verbatim_trace);
                    INSERT INTO episodic_events_fts(rowid, gist_summary, verbatim_trace)
                    VALUES (new.rowid, new.gist_summary, new.verbatim_trace);
                END;
                """
            )

            # Sync tables if empty
            fts_count = conn.execute("SELECT COUNT(*) AS c FROM hm_episodes_fts").fetchone()["c"]
            core_count = conn.execute("SELECT COUNT(*) AS c FROM hm_episodes").fetchone()["c"]
            if fts_count == 0 and core_count > 0:
                conn.execute("INSERT INTO hm_episodes_fts(rowid, content) SELECT rowid, content FROM hm_episodes")

            v2_fts_count = conn.execute("SELECT COUNT(*) AS c FROM episodic_events_fts").fetchone()["c"]
            v2_core_count = conn.execute("SELECT COUNT(*) AS c FROM episodic_events").fetchone()["c"]
            if v2_fts_count == 0 and v2_core_count > 0:
                conn.execute("INSERT INTO episodic_events_fts(rowid, gist_summary, verbatim_trace) SELECT rowid, gist_summary, verbatim_trace FROM episodic_events")

            # Migration checks for new v2.1 fields
            columns = {row[1] for row in conn.execute("PRAGMA table_info(episodic_events)")}
            if "decision_state_json" not in columns:
                conn.execute("ALTER TABLE episodic_events ADD COLUMN decision_state_json TEXT")
            if "verbatim_trace_hash" not in columns:
                conn.execute("ALTER TABLE episodic_events ADD COLUMN verbatim_trace_hash TEXT")
            if "confidence" not in columns:
                conn.execute("ALTER TABLE episodic_events ADD COLUMN confidence REAL DEFAULT 1.0 CHECK (confidence BETWEEN 0.0 AND 1.0)")

            conn.commit()

    @classmethod
    def _get_chroma_collection(cls) -> Any:
        with cls._lock:
            if cls._collection is None:
                config = load_config()
                config.chroma_path.mkdir(parents=True, exist_ok=True)
                cls._chroma_client = chromadb.PersistentClient(
                    path=str(config.chroma_path),
                    settings=chromadb.config.Settings(anonymized_telemetry=False)
                )
                cls._collection = cls._chroma_client.get_or_create_collection(
                    "episodic_vectors",
                    embedding_function=DefaultEmbeddingFunction()
                )
            return cls._collection

    # ----- Embedding Pipeline -----

    @classmethod
    def start_worker(cls) -> None:
        with cls._lock:
            cls._stop_event.clear()
            if cls._worker_thread is None or not cls._worker_thread.is_alive():
                cls._worker_thread = threading.Thread(target=cls._worker_loop, daemon=True)
                cls._worker_thread.start()
            if cls._gc_thread is None or not cls._gc_thread.is_alive():
                cls._gc_thread = threading.Thread(target=cls._gc_scheduler_loop, daemon=True)
                cls._gc_thread.start()

    @classmethod
    def stop_worker(cls) -> None:
        with cls._lock:
            cls._stop_event.set()
            cls._embed_queue.put(("", ""))
            if cls._worker_thread is not None:
                cls._worker_thread.join(timeout=2.0)
                cls._worker_thread = None
            if cls._gc_thread is not None:
                cls._gc_thread.join(timeout=2.0)
                cls._gc_thread = None

    @classmethod
    def _worker_loop(cls) -> None:
        while not cls._stop_event.is_set():
            try:
                episode_id, content = cls._embed_queue.get(timeout=1.0)
                if not episode_id:
                    cls._embed_queue.task_done()
                    continue
                
                items = [(episode_id, content)]
                while len(items) < 20:
                    try:
                        next_id, next_content = cls._embed_queue.get_nowait()
                        if next_id:
                            items.append((next_id, next_content))
                        else:
                            cls._embed_queue.task_done()
                    except queue.Empty:
                        break

                try:
                    cls._process_embeddings(items)
                finally:
                    for _ in range(len(items)):
                        cls._embed_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                log_event(f"episodic_memory: background embedding failed: {e}")

    @classmethod
    def _process_embeddings(cls, items: list[Tuple[str, str]]) -> None:
        ids = [item[0] for item in items]
        documents = [item[1] for item in items]
        collection = cls._get_chroma_collection()
        collection.add(ids=ids, documents=documents)

    @classmethod
    def flush_embeddings(cls, timeout: float = 5.0) -> None:
        cls._embed_queue.join()

    # ----- CRUD Operations -----

    @classmethod
    def create_episode(
        cls,
        content: str = "",
        importance: float = 0.5,
        category: str = "PLANNING",
        session_id: str = "primary",
        tags: list[str] | None = None,
        pinned: int = 0,
        source: Optional[str] = None,
        *,
        episode_id: str | None = None,
        event_type: str | None = None,
        source_type: str = "DID",
        title: str | None = None,
        verbatim_trace: str | None = None,
        gist_summary: str | None = None,
        outcome: str = "SUCCESS",
        lesson_learned: str = "",
        operational_salience: float = 0.1,
        conversation_lineage: list[str] | None = None,
        created_by: str = "AGENT",
        decision_state: dict[str, Any] | None = None
    ) -> str:
        """Create a new episodic memory record, writing to episodic_events & legacy hm_episodes."""
        event_id = str(uuid.uuid4())
        now = time.time()

        # Parse category/event_type mappings
        if not event_type:
            cat_upper = category.upper()
            if cat_upper in {'PLANNING', 'IMPLEMENTATION', 'TESTING', 'BENCHMARK', 'INCIDENT', 'CRITICAL_RECOVERY'}:
                event_type = cat_upper
            elif category == "hce_candidate":
                event_type = "PLANNING"
            else:
                event_type = "IMPLEMENTATION"

        # Defaults for verbatim/gist/title
        if not verbatim_trace:
            verbatim_trace = content
        if not gist_summary:
            gist_summary = content
        if not title:
            title = content[:80] if content else "Untitled Event"

        lineage_json = json.dumps(conversation_lineage or [])
        tags_json = json.dumps(tags or [])

        # Compute SHA256 verbatim trace hash
        import hashlib
        trace_bytes = (verbatim_trace or "").encode("utf-8")
        trace_hash = hashlib.sha256(trace_bytes).hexdigest()

        # Determine base confidence from source type reliability
        reliability_map = {
            "DID": 1.0,
            "READ": 0.8,
            "HEARD": 0.8,
            "SIMULATED": 0.5,
            "INFERRED": 0.7
        }
        base_confidence = reliability_map.get(source_type, 1.0)
        decision_json = json.dumps(decision_state) if decision_state else None

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Enforce parent episode check or create dynamic fallback
                if episode_id:
                    row = conn.execute("SELECT id FROM episodic_episodes WHERE id = ?", (episode_id,)).fetchone()
                    if not row:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO episodic_episodes (id, project_identifier, title, summary_gist, status, created_at, updated_at)
                            VALUES (?, ?, ?, ?, 'OPEN', ?, ?)
                            """,
                            (episode_id, session_id, f"Episode: {episode_id[:8]}", "Auto-generated episode boundary", now, now)
                        )

                # Insert to episodic_events
                conn.execute(
                    """
                    INSERT INTO episodic_events (
                        event_id, episode_id, timestamp, event_type, source_type, title,
                        verbatim_trace, gist_summary, outcome, lesson_learned,
                        base_importance, operational_salience, conversation_lineage_json, created_by,
                        decision_state_json, verbatim_trace_hash, confidence
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id, episode_id, now, event_type, source_type, title,
                        verbatim_trace, gist_summary, outcome, lesson_learned,
                        float(importance), float(operational_salience), lineage_json, created_by,
                        decision_json, trace_hash, base_confidence
                    )
                )

                # Insert to legacy hm_episodes (backward compatibility)
                conn.execute(
                    """
                    INSERT INTO hm_episodes (
                        id, session_id, content, importance, category,
                        created_at, last_recalled_at, recall_count, pinned, tags
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (event_id, session_id, content or gist_summary, importance, category, now, now, pinned, tags_json)
                )

                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        # Log provenance via MemoryGovernance
        try:
            from backend.core.memory_governance import MemoryGovernance
            effective_source = source or category or "chat"
            MemoryGovernance.log_provenance(
                memory_id=event_id,
                memory_type="episodic",
                source=effective_source,
                created_by=created_by,
                confidence=importance,
                metadata={"category": category, "tags": tags or []}
            )
        except Exception as e:
            log_event(f"episodic_memory: failed to log provenance for {event_id}: {e}")

        # Queue for background Chroma vector indexing
        cls.start_worker()
        cls._embed_queue.put((event_id, gist_summary))

        return event_id

    @classmethod
    def get_episode(cls, episode_id: str) -> dict[str, Any] | None:
        """Retrieves a single episode details from SQLite, checking episodic_events."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute(
                """
                SELECT e.*, h.session_id, h.pinned, h.last_recalled_at, h.recall_count, h.tags
                FROM episodic_events e
                JOIN hm_episodes h ON e.event_id = h.id
                WHERE e.event_id = ?
                """,
                (episode_id,)
            ).fetchone()
            
            if not row:
                # Try legacy table fallback directly
                row_legacy = conn.execute("SELECT * FROM hm_episodes WHERE id = ?", (episode_id,)).fetchone()
                if not row_legacy:
                    return None
                record = dict(row_legacy)
                record["tags"] = json.loads(record["tags"])
                record["decay_score"] = cls._calculate_decay(
                    record["importance"], record["last_recalled_at"], bool(record["pinned"])
                )
                return record
            
            record = dict(row)
            
            # Verbatim Trace Hash Protection Verification
            if record.get("verbatim_trace_hash"):
                import hashlib
                calc_hash = hashlib.sha256((record["verbatim_trace"] or "").encode("utf-8")).hexdigest()
                if calc_hash != record["verbatim_trace_hash"]:
                    log_event(f"SECURITY ANOMALY: Verbatim trace hash mismatch detected for event {episode_id}!")
                    return None
            
            record["id"] = record["event_id"]
            record["conversation_lineage"] = json.loads(record.pop("conversation_lineage_json", "[]"))
            record["content"] = record["gist_summary"]
            record["category"] = record["event_type"]
            record["importance"] = record["base_importance"]
            record["pinned"] = record.get("pinned") or 0
            record["session_id"] = record.get("session_id") or "primary"
            record["recall_count"] = record.get("recall_count") or 0
            
            # tags
            tags_val = record.get("tags")
            if tags_val:
                try:
                    record["tags"] = json.loads(tags_val)
                except Exception:
                    record["tags"] = []
            else:
                record["tags"] = []

            # Calculate decay_score
            last_recalled_at = record.get("last_recalled_at") or record["timestamp"]
            record["decay_score"] = cls._calculate_decay(
                record["base_importance"],
                last_recalled_at,
                bool(record["pinned"])
            )
            
            # Fetch dynamic corroboration and contradiction counts for confidence calculation
            contr_row = conn.execute(
                "SELECT COUNT(*) FROM episodic_contradictions WHERE source_event_id = ? OR contradicting_event_id = ?",
                (episode_id, episode_id)
            ).fetchone()
            contradiction_count = contr_row[0] if contr_row else 0

            corr_row = conn.execute(
                "SELECT COUNT(*) FROM episodic_links WHERE source_event_id = ? OR target_event_id = ?",
                (episode_id, episode_id)
            ).fetchone()
            corroboration_count = corr_row[0] if corr_row else 0

            reliability_map = {
                "DID": 1.0,
                "READ": 0.8,
                "HEARD": 0.8,
                "SIMULATED": 0.5,
                "INFERRED": 0.7
            }
            source_reliability = reliability_map.get(record["source_type"], 1.0)
            
            time_elapsed = (time.time() - last_recalled_at) / 86400.0
            record["confidence"] = max(0.0, min(1.0, 
                source_reliability * (1.0 - 0.15 * contradiction_count) + 
                0.05 * corroboration_count - 0.01 * time_elapsed
            ))

            # Deserialize decision state snapshot
            ds_val = record.pop("decision_state_json", None)
            if ds_val:
                try:
                    record["decision_state"] = json.loads(ds_val)
                except Exception:
                    record["decision_state"] = None
            else:
                record["decision_state"] = None

            return record
        finally:
            conn.close()

    @classmethod
    def update_episode(cls, episode_id: str, **kwargs) -> bool:
        """Updates fields in SQLite."""
        allowed_v2 = {"episode_id", "title", "verbatim_trace", "gist_summary", "outcome", "lesson_learned", "base_importance", "operational_salience"}
        updates_v2 = {k: v for k, v in kwargs.items() if k in allowed_v2}

        # Legacy update support
        allowed_legacy = {"session_id", "content", "importance", "category", "pinned", "tags"}
        updates_legacy = {k: v for k, v in kwargs.items() if k in allowed_legacy}

        if not updates_v2 and not updates_legacy:
            return False

        # Map legacy inputs to v2 columns to keep tables synchronized
        if "content" in kwargs:
            if "gist_summary" not in updates_v2:
                updates_v2["gist_summary"] = kwargs["content"]
            if "verbatim_trace" not in updates_v2:
                updates_v2["verbatim_trace"] = kwargs["content"]
        if "importance" in kwargs and "base_importance" not in updates_v2:
            updates_v2["base_importance"] = kwargs["importance"]
        if "category" in kwargs and "event_type" not in updates_v2:
            cat_upper = kwargs["category"].upper()
            if cat_upper in {'PLANNING', 'IMPLEMENTATION', 'TESTING', 'BENCHMARK', 'INCIDENT', 'CRITICAL_RECOVERY'}:
                updates_v2["event_type"] = cat_upper

        # Recalculate hash if verbatim_trace is updated
        if "verbatim_trace" in updates_v2:
            import hashlib
            trace_val = updates_v2["verbatim_trace"] or ""
            updates_v2["verbatim_trace_hash"] = hashlib.sha256(trace_val.encode("utf-8")).hexdigest()

        updated = False
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                if updates_v2:
                    set_clause = ", ".join(f"{k} = ?" for k in updates_v2.keys())
                    params = list(updates_v2.values()) + [episode_id]
                    cursor = conn.execute(f"UPDATE episodic_events SET {set_clause} WHERE event_id = ?", params)
                    if cursor.rowcount > 0:
                        updated = True

                if updates_legacy:
                    if "tags" in updates_legacy:
                        updates_legacy["tags"] = json.dumps(updates_legacy["tags"])
                    set_clause = ", ".join(f"{k} = ?" for k in updates_legacy.keys())
                    params = list(updates_legacy.values()) + [episode_id]
                    cursor = conn.execute(f"UPDATE hm_episodes SET {set_clause} WHERE id = ?", params)
                    if cursor.rowcount > 0:
                        updated = True

                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        if updated and ("gist_summary" in updates_v2 or "content" in updates_legacy):
            content_to_embed = updates_v2.get("gist_summary") or updates_legacy.get("content")
            if content_to_embed:
                cls.start_worker()
                cls._embed_queue.put((episode_id, content_to_embed))

        return updated

    @classmethod
    def delete_episode(cls, episode_id: str) -> bool:
        """Deletes from both SQLite and Chroma vector index."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cursor1 = conn.execute("DELETE FROM episodic_events WHERE event_id = ?", (episode_id,))
                cursor2 = conn.execute("DELETE FROM hm_episodes WHERE id = ?", (episode_id,))
                conn.commit()
                deleted = cursor1.rowcount > 0 or cursor2.rowcount > 0
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        if deleted:
            try:
                collection = cls._get_chroma_collection()
                collection.delete(ids=[episode_id])
            except Exception:
                pass

        return deleted

    # ----- Lazy Decay Core -----

    @classmethod
    def _calculate_decay(cls, importance: float, last_recalled_at: float, pinned: bool) -> float:
        if pinned:
            return importance
        time_elapsed = time.time() - last_recalled_at
        half_life = 86400.0
        decay_factor = 0.95 ** (time_elapsed / half_life)
        return max(0.0, min(1.0, importance * decay_factor))

    # ----- FTS5 Query Sanitization -----

    @classmethod
    def _sanitize_fts_query(cls, query: str) -> str:
        words = re.findall(r"\w+", query)
        if not words:
            return ""
        return " AND ".join(f'"{w}"*' for w in words)

    # ----- Retrieval & Hybrid Fusion -----

    @classmethod
    def recall(
        cls,
        query: str,
        limit: int = 5,
        relevance_floor: float = 0.35,
        *,
        source_types: list[str] | None = None,
        session_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Hybrid Score-Fused Retrieval with read-only logs, decay, and Zeigarnik boost."""
        fts_hits: list[str] = []
        vector_hits: list[str] = []
        
        # Reality Tagging Firewall default
        allowed_sources = source_types if source_types is not None else ["DID"]

        # 1. Lexical search via FTS5
        sanitized = cls._sanitize_fts_query(query)
        if sanitized:
            conn = cls._get_sqlite_conn()
            try:
                placeholders = ", ".join("?" for _ in allowed_sources)
                q_params = [sanitized] + allowed_sources
                
                stmt = f"""
                    SELECT e.event_id FROM episodic_events e
                    JOIN hm_episodes h ON e.event_id = h.id
                    JOIN episodic_events_fts f ON e.rowid = f.rowid
                    WHERE f.episodic_events_fts MATCH ? AND e.source_type IN ({placeholders})
                """
                if session_id:
                    stmt += " AND (h.session_id = ? OR e.episode_id IN (SELECT id FROM episodic_episodes WHERE project_identifier = ?))"
                    q_params.extend([session_id, session_id])
                stmt += " ORDER BY f.rank LIMIT ?"
                
                rows = conn.execute(stmt, q_params + [limit * 3]).fetchall()
                fts_hits = [r["event_id"] for r in rows]
            except Exception as e:
                log_event(f"episodic_memory: FTS5 recall error: {e}")
            finally:
                conn.close()

        # 2. Semantic search via vector index
        try:
            collection = cls._get_chroma_collection()
            if collection.count() > 0:
                query_vector = cls._get_query_embedding(query)
                results = collection.query(
                    query_embeddings=[query_vector],
                    n_results=min(limit * 3, collection.count())
                )
                if results and results.get("ids") and results["ids"][0]:
                    for idx, vid in enumerate(results["ids"][0]):
                        dist = results["distances"][0][idx] if (results.get("distances") and len(results["distances"]) > 0) else 0.0
                        cosine_sim = max(0.0, min(1.0, 1.0 - dist / 2.0))
                        
                        # Apply semantic similarity floor to avoid noise/irrelevant crossovers
                        if cosine_sim < 0.6:
                            continue
                        
                        # Verify source type and session parameters in SQL
                        conn = cls._get_sqlite_conn()
                        try:
                            placeholders = ", ".join("?" for _ in allowed_sources)
                            stmt = f"""
                                SELECT e.event_id FROM episodic_events e
                                JOIN hm_episodes h ON e.event_id = h.id
                                WHERE e.event_id = ? AND e.source_type IN ({placeholders})
                            """
                            params = [str(vid)] + allowed_sources
                            if session_id:
                                stmt += " AND (h.session_id = ? OR e.episode_id IN (SELECT id FROM episodic_episodes WHERE project_identifier = ?))"
                                params.extend([session_id, session_id])
                            row = conn.execute(stmt, params).fetchone()
                            if row:
                                vector_hits.append((str(vid), cosine_sim))
                        finally:
                            conn.close()
        except Exception as e:
            log_event(f"episodic_memory: Vector recall error: {e}")

        # 3. Composite score mapping
        semantic_scores = {vid: sim for vid, sim in vector_hits}
        rrf_scores: dict[str, float] = {}
        k = 60.0

        for rank, eid in enumerate(fts_hits):
            rrf_scores[eid] = rrf_scores.get(eid, 0.0) + (1.0 / (k + rank + 1))

        for rank, (eid, sim) in enumerate(vector_hits):
            rrf_scores[eid] = rrf_scores.get(eid, 0.0) + (1.0 / (k + rank + 1))

        sorted_candidates = sorted(rrf_scores.items(), key=lambda kv: kv[1], reverse=True)

        recalled_events: list[dict[str, Any]] = []
        accessed_ids: list[str] = []

        conn = cls._get_sqlite_conn()
        try:
            now = time.time()
            
            # Fetch average access count for RRF normalization
            avg_access_row = conn.execute("SELECT AVG(c) FROM (SELECT COUNT(*) AS c FROM episodic_reinforcement GROUP BY event_id)").fetchone()
            avg_access_count = float(avg_access_row[0]) if (avg_access_row and avg_access_row[0] is not None) else 1.0
            if avg_access_count < 1.0:
                avg_access_count = 1.0

            for eid, rrf_score in sorted_candidates:
                row = conn.execute(
                    """
                    SELECT e.*, ep.status AS episode_status, ep.project_identifier,
                           h.session_id, h.pinned, h.last_recalled_at, h.recall_count, h.tags
                    FROM episodic_events e
                    LEFT JOIN episodic_episodes ep ON e.episode_id = ep.id
                    JOIN hm_episodes h ON e.event_id = h.id
                    WHERE e.event_id = ?
                    """,
                    (eid,)
                ).fetchone()

                if not row:
                    continue

                record = dict(row)
                
                # Verbatim Trace Hash Protection Verification
                if record.get("verbatim_trace_hash"):
                    import hashlib
                    calc_hash = hashlib.sha256((record["verbatim_trace"] or "").encode("utf-8")).hexdigest()
                    if calc_hash != record["verbatim_trace_hash"]:
                        log_event(f"SECURITY ANOMALY: Verbatim trace hash mismatch detected for event {eid}! Excluding from retrieval.")
                        continue
                
                record["id"] = record["event_id"]
                record["conversation_lineage"] = json.loads(record.pop("conversation_lineage_json", "[]"))

                # Read-Only Event Invariant: access counts from episodic_reinforcement log
                access_rows = conn.execute(
                    "SELECT access_timestamp FROM episodic_reinforcement WHERE event_id = ? ORDER BY access_timestamp DESC",
                    (eid,)
                ).fetchall()
                
                access_count = len(access_rows)
                last_access = access_rows[0]["access_timestamp"] if access_count > 0 else record["timestamp"]

                # Decay calculation
                time_elapsed = (now - last_access) / 86400.0
                lambda_constant = 0.02 if (record["outcome"] == "FAILURE" or record["event_type"] == "INCIDENT") else 0.15
                decay_factor = math.exp(-lambda_constant * time_elapsed)

                # Zeigarnik effect (boost unresolved episodes)
                status_boost = 0.25 if record.get("episode_status") == "OPEN" else 0.0

                # Salience
                salience_boost = 1.0 + record["operational_salience"]

                # Calculated strength
                strength = min(1.0, record["base_importance"] * decay_factor * salience_boost + status_boost)

                # Reinforcement
                reinforcement = math.log(1.0 + access_count) / math.log(1.0 + avg_access_count)

                # Time relevance (linear 30-day window)
                window_delta = 2592000.0
                time_relevance = max(0.0, 1.0 - abs(now - record["timestamp"]) / window_delta)

                semantic_sim = semantic_scores.get(eid, 0.5)

                # Composite retrieval score
                composite_score = (
                    0.40 * semantic_sim +
                    0.25 * record["base_importance"] +
                    0.15 * min(1.0, reinforcement) +  # Cap reinforcement weight at 15% and reinforce term at 1.0
                    0.20 * time_relevance
                )

                # Relevance Floor
                if composite_score < relevance_floor:
                    continue

                record["decay_score"] = strength
                record["rrf_score"] = rrf_score
                record["composite_score"] = composite_score
                record["access_count"] = access_count
                record["last_recalled_at"] = last_access

                # Mappings for legacy compatibility
                record["content"] = record["gist_summary"]
                record["category"] = record["event_type"]
                record["importance"] = record["base_importance"]
                record["pinned"] = record.get("pinned") or 0
                record["session_id"] = record.get("session_id") or "primary"
                record["recall_count"] = access_count + 1
                
                # Fetch dynamic corroboration and contradiction counts for confidence calculation
                contr_row = conn.execute(
                    "SELECT COUNT(*) FROM episodic_contradictions WHERE source_event_id = ? OR contradicting_event_id = ?",
                    (eid, eid)
                ).fetchone()
                contradiction_count = contr_row[0] if contr_row else 0

                corr_row = conn.execute(
                    "SELECT COUNT(*) FROM episodic_links WHERE source_event_id = ? OR target_event_id = ?",
                    (eid, eid)
                ).fetchone()
                corroboration_count = corr_row[0] if corr_row else 0

                reliability_map = {
                    "DID": 1.0,
                    "READ": 0.8,
                    "HEARD": 0.8,
                    "SIMULATED": 0.5,
                    "INFERRED": 0.7
                }
                source_reliability = reliability_map.get(record["source_type"], 1.0)
                
                time_elapsed_confidence = (time.time() - last_access) / 86400.0
                record["confidence"] = max(0.0, min(1.0, 
                    source_reliability * (1.0 - 0.15 * contradiction_count) + 
                    0.05 * corroboration_count - 0.01 * time_elapsed_confidence
                ))

                # Deserialize decision state snapshot
                ds_val = record.pop("decision_state_json", None)
                if ds_val:
                    try:
                        record["decision_state"] = json.loads(ds_val)
                    except Exception:
                        record["decision_state"] = None
                else:
                    record["decision_state"] = None
                
                tags_val = record.get("tags")
                if tags_val:
                    try:
                        record["tags"] = json.loads(tags_val)
                    except Exception:
                        record["tags"] = []
                else:
                    record["tags"] = []

                recalled_events.append(record)
                accessed_ids.append(eid)

                if len(recalled_events) >= limit:
                    break

            # Write access logs (Read-only event table logs)
            if accessed_ids:
                for eid in accessed_ids:
                    conn.execute(
                        "INSERT INTO episodic_reinforcement (event_id, access_timestamp, retrieval_reason) VALUES (?, ?, ?)",
                        (eid, now, f"recall: {query[:50]}")
                    )
                conn.commit()

        except Exception as e:
            conn.rollback()
            log_event(f"episodic_memory: query tracking update failed: {e}")
        finally:
            conn.close()

        return recalled_events

    # ----- Consistency GC -----

    @classmethod
    def run_vector_gc(cls) -> int:
        orphans_purged = 0
        try:
            collection = cls._get_chroma_collection()
            count = collection.count()
            if count == 0:
                return 0

            results = collection.get(include=[])
            chroma_ids = results.get("ids", [])
            if not chroma_ids:
                return 0

            chunk_size = 500
            conn = cls._get_sqlite_conn()
            try:
                for i in range(0, len(chroma_ids), chunk_size):
                    chunk = chroma_ids[i:i+chunk_size]
                    placeholders = ", ".join("?" for _ in chunk)
                    
                    # Fetch present IDs from the authoritative legacy table
                    rows_legacy = conn.execute(
                        f"SELECT id FROM hm_episodes WHERE id IN ({placeholders})", chunk
                    ).fetchall()
                    sqlite_present_ids = {r["id"] for r in rows_legacy}

                    orphans = [cid for cid in chunk if cid not in sqlite_present_ids]
                    if orphans:
                        collection.delete(ids=orphans)
                        orphan_placeholders = ", ".join("?" for _ in orphans)
                        conn.execute(
                            f"DELETE FROM episodic_events WHERE event_id IN ({orphan_placeholders})", orphans
                        )
                        conn.commit()
                        orphans_purged += len(orphans)
            finally:
                conn.close()
        except Exception as e:
            log_event(f"episodic_memory: GC sweep failed: {e}")

        return orphans_purged

    # ----- Query Cache, Archiving & GC Scheduler -----

    @classmethod
    def _get_embedding_fn(cls) -> Any:
        with cls._lock:
            if cls._emb_fn is None:
                cls._emb_fn = DefaultEmbeddingFunction()
            return cls._emb_fn

    @classmethod
    def _get_query_embedding(cls, query: str) -> list[float]:
        with cls._lock:
            if query in cls._query_cache:
                return cls._query_cache[query]

            emb_fn = cls._get_embedding_fn()
            embedding = emb_fn([query])[0]

            if len(cls._query_cache) > 500:
                cls._query_cache.pop(next(iter(cls._query_cache)))
            cls._query_cache[query] = embedding
            return embedding

    @classmethod
    def archive_decayed_episodes(cls, threshold: float = 0.1) -> int:
        archived_count = 0
        conn = cls._get_sqlite_conn()
        try:
            # Query v2 tables
            rows = conn.execute("SELECT * FROM episodic_events").fetchall()
            now = time.time()
            to_archive = []

            for row in rows:
                # Compute decay using access logs
                access_rows = conn.execute(
                    "SELECT access_timestamp FROM episodic_reinforcement WHERE event_id = ? ORDER BY access_timestamp DESC LIMIT 1",
                    (row["event_id"],)
                ).fetchone()
                last_access = access_rows["access_timestamp"] if access_rows else row["timestamp"]
                decay = cls._calculate_decay(row["base_importance"], last_access, False)
                if decay < threshold:
                    to_archive.append(dict(row))

            if to_archive:
                with cls._lock:
                    for item in to_archive:
                        eid = item["event_id"]
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO hm_episodes_archive (
                                id, session_id, content, importance, category, created_at, archived_at, tags
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (eid, "primary", item["gist_summary"], item["base_importance"],
                             item["event_type"], item["timestamp"], now, "[]")
                        )
                        conn.execute("DELETE FROM episodic_events WHERE event_id = ?", (eid,))
                        conn.execute("DELETE FROM hm_episodes WHERE id = ?", (eid,))

                        try:
                            collection = cls._get_chroma_collection()
                            collection.delete(ids=[eid])
                        except Exception:
                            pass

                        archived_count += 1
                    conn.commit()
        except Exception as e:
            log_event(f"episodic_memory: scheduled archiving failed: {e}")
        finally:
            conn.close()
        return archived_count

    @classmethod
    def _gc_scheduler_loop(cls) -> None:
        while not cls._stop_event.is_set():
            for _ in range(600):
                if cls._stop_event.is_set():
                    break
                time.sleep(1.0)
            if cls._stop_event.is_set():
                break

            try:
                cls.run_vector_gc()
                cls.archive_decayed_episodes(threshold=0.1)
            except Exception as e:
                log_event(f"episodic_memory: scheduled GC and archive sweep failed: {e}")
