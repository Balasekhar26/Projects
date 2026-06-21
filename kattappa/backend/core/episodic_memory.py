from __future__ import annotations

import json
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
    """Episodic Memory Subsystem (Layer 3) representing chronological experience history.
    
    Adheres to Memory System v2.0 specification:
    - Authoritative source of truth is SQLite.
    - Retrieval indexing via Chroma DB (indices only, never authoritative).
    - Query-time lazy decay to avoid write amplification and lockups.
    - Hybrid retrieval (FTS5 + Vector + Reciprocal Rank Fusion).
    - Background embedding queue to keep the chat loop fast.
    - Vector GC to prevent ghost recalls.
    """
    
    _lock = threading.RLock()
    _embed_queue: queue.Queue[Tuple[str, str]] = queue.Queue()
    _worker_thread: threading.Thread | None = None
    _stop_event = threading.Event()
    _chroma_client: Any | None = None
    _collection: Any | None = None

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            # 1. Authoritative SQLite Episodes Table
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

                -- 2. FTS5 Virtual Table for External Content mapping (Memory System v2.0)
                CREATE VIRTUAL TABLE IF NOT EXISTS hm_episodes_fts USING fts5(
                    content,
                    content='hm_episodes'
                );

                -- 3. Drop triggers to re-create with correct external-content deletion syntax
                DROP TRIGGER IF EXISTS trg_hm_episodes_ai;
                DROP TRIGGER IF EXISTS trg_hm_episodes_ad;
                DROP TRIGGER IF EXISTS trg_hm_episodes_au;

                -- 4. Triggers to auto-sync FTS5 External Content Virtual Table
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
                """
            )
            
            # Sync FTS table if it has missed items
            fts_count = conn.execute("SELECT COUNT(*) AS c FROM hm_episodes_fts").fetchone()["c"]
            core_count = conn.execute("SELECT COUNT(*) AS c FROM hm_episodes").fetchone()["c"]
            if fts_count == 0 and core_count > 0:
                conn.execute("INSERT INTO hm_episodes_fts(rowid, content) SELECT rowid, content FROM hm_episodes")
            
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
            if cls._worker_thread is not None and cls._worker_thread.is_alive():
                return
            cls._stop_event.clear()
            cls._worker_thread = threading.Thread(target=cls._worker_loop, daemon=True)
            cls._worker_thread.start()

    @classmethod
    def stop_worker(cls) -> None:
        with cls._lock:
            if cls._worker_thread is None:
                return
            cls._stop_event.set()
            cls._embed_queue.put(("", "")) # Unblock loop
            cls._worker_thread.join(timeout=3.0)
            cls._worker_thread = None

    @classmethod
    def _worker_loop(cls) -> None:
        while not cls._stop_event.is_set():
            try:
                # Retrieve from queue
                episode_id, content = cls._embed_queue.get(timeout=1.0)
                if not episode_id:
                    cls._embed_queue.task_done()
                    continue
                
                # Batch read others from queue to optimize embeddings
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

                # Execute write to vector store
                cls._process_embeddings(items)
                
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
        """Forces the worker to finish processing the current queue contents (useful in tests)."""
        cls._embed_queue.join()

    # ----- CRUD Operations -----

    @classmethod
    def create_episode(
        cls,
        content: str,
        importance: float,
        category: str,
        session_id: str = "primary",
        tags: list[str] | None = None,
        pinned: int = 0
    ) -> str:
        """Creates a new episodic memory record and queues it for semantic vector indexing."""
        episode_id = str(uuid.uuid4())
        tags_json = json.dumps(tags or [])
        now = time.time()

        # 1. Authoritative insert to SQLite
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_episodes (
                        id, session_id, content, importance, category,
                        created_at, last_recalled_at, recall_count, pinned, tags
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (episode_id, session_id, content, importance, category, now, now, pinned, tags_json)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        # 2. Queue for background Chroma vector indexing
        cls.start_worker()
        cls._embed_queue.put((episode_id, content))
        
        return episode_id

    @classmethod
    def get_episode(cls, episode_id: str) -> dict[str, Any] | None:
        """Retrieves a single episode from SQLite, computing lazy decay on the fly."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM hm_episodes WHERE id = ?", (episode_id,)).fetchone()
            if not row:
                return None
            
            record = dict(row)
            record["tags"] = json.loads(record["tags"])
            record["decay_score"] = cls._calculate_decay(
                record["importance"], record["last_recalled_at"], bool(record["pinned"])
            )
            return record
        finally:
            conn.close()

    @classmethod
    def update_episode(cls, episode_id: str, **kwargs) -> bool:
        """Updates fields in SQLite. If content is updated, queues the vector index for updates."""
        allowed_fields = {"session_id", "content", "importance", "category", "pinned", "tags"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return False

        if "tags" in updates:
            updates["tags"] = json.dumps(updates["tags"])

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        params = list(updates.values()) + [episode_id]

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cursor = conn.execute(f"UPDATE hm_episodes SET {set_clause} WHERE id = ?", params)
                conn.commit()
                updated = cursor.rowcount > 0
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        if updated and "content" in updates:
            cls.start_worker()
            cls._embed_queue.put((episode_id, updates["content"]))

        return updated

    @classmethod
    def delete_episode(cls, episode_id: str) -> bool:
        """Deletes from both SQLite and Chroma vector index."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cursor = conn.execute("DELETE FROM hm_episodes WHERE id = ?", (episode_id,))
                conn.commit()
                deleted = cursor.rowcount > 0
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
                pass # Graceful fallback if vector index delete errors

        return deleted

    # ----- Lazy Decay Core -----

    @classmethod
    def _calculate_decay(cls, importance: float, last_recalled_at: float, pinned: bool) -> float:
        if pinned:
            return importance
        
        # Power-law / exponential decay based on time elapsed since last recall
        # Half-life: 1 day (86400 seconds)
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
        # Format as a prefix OR match, e.g., "word1"* OR "word2"*
        # This completely prevents search syntax injection errors
        return " OR ".join(f'"{w}"*' for w in words)

    # ----- Retrieval & Hybrid Fusion -----

    @classmethod
    def recall(cls, query: str, limit: int = 5, relevance_floor: float = 0.01) -> list[dict[str, Any]]:
        """Hybrid Score-Fused Retrieval (FTS5 + Chroma Vector + RRF + Relevance Floor)."""
        fts_hits: list[str] = []
        vector_hits: list[str] = []

        # 1. Lexical search via FTS5
        sanitized = cls._sanitize_fts_query(query)
        if sanitized:
            conn = cls._get_sqlite_conn()
            try:
                rows = conn.execute(
                    """
                    SELECT id FROM hm_episodes 
                    WHERE rowid IN (
                        SELECT rowid FROM hm_episodes_fts WHERE hm_episodes_fts MATCH ?
                    )
                    LIMIT ?
                    """,
                    (sanitized, limit * 3)
                ).fetchall()
                fts_hits = [r["id"] for r in rows]
            except Exception as e:
                log_event(f"episodic_memory: FTS5 recall error: {e}")
            finally:
                conn.close()

        # 2. Semantic search via ChromaDB vector index
        try:
            collection = cls._get_chroma_collection()
            if collection.count() > 0:
                results = collection.query(
                    query_texts=[query],
                    n_results=min(limit * 3, collection.count())
                )
                if results and results.get("ids") and results["ids"][0]:
                    for idx, vid in enumerate(results["ids"][0]):
                        dist = results["distances"][0][idx] if (results.get("distances") and len(results["distances"]) > 0) else 0.0
                        if dist <= 1.2:
                            vector_hits.append(str(vid))
        except Exception as e:
            log_event(f"episodic_memory: Vector recall error: {e}")

        # 3. Reciprocal Rank Fusion (RRF)
        # Combine the lists. Constant k = 60 is standard.
        rrf_scores: dict[str, float] = {}
        k = 60.0

        for rank, eid in enumerate(fts_hits):
            rrf_scores[eid] = rrf_scores.get(eid, 0.0) + (1.0 / (k + rank + 1))

        for rank, eid in enumerate(vector_hits):
            rrf_scores[eid] = rrf_scores.get(eid, 0.0) + (1.0 / (k + rank + 1))

        # Sort candidates by descending RRF score
        sorted_candidates = sorted(rrf_scores.items(), key=lambda kv: kv[1], reverse=True)

        # 4. Fetch live records from SQLite (Authoritative check)
        recalled_episodes: list[dict[str, Any]] = []
        accessed_ids: list[str] = []

        conn = cls._get_sqlite_conn()
        try:
            now = time.time()
            for eid, rrf_score in sorted_candidates:
                # Apply relevance floor
                if rrf_score < relevance_floor:
                    continue

                # Query database
                row = conn.execute("SELECT * FROM hm_episodes WHERE id = ?", (eid,)).fetchone()
                if not row:
                    # SQLite missing record - flag vector index discrepancy
                    log_event(f"episodic_memory: consistency warning - vector index contains orphan ID {eid}")
                    continue

                record = dict(row)
                record["tags"] = json.loads(record["tags"])
                record["rrf_score"] = rrf_score
                record["decay_score"] = cls._calculate_decay(
                    record["importance"], record["last_recalled_at"], bool(record["pinned"])
                )
                record["recall_count"] += 1
                record["last_recalled_at"] = now

                recalled_episodes.append(record)
                accessed_ids.append(eid)

                if len(recalled_episodes) >= limit:
                    break

            # 5. Dynamic update of access parameters inside transaction
            if accessed_ids:
                placeholders = ", ".join("?" for _ in accessed_ids)
                conn.execute(
                    f"UPDATE hm_episodes SET last_recalled_at = ?, recall_count = recall_count + 1 WHERE id IN ({placeholders})",
                    [now] + accessed_ids
                )
                conn.commit()
        except Exception as e:
            conn.rollback()
            log_event(f"episodic_memory: query tracking update failed: {e}")
        finally:
            conn.close()

        return recalled_episodes

    # ----- Consistency GC -----

    @classmethod
    def run_vector_gc(cls) -> int:
        """Finds and deletes any vector IDs in Chroma that are missing from SQLite."""
        orphans_purged = 0
        try:
            collection = cls._get_chroma_collection()
            count = collection.count()
            if count == 0:
                return 0

            # Get all IDs in the Chroma collection
            results = collection.get(include=[])
            chroma_ids = results.get("ids", [])
            if not chroma_ids:
                return 0

            # Batch verify against SQLite in chunks of 500
            chunk_size = 500
            conn = cls._get_sqlite_conn()
            try:
                for i in range(0, len(chroma_ids), chunk_size):
                    chunk = chroma_ids[i:i+chunk_size]
                    placeholders = ", ".join("?" for _ in chunk)
                    
                    # Fetch present IDs
                    rows = conn.execute(
                        f"SELECT id FROM hm_episodes WHERE id IN ({placeholders})", chunk
                    ).fetchall()
                    sqlite_present_ids = {r["id"] for r in rows}

                    # Find orphans in this chunk
                    orphans = [cid for cid in chunk if cid not in sqlite_present_ids]
                    if orphans:
                        collection.delete(ids=orphans)
                        orphans_purged += len(orphans)
                        log_event(f"episodic_memory: GC deleted {len(orphans)} orphan vectors from Chroma")
            finally:
                conn.close()

        except Exception as e:
            log_event(f"episodic_memory: GC sweep failed: {e}")

        return orphans_purged
