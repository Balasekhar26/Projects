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


class SemanticMemory:
    """Semantic Memory Subsystem (Layer 4) representing long-term verified facts.
    
    Adheres to Memory System v2.0 specification:
    - Authoritative source of truth is SQLite (Property Graph schema: nodes and edges).
    - FTS5 virtual table indexing for concepts and descriptions.
    - Chroma concept index for semantic vector search (never authoritative).
    - Negation / polarity matching check before merging during canonicalization.
    - Incremental confidence and evidence updates on node merges.
    - Graph traversal API up to 3 hops with edge weight thresholds (>= 0.35).
    - Hybrid score-fused retrieval (FTS5 + Chroma Vector + RRF).
    - Asynchronous worker queue for batch embeddings updates.
    """
    
    _lock = threading.RLock()
    _embed_queue: queue.Queue[Tuple[str, str, str]] = queue.Queue() # (node_id, concept, description)
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
            # 1. Authoritative SQLite Semantic Tables (Property Graph)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS hm_semantic_nodes (
                    id TEXT PRIMARY KEY,
                    concept TEXT NOT NULL,
                    description TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_count INTEGER DEFAULT 1,
                    source_episode_ids TEXT DEFAULT '[]',
                    provenance TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_hm_semantic_nodes_concept ON hm_semantic_nodes(concept);

                CREATE TABLE IF NOT EXISTS hm_semantic_edges (
                    id TEXT PRIMARY KEY,
                    source_node_id TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (source_node_id) REFERENCES hm_semantic_nodes(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_node_id) REFERENCES hm_semantic_nodes(id) ON DELETE CASCADE,
                    UNIQUE (source_node_id, target_node_id, relation)
                );
                CREATE INDEX IF NOT EXISTS idx_hm_semantic_edges_source ON hm_semantic_edges(source_node_id);
                CREATE INDEX IF NOT EXISTS idx_hm_semantic_edges_target ON hm_semantic_edges(target_node_id);

                -- 2. FTS5 Virtual Table for External Content mapping (Memory System v2.0)
                CREATE VIRTUAL TABLE IF NOT EXISTS hm_semantic_nodes_fts USING fts5(
                    concept,
                    description,
                    content='hm_semantic_nodes'
                );

                -- 3. Drop triggers to re-create with correct external-content deletion syntax
                DROP TRIGGER IF EXISTS trg_hm_semantic_nodes_ai;
                DROP TRIGGER IF EXISTS trg_hm_semantic_nodes_ad;
                DROP TRIGGER IF EXISTS trg_hm_semantic_nodes_au;

                -- 4. Triggers to auto-sync FTS5 External Content Virtual Table
                CREATE TRIGGER trg_hm_semantic_nodes_ai AFTER INSERT ON hm_semantic_nodes BEGIN
                    INSERT INTO hm_semantic_nodes_fts(rowid, concept, description) VALUES (new.rowid, new.concept, new.description);
                END;

                CREATE TRIGGER trg_hm_semantic_nodes_ad AFTER DELETE ON hm_semantic_nodes BEGIN
                    INSERT INTO hm_semantic_nodes_fts(hm_semantic_nodes_fts, rowid, concept, description) VALUES ('delete', old.rowid, old.concept, old.description);
                END;

                CREATE TRIGGER trg_hm_semantic_nodes_au AFTER UPDATE OF concept, description ON hm_semantic_nodes BEGIN
                    INSERT INTO hm_semantic_nodes_fts(hm_semantic_nodes_fts, rowid, concept, description) VALUES ('delete', old.rowid, old.concept, old.description);
                    INSERT INTO hm_semantic_nodes_fts(rowid, concept, description) VALUES (new.rowid, new.concept, new.description);
                END;
                """
            )
            
            # Sync FTS table if it has missed items
            fts_count = conn.execute("SELECT COUNT(*) AS c FROM hm_semantic_nodes_fts").fetchone()["c"]
            core_count = conn.execute("SELECT COUNT(*) AS c FROM hm_semantic_nodes").fetchone()["c"]
            if fts_count == 0 and core_count > 0:
                conn.execute("INSERT INTO hm_semantic_nodes_fts(rowid, concept, description) SELECT rowid, concept, description FROM hm_semantic_nodes")
            
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
                    "semantic_vectors",
                    embedding_function=DefaultEmbeddingFunction()
                )
            return cls._collection

    # ----- Asynchronous Embedding Pipeline -----

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
            cls._embed_queue.put(("", "", "")) # Unblock loop
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
                node_id, concept, description = cls._embed_queue.get(timeout=1.0)
                if not node_id:
                    cls._embed_queue.task_done()
                    continue
                
                items = [(node_id, concept, description)]
                while len(items) < 20:
                    try:
                        next_id, next_concept, next_desc = cls._embed_queue.get_nowait()
                        if next_id:
                            items.append((next_id, next_concept, next_desc))
                        else:
                            cls._embed_queue.task_done()
                    except queue.Empty:
                        break

                cls._process_embeddings(items)
                
                for _ in range(len(items)):
                    cls._embed_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                log_event(f"semantic_memory: background embedding failed: {e}")

    @classmethod
    def _process_embeddings(cls, items: list[Tuple[str, str, str]]) -> None:
        ids = [item[0] for item in items]
        documents = [f"{item[1]}: {item[2]}" for item in items]
        collection = cls._get_chroma_collection()
        collection.upsert(ids=ids, documents=documents)

    @classmethod
    def flush_embeddings(cls, timeout: float = 5.0) -> None:
        """Forces worker thread to flush the queue contents."""
        cls._embed_queue.join()

    # ----- Polarity & Negation Logic -----

    @classmethod
    def _detect_negation(cls, text: str) -> bool:
        negation_pattern = re.compile(
            r"\b(not|no|never|neither|nor|none|n't|cannot|cant|don't|dont|doesn't|doesnt|isn't|isnt|wasn't|wasnt|won't|wont|shant|shan't|shouldn't|shouldnt|wouldn't|wouldnt|couldn't|couldnt)\b",
            re.IGNORECASE
        )
        return bool(negation_pattern.search(text))

    @classmethod
    def _check_polarity_match(cls, text1: str, text2: str) -> bool:
        return cls._detect_negation(text1) == cls._detect_negation(text2)

    # ----- Canonicalization Node Upsert -----

    @classmethod
    def upsert_node(
        cls,
        concept: str,
        description: str,
        source_episode_id: str,
        provenance: Optional[str] = None,
        confidence: float = 0.5,
        similarity_threshold: float = 0.6
    ) -> str:
        """Upsert a semantic node into SQLite, applying canonicalization and polarity checks before merge.
        
        Merge condition:
        - Cosine similarity (L2 distance <= similarity_threshold) OR exact case-insensitive concept match
        - AND same polarity (both negated or neither negated)
        """
        concept_clean = concept.strip()
        description_clean = description.strip()
        
        existing_node: dict[str, Any] | None = None
        
        # 1. Exact case-insensitive concept match in SQLite
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT * FROM hm_semantic_nodes WHERE LOWER(concept) = LOWER(?)",
                (concept_clean,)
            ).fetchone()
            if row:
                existing_node = dict(row)
        finally:
            conn.close()

        # 2. If no exact match, semantic search via ChromaDB
        if not existing_node:
            try:
                collection = cls._get_chroma_collection()
                if collection.count() > 0:
                    results = collection.query(
                        query_texts=[f"{concept_clean}: {description_clean}"],
                        n_results=1
                    )
                    if results and results.get("ids") and results["ids"][0]:
                        candidate_id = results["ids"][0][0]
                        distance = results["distances"][0][0] if results.get("distances") else 9.9
                        
                        if distance <= similarity_threshold:
                            conn = cls._get_sqlite_conn()
                            try:
                                row = conn.execute("SELECT * FROM hm_semantic_nodes WHERE id = ?", (candidate_id,)).fetchone()
                                if row:
                                    existing_node = dict(row)
                            finally:
                                conn.close()
            except Exception as e:
                log_event(f"semantic_memory: vector similarity search failed: {e}")

        # 3. Merging & Canonicalization checks
        if existing_node:
            if cls._check_polarity_match(description_clean, existing_node["description"]):
                node_id = existing_node["id"]
                evidence_count = existing_node["evidence_count"] + 1
                
                try:
                    episode_ids = json.loads(existing_node["source_episode_ids"])
                except Exception:
                    episode_ids = []
                if source_episode_id not in episode_ids:
                    episode_ids.append(source_episode_id)
                episode_ids_json = json.dumps(episode_ids)
                
                # Asymptotic confidence model
                new_confidence = min(1.0, 1.0 - (0.5 ** evidence_count))
                
                existing_desc = existing_node["description"]
                if description_clean in existing_desc:
                    merged_desc = existing_desc
                elif existing_desc in description_clean:
                    merged_desc = description_clean
                else:
                    merged_desc = f"{existing_desc}; {description_clean}"

                now = time.time()
                
                with cls._lock:
                    conn = cls._get_sqlite_conn()
                    try:
                        conn.execute(
                            """
                            UPDATE hm_semantic_nodes 
                            SET description = ?, confidence = ?, evidence_count = ?, 
                                source_episode_ids = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (merged_desc, new_confidence, evidence_count, episode_ids_json, now, node_id)
                        )
                        conn.commit()
                    except Exception as e:
                        conn.rollback()
                        raise e
                    finally:
                        conn.close()

                cls.start_worker()
                cls._embed_queue.put((node_id, existing_node["concept"], merged_desc))
                
                return node_id
            else:
                log_event(f"semantic_memory: polarity mismatch against existing concept '{existing_node['concept']}' - skipping merge")

        # 4. Create new node (no polarity-compatible match found)
        node_id = str(uuid.uuid4())
        episode_ids_json = json.dumps([source_episode_id])
        now = time.time()

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_semantic_nodes (
                        id, concept, description, confidence, evidence_count,
                        source_episode_ids, provenance, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                    """,
                    (node_id, concept_clean, description_clean, confidence, episode_ids_json, provenance, now, now)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        cls.start_worker()
        cls._embed_queue.put((node_id, concept_clean, description_clean))

        return node_id

    @classmethod
    def get_node(cls, node_id: str) -> dict[str, Any] | None:
        """Retrieves a single semantic node from SQLite."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM hm_semantic_nodes WHERE id = ?", (node_id,)).fetchone()
            if not row:
                return None
            record = dict(row)
            record["source_episode_ids"] = json.loads(record["source_episode_ids"])
            return record
        finally:
            conn.close()

    @classmethod
    def delete_node(cls, node_id: str) -> bool:
        """Delete semantic node from SQLite and ChromaDB."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cursor = conn.execute("DELETE FROM hm_semantic_nodes WHERE id = ?", (node_id,))
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
                collection.delete(ids=[node_id])
            except Exception:
                pass
        return deleted

    # ----- Property Graph Edges -----

    @classmethod
    def create_edge(
        cls,
        source_node_id: str,
        target_node_id: str,
        relation: str,
        weight: float = 0.5
    ) -> str:
        """Create or update a relationship edge between two nodes in the property graph."""
        edge_id = str(uuid.uuid4())
        relation_clean = relation.strip().lower()
        now = time.time()

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Check for existing relation edge
                row = conn.execute(
                    """
                    SELECT id FROM hm_semantic_edges 
                    WHERE source_node_id = ? AND target_node_id = ? AND relation = ?
                    """,
                    (source_node_id, target_node_id, relation_clean)
                ).fetchone()

                if row:
                    existing_id = row["id"]
                    conn.execute(
                        """
                        UPDATE hm_semantic_edges 
                        SET weight = ?, updated_at = ? 
                        WHERE id = ?
                        """,
                        (weight, now, existing_id)
                    )
                    conn.commit()
                    return existing_id
                else:
                    conn.execute(
                        """
                        INSERT INTO hm_semantic_edges (
                            id, source_node_id, target_node_id, relation, weight, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (edge_id, source_node_id, target_node_id, relation_clean, weight, now, now)
                    )
                    conn.commit()
                    return edge_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_edge(cls, edge_id: str) -> dict[str, Any] | None:
        """Retrieve edge details from SQLite."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM hm_semantic_edges WHERE id = ?", (edge_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @classmethod
    def delete_edge(cls, edge_id: str) -> bool:
        """Delete relationship edge from SQLite."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cursor = conn.execute("DELETE FROM hm_semantic_edges WHERE id = ?", (edge_id,))
                conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    # ----- Graph Traversal -----

    @classmethod
    def traverse_graph(
        cls,
        start_node_id: str,
        max_hops: int = 3,
        min_weight: float = 0.35
    ) -> dict[str, Any]:
        """Traverse the semantic property graph starting from start_node_id.
        
        Returns a dict of nodes and edges in the traversed subgraph.
        Traverses up to max_hops away along edges with weight >= min_weight.
        """
        visited_nodes: dict[str, dict[str, Any]] = {}
        traversed_edges: list[dict[str, Any]] = []
        queue_bfs = [(start_node_id, 0)]
        
        conn = cls._get_sqlite_conn()
        try:
            start_row = conn.execute("SELECT * FROM hm_semantic_nodes WHERE id = ?", (start_node_id,)).fetchone()
            if not start_row:
                return {"nodes": {}, "edges": []}
            
            start_node = dict(start_row)
            start_node["source_episode_ids"] = json.loads(start_node["source_episode_ids"])
            visited_nodes[start_node_id] = start_node
            
            idx = 0
            while idx < len(queue_bfs):
                current_id, hop = queue_bfs[idx]
                idx += 1
                
                if hop >= max_hops:
                    continue
                
                rows = conn.execute(
                    """
                    SELECT e.*, n.concept, n.description, n.confidence, n.evidence_count, n.source_episode_ids, n.provenance
                    FROM hm_semantic_edges e
                    JOIN hm_semantic_nodes n ON e.target_node_id = n.id
                    WHERE e.source_node_id = ? AND e.weight >= ?
                    """,
                    (current_id, min_weight)
                ).fetchall()
                
                for r in rows:
                    edge = {
                        "id": r["id"],
                        "source_node_id": r["source_node_id"],
                        "target_node_id": r["target_node_id"],
                        "relation": r["relation"],
                        "weight": r["weight"]
                    }
                    if edge not in traversed_edges:
                        traversed_edges.append(edge)
                    
                    target_id = r["target_node_id"]
                    if target_id not in visited_nodes:
                        target_node = {
                            "id": target_id,
                            "concept": r["concept"],
                            "description": r["description"],
                            "confidence": r["confidence"],
                            "evidence_count": r["evidence_count"],
                            "source_episode_ids": json.loads(r["source_episode_ids"]),
                            "provenance": r["provenance"]
                        }
                        visited_nodes[target_id] = target_node
                        queue_bfs.append((target_id, hop + 1))
                        
            return {
                "nodes": visited_nodes,
                "edges": traversed_edges
            }
        finally:
            conn.close()

    # ----- Hybrid Retrieval -----

    @classmethod
    def _sanitize_fts_query(cls, query: str) -> str:
        words = re.findall(r"\w+", query)
        if not words:
            return ""
        return " OR ".join(f'"{w}"*' for w in words)

    @classmethod
    def recall(
        cls,
        query: str,
        limit: int = 5,
        relevance_floor: float = 0.01,
        similarity_threshold: float = 1.2
    ) -> list[dict[str, Any]]:
        """Hybrid retrieval for semantic memory (FTS5 + Vector query + RRF)."""
        fts_hits: list[str] = []
        vector_hits: list[str] = []

        # 1. Lexical search via FTS5
        sanitized = cls._sanitize_fts_query(query)
        if sanitized:
            conn = cls._get_sqlite_conn()
            try:
                rows = conn.execute(
                    """
                    SELECT id FROM hm_semantic_nodes 
                    WHERE rowid IN (
                        SELECT rowid FROM hm_semantic_nodes_fts WHERE hm_semantic_nodes_fts MATCH ?
                    )
                    LIMIT ?
                    """,
                    (sanitized, limit * 3)
                ).fetchall()
                fts_hits = [r["id"] for r in rows]
            except Exception as e:
                log_event(f"semantic_memory: FTS5 recall error: {e}")
            finally:
                conn.close()

        # 2. Semantic search via ChromaDB vector index
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
                        if dist <= similarity_threshold:
                            vector_hits.append(str(vid))
        except Exception as e:
            log_event(f"semantic_memory: Vector recall error: {e}")

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores: dict[str, float] = {}
        k = 60.0

        for rank, nid in enumerate(fts_hits):
            rrf_scores[nid] = rrf_scores.get(nid, 0.0) + (1.0 / (k + rank + 1))

        for rank, nid in enumerate(vector_hits):
            rrf_scores[nid] = rrf_scores.get(nid, 0.0) + (1.0 / (k + rank + 1))

        sorted_candidates = sorted(rrf_scores.items(), key=lambda kv: kv[1], reverse=True)

        # 4. Fetch live records from SQLite
        recalled_nodes: list[dict[str, Any]] = []
        
        conn = cls._get_sqlite_conn()
        try:
            for nid, rrf_score in sorted_candidates:
                if rrf_score < relevance_floor:
                    continue

                row = conn.execute("SELECT * FROM hm_semantic_nodes WHERE id = ?", (nid,)).fetchone()
                if not row:
                    log_event(f"semantic_memory: consistency warning - vector index contains orphan ID {nid}")
                    continue

                record = dict(row)
                record["source_episode_ids"] = json.loads(record["source_episode_ids"])
                record["rrf_score"] = rrf_score

                recalled_nodes.append(record)

                if len(recalled_nodes) >= limit:
                    break
        finally:
            conn.close()

        return recalled_nodes

    # ----- Vector GC -----

    @classmethod
    def run_vector_gc(cls) -> int:
        """Finds and deletes any vector IDs in Chroma that are missing from SQLite."""
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
                    
                    rows = conn.execute(
                        f"SELECT id FROM hm_semantic_nodes WHERE id IN ({placeholders})", chunk
                    ).fetchall()
                    sqlite_present_ids = {r["id"] for r in rows}

                    orphans = [cid for cid in chunk if cid not in sqlite_present_ids]
                    if orphans:
                        collection.delete(ids=orphans)
                        orphans_purged += len(orphans)
                        log_event(f"semantic_memory: GC deleted {len(orphans)} orphan vectors from Chroma")
            finally:
                conn.close()
        except Exception as e:
            log_event(f"semantic_memory: GC sweep failed: {e}")
        return orphans_purged

    # ----- Query Cache & GC Scheduler -----

    @classmethod
    def _get_embedding_fn(cls) -> Any:
        with cls._lock:
            if cls._emb_fn is None:
                cls._emb_fn = DefaultEmbeddingFunction()
            return cls._emb_fn

    @classmethod
    def _get_query_embedding(cls, query: str) -> list[float]:
        """Retrieve the query embedding, using a thread-safe local LRU cache if available."""
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
    def _gc_scheduler_loop(cls) -> None:
        """Background daemon scheduler that runs vector GC every 10 minutes (600s)."""
        while not cls._stop_event.is_set():
            for _ in range(600):
                if cls._stop_event.is_set():
                    break
                time.sleep(1.0)
            if cls._stop_event.is_set():
                break

            try:
                cls.run_vector_gc()
            except Exception as e:
                log_event(f"semantic_memory: scheduled GC sweep failed: {e}")
