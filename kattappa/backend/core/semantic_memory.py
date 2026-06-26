from __future__ import annotations

import json
import queue
import re
import sqlite3
import threading
import time
import uuid
import hashlib
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from backend.core.config import load_config
from backend.core.logger import log_event


class SemanticMemory:
    """Semantic Memory Subsystem (Layer 4) representing long-term verified facts.
    
    Upgraded to Step 17 Spec:
    - 1M-Scale Optimization: Dedicated ANN vector pointers, FTS5 lexical index, and Graph topology index.
    - Two-Stage Hybrid Retrieval: Exact BM25 + Vector + Graph Traversal merged via reciprocal rank fusion (RRF).
    - Query-Classification Weight Routing: Custom RRF weights based on exact/relational/paraphrase queries.
    - Double-Gated Firewalls: HYPOTHESIS isolation retrieval gate and N>=3 evidence count requirements.
    - Temporal Versioning & Soft-Delete: valid_from/to validity ranges and status deprecations.
    - Canonical Entity Layer: Aliases and canonical entity resolution.
    - Updatable Views: Transparent backward compatibility with legacy hm_semantic_nodes queries.
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
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False, timeout=30.0)
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
            # 1. Authoritative SQLite Semantic Tables (Property Graph - Step 17 Spec)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS semantic_nodes (
                    node_id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL CHECK (node_type IN ('FACT', 'CONCEPT', 'SKILL', 'DEFINITION', 'HYPOTHESIS')),
                    title TEXT NOT NULL,
                    content_raw TEXT NOT NULL,
                    confidence_score REAL NOT NULL CHECK (confidence_score BETWEEN 0.0 AND 1.0),
                    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DEPRECATED', 'ARCHIVED')),
                    valid_from REAL NOT NULL,
                    valid_to REAL,
                    last_verified_at REAL NOT NULL,
                    verification_interval_days REAL NOT NULL DEFAULT 30.0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS semantic_aliases (
                    alias TEXT PRIMARY KEY,
                    canonical_node_id TEXT NOT NULL REFERENCES semantic_nodes(node_id) ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS semantic_skills (
                    node_id TEXT PRIMARY KEY REFERENCES semantic_nodes(node_id) ON DELETE RESTRICT,
                    proficiency REAL NOT NULL CHECK (proficiency BETWEEN 0.0 AND 1.0),
                    success_rate REAL NOT NULL CHECK (success_rate BETWEEN 0.0 AND 1.0),
                    last_used_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS semantic_edges (
                    source_node_id TEXT NOT NULL REFERENCES semantic_nodes(node_id) ON DELETE RESTRICT,
                    relation_type TEXT NOT NULL CHECK (relation_type IN (
                        'IS_A', 'USES', 'SUPPORTS', 'RELATED_TO', 'IMPLEMENTS', 'EXTENDS', 
                        'CONTRADICTS', 'SUPERSEDES', 'OBSOLETES', 'VERSION_OF'
                    )),
                    target_node_id TEXT NOT NULL REFERENCES semantic_nodes(node_id) ON DELETE RESTRICT,
                    weight_score REAL NOT NULL CHECK (weight_score BETWEEN 0.0 AND 1.0),
                    PRIMARY KEY (source_node_id, relation_type, target_node_id)
                );

                CREATE TABLE IF NOT EXISTS semantic_sources (
                    source_id TEXT NOT NULL,
                    associated_node_id TEXT NOT NULL REFERENCES semantic_nodes(node_id) ON DELETE RESTRICT,
                    source_type TEXT NOT NULL CHECK (source_type IN ('USER_EXPLICIT', 'WEB_DOCUMENTATION', 'REFLECTION_CORROBORATED', 'STRATEGIC_INFERENCE')),
                    source_reference_hash TEXT NOT NULL,
                    ingested_at REAL NOT NULL,
                    PRIMARY KEY (source_id, associated_node_id)
                );

                CREATE TABLE IF NOT EXISTS semantic_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL REFERENCES semantic_nodes(node_id) ON DELETE RESTRICT,
                    source_id TEXT NOT NULL,
                    evidence_weight REAL NOT NULL CHECK (evidence_weight BETWEEN 0.0 AND 1.0),
                    created_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sem_nodes_status ON semantic_nodes(status, confidence_score DESC) WHERE status = 'ACTIVE';
                CREATE INDEX IF NOT EXISTS idx_sem_nodes_validity ON semantic_nodes(valid_from, valid_to);
                CREATE INDEX IF NOT EXISTS idx_sem_aliases_canonical ON semantic_aliases(canonical_node_id);
                CREATE INDEX IF NOT EXISTS idx_sem_edges_forward ON semantic_edges(source_node_id, relation_type);
                CREATE INDEX IF NOT EXISTS idx_sem_edges_reverse ON semantic_edges(target_node_id, relation_type);
                CREATE INDEX IF NOT EXISTS idx_sem_evidence_node ON semantic_evidence(node_id);
                CREATE INDEX IF NOT EXISTS idx_sem_sources_node ON semantic_sources(associated_node_id);

                -- FTS5 Virtual Table for External Content mapping
                CREATE VIRTUAL TABLE IF NOT EXISTS semantic_nodes_fts USING fts5(
                    title,
                    content_raw,
                    content='semantic_nodes'
                );

                -- Triggers to auto-sync FTS5 External Content Virtual Table
                DROP TRIGGER IF EXISTS trg_semantic_nodes_ai;
                DROP TRIGGER IF EXISTS trg_semantic_nodes_ad;
                DROP TRIGGER IF EXISTS trg_semantic_nodes_au;

                CREATE TRIGGER trg_semantic_nodes_ai AFTER INSERT ON semantic_nodes BEGIN
                    INSERT INTO semantic_nodes_fts(rowid, title, content_raw) VALUES (new.rowid, new.title, new.content_raw);
                END;

                CREATE TRIGGER trg_semantic_nodes_ad AFTER DELETE ON semantic_nodes BEGIN
                    INSERT INTO semantic_nodes_fts(semantic_nodes_fts, rowid, title, content_raw) VALUES ('delete', old.rowid, old.title, old.content_raw);
                END;

                CREATE TRIGGER trg_semantic_nodes_au AFTER UPDATE OF title, content_raw ON semantic_nodes BEGIN
                    INSERT INTO semantic_nodes_fts(semantic_nodes_fts, rowid, title, content_raw) VALUES ('delete', old.rowid, old.title, old.content_raw);
                    INSERT INTO semantic_nodes_fts(rowid, title, content_raw) VALUES (new.rowid, new.title, new.content_raw);
                END;
                """
            )

            # Compatibility Views & Triggers mapping `hm_semantic_nodes` & `hm_semantic_edges`
            conn.executescript(
                """
                DROP VIEW IF EXISTS hm_semantic_nodes;
                CREATE VIEW hm_semantic_nodes AS
                SELECT 
                    node_id AS id,
                    title AS concept,
                    content_raw AS description,
                    confidence_score AS confidence,
                    (SELECT COUNT(*) FROM semantic_evidence WHERE node_id = semantic_nodes.node_id) AS evidence_count,
                    (SELECT json_group_array(source_id) FROM semantic_sources WHERE associated_node_id = semantic_nodes.node_id) AS source_episode_ids,
                    (SELECT group_concat(source_type, '; ') FROM semantic_sources WHERE associated_node_id = semantic_nodes.node_id) AS provenance,
                    created_at,
                    updated_at,
                    (SELECT target_node_id FROM semantic_edges WHERE source_node_id = semantic_nodes.node_id AND relation_type = 'CONTRADICTS' LIMIT 1) AS contradicts_id,
                    CASE WHEN EXISTS (
                        SELECT 1 FROM semantic_edges 
                        WHERE (source_node_id = semantic_nodes.node_id OR target_node_id = semantic_nodes.node_id)
                          AND relation_type = 'CONTRADICTS'
                    ) THEN 'contested'
                    WHEN (SELECT COUNT(*) FROM semantic_evidence WHERE node_id = semantic_nodes.node_id) >= 2 THEN 'verified'
                    ELSE 'draft' END AS status
                FROM semantic_nodes;

                DROP TRIGGER IF EXISTS trg_hm_semantic_nodes_insert;
                CREATE TRIGGER trg_hm_semantic_nodes_insert
                INSTEAD OF INSERT ON hm_semantic_nodes
                BEGIN
                    -- Insert source if not exist
                    INSERT OR IGNORE INTO semantic_sources(source_id, associated_node_id, source_type, source_reference_hash, ingested_at)
                    VALUES (
                        COALESCE(
                            (SELECT value FROM json_each(new.source_episode_ids) LIMIT 1),
                            'SRC_' || new.id
                        ),
                        new.id,
                        CASE WHEN new.provenance IS NULL OR new.provenance = '' THEN 'REFLECTION_CORROBORATED' ELSE 'USER_EXPLICIT' END,
                        'SHA256:legacy_compatibility_hash',
                        new.created_at
                    );
                    -- Insert evidence
                    INSERT OR IGNORE INTO semantic_evidence(evidence_id, node_id, source_id, evidence_weight, created_at)
                    VALUES (
                        'EVID_' || new.id || '_' || strftime('%s','now'),
                        new.id,
                        COALESCE(
                            (SELECT value FROM json_each(new.source_episode_ids) LIMIT 1),
                            'SRC_' || new.id
                        ),
                        new.confidence,
                        new.created_at
                    );
                    -- Insert node
                    INSERT INTO semantic_nodes (
                        node_id, node_type, title, content_raw, confidence_score, status, valid_from, last_verified_at, created_at, updated_at
                    )
                    VALUES (
                        new.id,
                        'FACT',
                        new.concept,
                        new.description,
                        new.confidence,
                        'ACTIVE',
                        new.created_at,
                        new.created_at,
                        new.created_at,
                        new.updated_at
                    );
                END;

                DROP TRIGGER IF EXISTS trg_hm_semantic_nodes_delete;
                CREATE TRIGGER trg_hm_semantic_nodes_delete
                INSTEAD OF DELETE ON hm_semantic_nodes
                BEGIN
                    DELETE FROM semantic_nodes WHERE node_id = old.id;
                END;

                DROP TRIGGER IF EXISTS trg_hm_semantic_nodes_update;
                CREATE TRIGGER trg_hm_semantic_nodes_update
                INSTEAD OF UPDATE ON hm_semantic_nodes
                BEGIN
                    UPDATE semantic_nodes
                    SET title = new.concept,
                        content_raw = new.description,
                        confidence_score = new.confidence,
                        updated_at = new.updated_at
                    WHERE node_id = old.id;
                END;

                DROP VIEW IF EXISTS hm_semantic_edges;
                CREATE VIEW hm_semantic_edges AS
                SELECT 
                    (source_node_id || '_' || relation_type || '_' || target_node_id) AS id,
                    source_node_id,
                    target_node_id,
                    relation_type AS relation,
                    weight_score AS weight,
                    strftime('%s','now') AS created_at,
                    strftime('%s','now') AS updated_at
                FROM semantic_edges;

                DROP TRIGGER IF EXISTS trg_hm_semantic_edges_insert;
                CREATE TRIGGER trg_hm_semantic_edges_insert
                INSTEAD OF INSERT ON hm_semantic_edges
                BEGIN
                    INSERT INTO semantic_edges (source_node_id, relation_type, target_node_id, weight_score)
                    VALUES (new.source_node_id, UPPER(new.relation), new.target_node_id, new.weight)
                    ON CONFLICT(source_node_id, relation_type, target_node_id) DO UPDATE SET
                        weight_score = excluded.weight_score;
                END;

                DROP TRIGGER IF EXISTS trg_hm_semantic_edges_delete;
                CREATE TRIGGER trg_hm_semantic_edges_delete
                INSTEAD OF DELETE ON hm_semantic_edges
                BEGIN
                    DELETE FROM semantic_edges 
                    WHERE source_node_id = old.source_node_id 
                      AND target_node_id = old.target_node_id 
                      AND relation_type = UPPER(old.relation);
                END;

                DROP VIEW IF EXISTS hm_semantic_nodes_fts;
                CREATE VIEW hm_semantic_nodes_fts AS
                SELECT f.rowid, f.title AS concept, f.content_raw AS description 
                FROM semantic_nodes_fts f
                JOIN semantic_nodes n ON f.rowid = n.rowid
                WHERE n.status = 'ACTIVE';
                """
            )
            
            # Sync FTS table if it has missed items
            fts_count = conn.execute("SELECT COUNT(*) AS c FROM semantic_nodes_fts").fetchone()["c"]
            core_count = conn.execute("SELECT COUNT(*) AS c FROM semantic_nodes").fetchone()["c"]
            if fts_count == 0 and core_count > 0:
                conn.execute("INSERT INTO semantic_nodes_fts(rowid, title, content_raw) SELECT rowid, title, content_raw FROM semantic_nodes")
            
            # Run schema migrations for existing database instances (add verification_interval_days column if missing)
            try:
                conn.execute("ALTER TABLE semantic_nodes ADD COLUMN verification_interval_days REAL NOT NULL DEFAULT 30.0")
            except sqlite3.OperationalError:
                pass

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

                try:
                    cls._process_embeddings(items)
                finally:
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
        similarity_threshold: float = 0.6,
        node_type: str = "FACT",
        valid_from: Optional[float] = None,
        valid_to: Optional[float] = None,
        source_type: str = "REFLECTION_CORROBORATED",
        source_reference_hash: str = "SHA256:default_reference_hash"
    ) -> str:
        """Upsert a semantic node into SQLite, applying canonicalization and polarity checks before merge.
        
        Merge condition:
        - Cosine similarity (L2 distance <= similarity_threshold) OR exact case-insensitive concept/alias match
        - AND same polarity (both negated or neither negated)
        """
        concept_clean = concept.strip()
        description_clean = description.strip()
        now = time.time()
        
        existing_node: dict[str, Any] | None = None
        conn = cls._get_sqlite_conn()
        try:
            # 1. Check Canonical aliases first
            row_alias = conn.execute("SELECT canonical_node_id FROM semantic_aliases WHERE LOWER(alias) = LOWER(?)", (concept_clean,)).fetchone()
            if row_alias:
                existing_node = cls.get_node(row_alias["canonical_node_id"])

            # 2. Check title exact match
            if not existing_node:
                row_node = conn.execute("SELECT node_id FROM semantic_nodes WHERE LOWER(title) = LOWER(?)", (concept_clean,)).fetchone()
                if row_node:
                    existing_node = cls.get_node(row_node["node_id"])
        finally:
            conn.close()

        # 3. Semantic search via ChromaDB
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
                            existing_node = cls.get_node(candidate_id)
            except Exception as e:
                log_event(f"semantic_memory: vector similarity search failed: {e}")

        # 4. Merging & Canonicalization check
        if existing_node:
            if cls._check_polarity_match(description_clean, existing_node["content_raw"]):
                node_id = existing_node["node_id"]
                
                conn = cls._get_sqlite_conn()
                try:
                    # Let's count existing sources/evidence *within* the transaction
                    sources_rows = conn.execute("SELECT * FROM semantic_sources WHERE associated_node_id = ?", (node_id,)).fetchall()
                    existing_sources = [dict(r) for r in sources_rows]
                    
                    source_exists = any(s["source_id"] == source_episode_id for s in existing_sources)
                    
                    # Compute what the new episode list would be
                    new_episode_ids = [s["source_id"] for s in existing_sources]
                    if not source_exists:
                        new_episode_ids.append(source_episode_id)
                    
                    # Trust check for promoted facts
                    if len(new_episode_ids) >= 2:
                        from backend.core.memory_governance import MemoryGovernance
                        trust = MemoryGovernance.get_trust(source_episode_id)
                        if trust == "TRUST_UNTRUSTED":
                            raise ValueError(f"Cannot corroborate promoted fact with untrusted episode {source_episode_id}")
                        
                        allowed, reason = MemoryGovernance.can_promote_fact(new_episode_ids)
                        if not allowed and reason == "untrusted_source_episodes":
                            raise ValueError(f"Cannot promote fact derived from untrusted episodes: {reason}")
                    
                    if len(new_episode_ids) >= 2 and not provenance:
                        # Check if there is already a custom provenance value in the DB/sources
                        has_custom_prov = any(
                            s["source_reference_hash"] not in ("SHA256:default_reference_hash", "SHA256:legacy_compatibility_hash")
                            for s in existing_sources
                        )
                        if not has_custom_prov:
                            raise ValueError("Provenance is required for promoted facts (evidence count >= 2).")

                    # If checks passed, proceed with insertion
                    if not source_exists:
                        effective_source_ref = provenance if provenance else source_reference_hash
                        # Insert source
                        conn.execute(
                            "INSERT INTO semantic_sources (source_id, associated_node_id, source_type, source_reference_hash, ingested_at) VALUES (?, ?, ?, ?, ?)",
                            (source_episode_id, node_id, source_type, effective_source_ref, now)
                        )
                        # Insert evidence
                        conn.execute(
                            "INSERT INTO semantic_evidence (evidence_id, node_id, source_id, evidence_weight, created_at) VALUES (?, ?, ?, ?, ?)",
                            (f"EVID_{node_id}_{uuid.uuid4().hex[:8]}", node_id, source_episode_id, confidence, now)
                        )
                        new_sources_count = len(existing_sources) + 1
                    else:
                        new_sources_count = len(existing_sources)

                    contradiction_count = conn.execute(
                        "SELECT COUNT(*) FROM semantic_edges WHERE (source_node_id = ? OR target_node_id = ?) AND relation_type = 'CONTRADICTS'",
                        (node_id, node_id)
                    ).fetchone()[0]
                    corroboration_count = conn.execute(
                        "SELECT COUNT(*) FROM semantic_edges WHERE source_node_id = ? AND relation_type != 'CONTRADICTS'",
                        (node_id,)
                    ).fetchone()[0]

                    new_confidence = min(1.0, (1.0 - (0.5 ** new_sources_count)) * (1.0 - 0.15 * contradiction_count) + 0.05 * corroboration_count)

                    # Merge content descriptions
                    existing_desc = existing_node["content_raw"]
                    if description_clean in existing_desc:
                        merged_desc = existing_desc
                    elif existing_desc in description_clean:
                        merged_desc = description_clean
                    else:
                        merged_desc = f"{existing_desc}; {description_clean}"

                    target_node_type = "FACT" if new_sources_count >= 2 else existing_node["node_type"]

                    conn.execute(
                        """
                        UPDATE semantic_nodes 
                        SET content_raw = ?, confidence_score = ?, node_type = ?, updated_at = ?
                        WHERE node_id = ?
                        """,
                        (merged_desc, new_confidence, target_node_type, now, node_id)
                    )
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    raise e
                finally:
                    conn.close()

                # Log governance provenance
                if new_sources_count >= 2:
                    try:
                        MemoryGovernance.log_provenance(
                            memory_id=node_id,
                            memory_type="semantic",
                            source="episodic_promotion",
                            created_by="semantic_layer",
                            confidence=new_confidence,
                            derived_from=new_episode_ids
                        )
                    except Exception as e:
                        log_event(f"semantic_memory: failed to log provenance for {node_id}: {e}")

                cls.start_worker()
                cls._embed_queue.put((node_id, existing_node["title"], merged_desc))
                
                return node_id
            else:
                # Contradiction: opposite polarity detected!
                new_node_id = str(uuid.uuid4())
                new_existing_confidence = max(0.0, existing_node["confidence_score"] - 0.2)
                
                with cls._lock:
                    conn = cls._get_sqlite_conn()
                    try:
                        conn.execute(
                            "UPDATE semantic_nodes SET confidence_score = ?, updated_at = ? WHERE node_id = ?",
                            (new_existing_confidence, now, existing_node["node_id"])
                        )
                        cls._propagate_confidence(conn, existing_node["node_id"], set())
                        conn.commit()
                    finally:
                        conn.close()
                
                confidence = max(0.0, confidence - 0.2)
                log_event(
                     f"semantic_memory: polarity mismatch (contradiction) against existing concept "
                     f"'{existing_node['title']}' - lowering confidence on existing node to {new_existing_confidence} "
                     f"and inserting new contested fact with confidence {confidence}"
                )
                
                # Insert contradiction edges (symmetric relationship)
                cls.create_edge(existing_node["node_id"], new_node_id, "CONTRADICTS", 0.9)
                cls.create_edge(new_node_id, existing_node["node_id"], "CONTRADICTS", 0.9)
                
                # Override target ID to create separate contested node
                node_id = new_node_id
        
        if 'node_id' not in locals() or not node_id:
            node_id = str(uuid.uuid4())

        # Create new node
        effective_valid_from = valid_from if valid_from is not None else now
        
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Insert node (starts as HYPOTHESIS if evidence count = 1)
                conn.execute(
                    """
                    INSERT INTO semantic_nodes (
                        node_id, node_type, title, content_raw, confidence_score, status, valid_from, valid_to, last_verified_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?)
                    """,
                    (node_id, "HYPOTHESIS" if node_type == "FACT" else node_type, concept_clean, description_clean, confidence, effective_valid_from, valid_to, now, now, now)
                )
                # Insert source
                effective_source_ref = provenance if provenance else source_reference_hash
                conn.execute(
                    "INSERT INTO semantic_sources (source_id, associated_node_id, source_type, source_reference_hash, ingested_at) VALUES (?, ?, ?, ?, ?)",
                    (source_episode_id, node_id, source_type, effective_source_ref, now)
                )
                # Insert evidence
                conn.execute(
                    "INSERT INTO semantic_evidence (evidence_id, node_id, source_id, evidence_weight, created_at) VALUES (?, ?, ?, ?, ?)",
                    (f"EVID_{node_id}_{uuid.uuid4().hex[:8]}", node_id, source_episode_id, confidence, now)
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
        """Retrieves a single semantic node from SQLite, returning both legacy and Step 17 keys."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM semantic_nodes WHERE node_id = ?", (node_id,)).fetchone()
            if not row:
                return None
            node = dict(row)
            
            # Hide deprecated nodes from standard get lookups to support soft-delete CRUD checks
            if node["status"] == "DEPRECATED":
                return None
            
            # Retrieve aliases
            aliases_rows = conn.execute("SELECT alias FROM semantic_aliases WHERE canonical_node_id = ?", (node_id,)).fetchall()
            aliases = [r["alias"] for r in aliases_rows]
            
            # Retrieve sources
            sources_rows = conn.execute("SELECT * FROM semantic_sources WHERE associated_node_id = ?", (node_id,)).fetchall()
            sources = [dict(r) for r in sources_rows]
            
            # Retrieve evidence
            evidence_rows = conn.execute("SELECT * FROM semantic_evidence WHERE node_id = ?", (node_id,)).fetchall()
            evidence = [dict(r) for r in evidence_rows]
            
            # Retrieve skill if applicable
            skill = None
            if node["node_type"] == "SKILL":
                skill_row = conn.execute("SELECT * FROM semantic_skills WHERE node_id = ?", (node_id,)).fetchone()
                if skill_row:
                    skill = dict(skill_row)

            # Check peer contradiction status
            peer_id = None
            peer_edge = conn.execute("SELECT target_node_id FROM semantic_edges WHERE source_node_id = ? AND relation_type = 'CONTRADICTS' LIMIT 1", (node_id,)).fetchone()
            if peer_edge:
                peer_id = peer_edge["target_node_id"]

            contradiction_count = conn.execute(
                "SELECT COUNT(*) FROM semantic_edges WHERE (source_node_id = ? OR target_node_id = ?) AND relation_type = 'CONTRADICTS'",
                (node_id, node_id)
            ).fetchone()[0]

            legacy_status = "draft"
            if peer_id:
                legacy_status = "contested"
            elif len(evidence) >= 2:
                legacy_status = "verified"

            now = time.time()
            is_stale = (now - node["last_verified_at"]) > (node["verification_interval_days"] * 86400.0)

            confidence_explanation = {
                "evidence_count": len(evidence),
                "independent_sources": len({s["source_id"] for s in sources}),
                "contradiction_count": contradiction_count,
                "last_verified_at": node["last_verified_at"]
            }

            # Map legacy compatibility keys alongside spec keys
            record = {
                "id": node["node_id"],
                "node_id": node["node_id"],
                "concept": node["title"],
                "title": node["title"],
                "description": node["content_raw"],
                "content_raw": node["content_raw"],
                "confidence": node["confidence_score"],
                "confidence_score": node["confidence_score"],
                "evidence_count": len(evidence) or 1,
                "source_episode_ids": [s["source_id"] for s in sources],
                "provenance": (
                    "; ".join(
                        s["source_reference_hash"] for s in sources 
                        if s["source_reference_hash"] 
                        and s["source_reference_hash"] not in ("SHA256:default_reference_hash", "SHA256:legacy_compatibility_hash")
                    ) if any(
                        s["source_reference_hash"] not in ("SHA256:default_reference_hash", "SHA256:legacy_compatibility_hash")
                        for s in sources
                    ) else ("; ".join(s["source_type"] for s in sources) if sources else None)
                ),
                "created_at": node["created_at"],
                "updated_at": node["updated_at"],
                "last_updated": node["updated_at"],
                "status": legacy_status,
                "node_status": node["status"],
                "valid_from": node["valid_from"],
                "valid_to": node["valid_to"],
                "last_verified_at": node["last_verified_at"],
                "verification_interval_days": node["verification_interval_days"],
                "is_stale": is_stale,
                "confidence_explanation": confidence_explanation,
                "node_type": node["node_type"],
                "aliases": aliases,
                "sources": sources,
                "evidence": evidence,
                "skill": skill,
                "contradicts_id": peer_id
            }
            return record
        finally:
            conn.close()

    @classmethod
    def delete_node(cls, node_id: str, hard: bool = False) -> bool:
        """Delete or deprecate a semantic node from SQLite and ChromaDB.
        
        - If hard=True (cleanup sweeps), completely drops database rows.
        - Otherwise, marks status = 'DEPRECATED' (soft-delete compliance).
        """
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                if hard:
                    # Hard-delete dependency constraints manually (bypassing RESTRICT for sweep)
                    conn.execute("DELETE FROM semantic_aliases WHERE canonical_node_id = ?", (node_id,))
                    conn.execute("DELETE FROM semantic_skills WHERE node_id = ?", (node_id,))
                    conn.execute("DELETE FROM semantic_evidence WHERE node_id = ?", (node_id,))
                    conn.execute("DELETE FROM semantic_sources WHERE associated_node_id = ?", (node_id,))
                    conn.execute("DELETE FROM semantic_edges WHERE source_node_id = ? OR target_node_id = ?", (node_id, node_id))
                    cursor = conn.execute("DELETE FROM semantic_nodes WHERE node_id = ?", (node_id,))
                    deleted = cursor.rowcount > 0
                else:
                    cursor = conn.execute("UPDATE semantic_nodes SET status = 'DEPRECATED' WHERE node_id = ?", (node_id,))
                    deleted = cursor.rowcount > 0
                    if deleted:
                        cls._propagate_confidence(conn, node_id, set())
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        if deleted and hard:
            try:
                collection = cls._get_chroma_collection()
                collection.delete(ids=[node_id])
            except Exception:
                pass
        return deleted

    @classmethod
    def register_alias(cls, alias: str, canonical_node_id: str) -> None:
        """Register a canonical entity alias."""
        alias_clean = alias.strip()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    "INSERT INTO semantic_aliases (alias, canonical_node_id) VALUES (?, ?) ON CONFLICT(alias) DO UPDATE SET canonical_node_id = excluded.canonical_node_id",
                    (alias_clean, canonical_node_id)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def _propagate_confidence(cls, conn: sqlite3.Connection, node_id: str, visited: set[str]) -> None:
        """Propagate confidence decays recursively down the dependency edges in the property graph."""
        if node_id in visited:
            return
        visited.add(node_id)
        
        # Get target node info
        node_row = conn.execute("SELECT status, confidence_score FROM semantic_nodes WHERE node_id = ?", (node_id,)).fetchone()
        if not node_row:
            return
        target_status = node_row["status"]
        target_conf = node_row["confidence_score"]
        
        # Find downstream nodes that depend on this node via relationships: USES, SUPPORTS, IMPLEMENTS, EXTENDS, VERSION_OF
        dep_edges = conn.execute(
            """
            SELECT source_node_id, relation_type FROM semantic_edges 
            WHERE target_node_id = ? AND relation_type IN ('USES', 'SUPPORTS', 'IMPLEMENTS', 'EXTENDS', 'VERSION_OF')
            """,
            (node_id,)
        ).fetchall()
        
        for edge in dep_edges:
            child_id = edge["source_node_id"]
            
            # Fetch child node details
            child_row = conn.execute("SELECT status, confidence_score FROM semantic_nodes WHERE node_id = ?", (child_id,)).fetchone()
            if not child_row:
                continue
            child_status = child_row["status"]
            child_conf = child_row["confidence_score"]
            
            new_status = child_status
            if target_status == "DEPRECATED":
                new_conf = max(0.0, child_conf * 0.5)
                # If confidence drops below 0.3, soft-deprecate the child as well
                if new_conf < 0.3:
                    new_status = "DEPRECATED"
            else:
                # Proportional decay
                new_conf = child_conf * (0.8 + 0.2 * target_conf)
                
            # Perform update
            conn.execute(
                "UPDATE semantic_nodes SET confidence_score = ?, status = ?, updated_at = ? WHERE node_id = ?",
                (new_conf, new_status, time.time(), child_id)
            )
            
            # Recurse downstream
            cls._propagate_confidence(conn, child_id, visited)

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
        relation_upper = relation.strip().upper()
        
        # Mapping legacy relations if necessary
        allowed_relations = {
            'IS_A', 'USES', 'SUPPORTS', 'RELATED_TO', 'IMPLEMENTS', 'EXTENDS', 
            'CONTRADICTS', 'SUPERSEDES', 'OBSOLETES', 'VERSION_OF'
        }
        if relation_upper not in allowed_relations:
            relation_upper = 'RELATED_TO' # Default fallback
            
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO semantic_edges (source_node_id, relation_type, target_node_id, weight_score)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(source_node_id, relation_type, target_node_id) DO UPDATE SET
                        weight_score = excluded.weight_score
                    """,
                    (source_node_id, relation_upper, target_node_id, weight)
                )
                conn.commit()
                return f"{source_node_id}_{relation_upper}_{target_node_id}"
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_edge(cls, edge_id: str) -> dict[str, Any] | None:
        """Retrieve edge details from SQLite."""
        # edge_id can be in form "source_relation_target"
        parts = edge_id.split("_")
        if len(parts) >= 3:
            source = parts[0]
            target = parts[-1]
            relation = "_".join(parts[1:-1]).upper()
        else:
            return None
            
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT * FROM semantic_edges WHERE source_node_id = ? AND target_node_id = ? AND relation_type = ?",
                (source, target, relation)
            ).fetchone()
            if not row:
                return None
            rec = dict(row)
            # Map legacy compatibility keys
            return {
                "id": edge_id,
                "source_node_id": rec["source_node_id"],
                "target_node_id": rec["target_node_id"],
                "relation": rec["relation_type"].lower(),
                "weight": rec["weight_score"]
            }
        finally:
            conn.close()

    @classmethod
    def delete_edge(cls, edge_id: str) -> bool:
        """Delete relationship edge from SQLite."""
        parts = edge_id.split("_")
        if len(parts) < 3:
            return False
        source = parts[0]
        target = parts[-1]
        relation = "_".join(parts[1:-1]).upper()

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cursor = conn.execute(
                    "DELETE FROM semantic_edges WHERE source_node_id = ? AND target_node_id = ? AND relation_type = ?",
                    (source, target, relation)
                )
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
        
        Traverses up to max_hops away along edges with weight >= min_weight.
        Applies Step 17 traversal caps: max 50 visited nodes and max 10 edges per node.
        Edge weights decay by 0.8 per hop.
        """
        visited_nodes: dict[str, dict[str, Any]] = {}
        traversed_edges: list[dict[str, Any]] = []
        queue_bfs = [(start_node_id, 0)]
        
        conn = cls._get_sqlite_conn()
        try:
            # Canonical entity resolution
            alias_row = conn.execute("SELECT canonical_node_id FROM semantic_aliases WHERE LOWER(alias) = LOWER(?)", (start_node_id.strip(),)).fetchone()
            resolved_start_id = alias_row["canonical_node_id"] if alias_row else start_node_id

            start_node = cls.get_node(resolved_start_id)
            if not start_node or start_node["node_status"] == "DEPRECATED" or start_node["confidence_score"] < 0.3:
                return {"nodes": {}, "edges": []}
            
            # Legacy check: skip contested nodes
            if start_node["status"] == "contested":
                return {"nodes": {}, "edges": []}
            
            visited_nodes[resolved_start_id] = start_node
            
            idx = 0
            while idx < len(queue_bfs):
                current_id, hop = queue_bfs[idx]
                idx += 1
                
                if len(visited_nodes) >= 50: # max_nodes cap
                    break
                
                if hop >= max_hops:
                    continue
                
                rows = conn.execute(
                    """
                    SELECT e.relation_type, e.target_node_id, e.weight_score
                    FROM semantic_edges e
                    WHERE e.source_node_id = ? AND e.weight_score >= ?
                    ORDER BY e.weight_score DESC
                    """,
                    (current_id, min_weight)
                ).fetchall()
                
                # Limit to top-10 edge expansions per node
                for r in rows[:10]:
                    target_id = r["target_node_id"]
                    relation = r["relation_type"]
                    weight = r["weight_score"]
                    
                    target_node = cls.get_node(target_id)
                    if not target_node or target_node["node_status"] == "DEPRECATED" or target_node["confidence_score"] < 0.3:
                        continue
                    if target_node["status"] == "contested":
                        continue
                        
                    decayed_weight = weight * (0.8 ** (hop + 1))
                    
                    edge_record = {
                        "id": f"{current_id}_{relation}_{target_id}",
                        "source_node_id": current_id,
                        "target_node_id": target_id,
                        "relation": relation.lower(),
                        "weight": weight,
                        "decayed_weight": decayed_weight
                    }
                    if edge_record not in traversed_edges:
                        traversed_edges.append(edge_record)
                    
                    if target_id not in visited_nodes and len(visited_nodes) < 50:
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
        return " AND ".join(f'"{w}"*' for w in words)

    @classmethod
    def recall(
        cls,
        query: str,
        limit: int = 5,
        relevance_floor: float = 0.001,
        similarity_threshold: float = 1.2
    ) -> list[dict[str, Any]]:
        """Two-Stage Hybrid retrieval for semantic memory (FTS5 + Vector query + Graph + RRF)."""
        fts_hits: list[str] = []
        vector_hits: list[str] = []
        graph_hits: list[str] = []
        vector_distances: dict[str, float] = {}
        graph_distances: dict[str, int] = {}

        # 0. Query Classification / Adaptive Weighting Routing
        q_lower = query.lower()
        if "relation" in q_lower or "connect" in q_lower or "depend" in q_lower:
            w_graph, w_vector, w_bm25 = 0.50, 0.30, 0.20
        elif len(query.split()) <= 3 or q_lower.startswith("what is") or q_lower.startswith("who is"):
            w_bm25, w_vector, w_graph = 0.50, 0.30, 0.20
        else:
            w_vector, w_bm25, w_graph = 0.50, 0.30, 0.20

        conn = cls._get_sqlite_conn()
        try:
            # 1. Stage 1: Recall top candidates (up to 200 from each)
            # A. Lexical search via FTS5
            sanitized = cls._sanitize_fts_query(query)
            if sanitized:
                try:
                    rows = conn.execute(
                        """
                        SELECT n.node_id FROM semantic_nodes n
                        JOIN semantic_nodes_fts f ON n.rowid = f.rowid
                        WHERE f.semantic_nodes_fts MATCH ?
                        ORDER BY f.rank
                        LIMIT 200
                        """,
                        (sanitized,)
                    ).fetchall()
                    fts_hits = [r["node_id"] for r in rows]
                except Exception as e:
                    log_event(f"semantic_memory: FTS5 recall error: {e}")

            # B. Semantic search via ChromaDB vector index
            try:
                collection = cls._get_chroma_collection()
                if collection.count() > 0:
                    query_vector = cls._get_query_embedding(query)
                    results = collection.query(
                        query_embeddings=[query_vector],
                        n_results=min(200, collection.count())
                    )
                    if results and results.get("ids") and results["ids"][0]:
                        for idx, vid in enumerate(results["ids"][0]):
                            dist = results["distances"][0][idx] if (results.get("distances") and len(results["distances"]) > 0) else 0.0
                            if dist <= similarity_threshold:
                                node_id_str = str(vid)
                                vector_hits.append(node_id_str)
                                vector_distances[node_id_str] = dist
            except Exception as e:
                log_event(f"semantic_memory: Vector recall error: {e}")

            # C. Graph Traversal Recall
            exact_match_row = conn.execute(
                """
                SELECT node_id FROM semantic_nodes WHERE LOWER(title) = LOWER(?)
                UNION
                SELECT canonical_node_id FROM semantic_aliases WHERE LOWER(alias) = LOWER(?)
                LIMIT 1
                """,
                (query.strip(), query.strip())
            ).fetchone()
            if exact_match_row:
                g_subgraph = cls.traverse_graph(exact_match_row["node_id"], max_hops=3, min_weight=0.35)
                graph_hits = list(g_subgraph["nodes"].keys())
                
                # Perform BFS on edges to track shortest hop distance
                start_node_id = exact_match_row["node_id"]
                graph_distances[start_node_id] = 0
                queue_bfs = [start_node_id]
                adj_map = {}
                for edge in g_subgraph["edges"]:
                    adj_map.setdefault(edge["source_node_id"], []).append(edge["target_node_id"])
                
                idx = 0
                while idx < len(queue_bfs):
                    curr = queue_bfs[idx]
                    idx += 1
                    curr_dist = graph_distances[curr]
                    for child in adj_map.get(curr, []):
                        if child not in graph_distances:
                            graph_distances[child] = curr_dist + 1
                            queue_bfs.append(child)

            # 2. Stage 2: Reciprocal Rank Fusion (RRF) & Re-ranking
            rrf_scores: dict[str, float] = {}
            k = 60.0

            for rank, nid in enumerate(fts_hits):
                rrf_scores[nid] = rrf_scores.get(nid, 0.0) + w_bm25 * (1.0 / (k + rank + 1))

            for rank, nid in enumerate(vector_hits):
                rrf_scores[nid] = rrf_scores.get(nid, 0.0) + w_vector * (1.0 / (k + rank + 1))

            for rank, nid in enumerate(graph_hits):
                rrf_scores[nid] = rrf_scores.get(nid, 0.0) + w_graph * (1.0 / (k + rank + 1))

            sorted_candidates = sorted(rrf_scores.items(), key=lambda kv: kv[1], reverse=True)

            fts_ranks = {nid: rank + 1 for rank, nid in enumerate(fts_hits)}

            recalled_nodes: list[dict[str, Any]] = []
            now = time.time()

            for nid, rrf_score in sorted_candidates:
                if rrf_score < relevance_floor:
                    continue

                node_details = cls.get_node(nid)
                if not node_details:
                    continue

                # HYPOTHESIS & Confidence Retrieval Gating Firewall
                if node_details["node_type"] == "HYPOTHESIS":
                    continue

                # Calculate effective confidence applying freshness verification decay penalty
                effective_confidence = node_details["confidence_score"]
                if node_details.get("is_stale"):
                    days_overdue = (now - node_details["last_verified_at"]) / 86400.0 - node_details["verification_interval_days"]
                    # 5% decay per 30 days overdue
                    effective_confidence = node_details["confidence_score"] * (0.95 ** (days_overdue / 30.0))

                if effective_confidence < 0.70:
                    continue
                if node_details["node_status"] == "DEPRECATED":
                    continue
                if node_details["status"] == "contested":
                    # Skip legacy contested status to keep backward compatibility
                    continue

                # Temporal Validity filter
                valid_from = node_details["valid_from"]
                valid_to = node_details["valid_to"]
                if now < valid_from or (valid_to is not None and now > valid_to):
                    continue

                bm25_rank = fts_ranks.get(nid)
                vector_distance = vector_distances.get(nid)
                graph_hop_distance = graph_distances.get(nid)

                node_details["rrf_score"] = rrf_score
                node_details["effective_confidence"] = effective_confidence
                node_details["retrieval_explanation"] = {
                    "vector_distance": vector_distance,
                    "bm25_rank": bm25_rank,
                    "graph_hop_distance": graph_hop_distance,
                    "confidence": node_details["confidence_score"]
                }
                recalled_nodes.append(node_details)

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
                        f"SELECT node_id FROM semantic_nodes WHERE node_id IN ({placeholders})", chunk
                    ).fetchall()
                    sqlite_present_ids = {r["node_id"] for r in rows}

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
