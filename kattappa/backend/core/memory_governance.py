from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.core.config import load_config
from backend.core.logger import log_event


class MemoryGovernance:
    """Memory Governance Layer (Control Tower) of the Kattappa Memory System.
    
    Consolidates:
    - Unified trust registry (hm_trust_registry) and normalized trust states.
    - Centralized provenance & lineage registry (hm_provenance).
    - Policy engine (fact promotion rules, procedure gates).
    - Unified background GC scheduler thread (vector GC, archive sweeps, consistency repairs).
    - Audit logs for governance events (hm_governance_events).
    """

    _lock = threading.RLock()
    _schema_ensured = False
    _scheduler_thread: threading.Thread | None = None
    _stop_event = threading.Event()

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
            cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            conn.executescript(
                """
                -- 1. Trust Registry
                CREATE TABLE IF NOT EXISTS hm_trust_registry (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL, -- 'memory', 'file', 'source', 'user'
                    trust_level TEXT NOT NULL, -- 'TRUST_SYSTEM', 'TRUST_USER', 'TRUST_CORROBORATED', 'TRUST_UNVERIFIED', 'TRUST_UNTRUSTED'
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_hm_trust_registry_type ON hm_trust_registry(entity_type);

                -- 2. Provenance Lineage Registry
                CREATE TABLE IF NOT EXISTS hm_provenance (
                    id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL, -- 'episodic', 'semantic', 'procedural'
                    source TEXT NOT NULL,      -- 'user', 'chat', 'ocr', 'web', 'system'
                    derived_from TEXT,         -- JSON array of parent memory IDs
                    created_by TEXT NOT NULL,  -- 'system', 'broker', 'compiler'
                    confidence REAL NOT NULL,
                    created_at REAL NOT NULL,
                    metadata_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_hm_provenance_type ON hm_provenance(memory_type);

                -- 3. Governance Events Audit Log
                CREATE TABLE IF NOT EXISTS hm_governance_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,  -- 'GC_SWEEP', 'REPAIR', 'PROMOTION', 'TRUST_VIOLATION'
                    target_id TEXT,
                    details_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_hm_governance_events_type ON hm_governance_events(event_type);
                """
            )
            conn.commit()

    # ----- Trust Registry APIs -----

    @classmethod
    def get_trust(cls, entity_id: str) -> str:
        """Get the trust level of an entity. Defaults to TRUST_UNVERIFIED."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT trust_level FROM hm_trust_registry WHERE id = ?",
                (entity_id,)
            ).fetchone()
            return row["trust_level"] if row else "TRUST_UNVERIFIED"
        finally:
            conn.close()

    @classmethod
    def set_trust(cls, entity_id: str, entity_type: str, trust_level: str) -> None:
        """Registers or updates trust level for an entity in the registry."""
        allowed_trusts = {
            "TRUST_SYSTEM", "TRUST_USER", "TRUST_CORROBORATED",
            "TRUST_UNVERIFIED", "TRUST_UNTRUSTED"
        }
        clean_level = trust_level.strip().upper()
        if clean_level not in allowed_trusts:
            raise ValueError(f"Invalid trust level: {trust_level}")

        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_trust_registry (id, entity_type, trust_level, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        trust_level = excluded.trust_level,
                        updated_at = excluded.updated_at
                    """,
                    (entity_id, entity_type.strip().lower(), clean_level, now)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    # ----- Provenance & Lineage APIs -----

    @classmethod
    def log_provenance(
        cls,
        memory_id: str,
        memory_type: str,
        source: str,
        created_by: str,
        confidence: float,
        derived_from: Optional[list[str]] = None,
        metadata: Optional[dict] = None
    ) -> None:
        """Logs the origin and derivation lineage of a memory record."""
        now = time.time()
        derived_json = json.dumps(derived_from or [])
        meta_json = json.dumps(metadata or {})
        
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_provenance (
                        id, memory_type, source, derived_from, created_by,
                        confidence, created_at, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        confidence = excluded.confidence,
                        derived_from = excluded.derived_from,
                        metadata_json = excluded.metadata_json
                    """,
                    (memory_id, memory_type.strip().lower(), source.strip().lower(),
                     derived_json, created_by.strip().lower(), confidence, now, meta_json)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def log_provenance_direct(
        cls,
        cursor: sqlite3.Cursor,
        memory_id: str,
        memory_type: str,
        source: str,
        created_by: str,
        confidence: float,
        derived_from: Optional[list[str]] = None,
        metadata_json: Optional[str] = None
    ) -> None:
        """Logs the origin and derivation lineage directly within an active SQLite transaction."""
        now = time.time()
        derived_json = json.dumps(derived_from or [])
        meta_json = metadata_json or "{}"
        
        cursor.execute(
            """
            INSERT INTO hm_provenance (
                id, memory_type, source, derived_from, created_by,
                confidence, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                confidence = excluded.confidence,
                derived_from = excluded.derived_from,
                metadata_json = excluded.metadata_json
            """,
            (memory_id, memory_type.strip().lower(), source.strip().lower(),
             derived_json, created_by.strip().lower(), confidence, now, meta_json)
        )

    @classmethod
    def get_provenance(cls, memory_id: str) -> dict[str, Any] | None:
        """Retrieves lineage and origin details of a memory record."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM hm_provenance WHERE id = ?", (memory_id,)).fetchone()
            if not row:
                return None
            record = dict(row)
            record["derived_from"] = json.loads(record["derived_from"])
            record["metadata"] = json.loads(record["metadata_json"])
            return record
        finally:
            conn.close()

    # ----- Promotion Policy Engine -----

    @classmethod
    def can_promote_fact(cls, episode_ids: list[str]) -> Tuple[bool, str]:
        """Policy check: verify if a fact can be promoted from a list of supporting episodes.
        
        Rules:
        - Must have at least 2 supporting episodes.
        - Supporting episodes must not be untrusted.
        """
        if len(episode_ids) < 2:
            return False, "insufficient_episode_count"

        # Check trust level of each supporting episode
        conn = cls._get_sqlite_conn()
        try:
            for eid in episode_ids:
                # Check trust registry
                trust = cls.get_trust(eid)
                if trust == "TRUST_UNTRUSTED":
                    return False, "untrusted_source_episodes"

                # Additionally verify provenance if the hm_episodes table exists
                try:
                    row = conn.execute(
                        "SELECT session_id, content FROM hm_episodes WHERE id = ?",
                        (eid,)
                    ).fetchone()
                    if row:
                        prov = cls.get_provenance(eid)
                        if prov and prov["source"] in {"web", "ocr", "untrusted"}:
                            return False, "untrusted_source_episodes"
                except Exception:
                    # hm_episodes table may not exist in all contexts (e.g. governance-only DBs)
                    pass
        finally:
            conn.close()

        return True, "allowed"

    # ----- Governance Audit Events -----

    @classmethod
    def log_governance_event(cls, event_type: str, target_id: Optional[str] = None, details: Optional[dict] = None) -> None:
        """Log a system governance event."""
        now = time.time()
        details_json = json.dumps(details or {})
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_governance_events (timestamp, event_type, target_id, details_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (now, event_type.strip().upper(), target_id, details_json)
                )
                conn.commit()
            except Exception as e:
                log_event(f"memory_governance: failed to log governance event: {e}")
            finally:
                conn.close()

    @classmethod
    def get_governance_events(cls, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve the latest governance events."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hm_governance_events ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ----- Global Centralized Scheduler & GC -----

    @classmethod
    def run_global_gc(cls) -> dict[str, int]:
        """Executes episodic, semantic, and vector garbage collection sequentially."""
        from backend.core.episodic_memory import EpisodicMemory
        from backend.core.semantic_memory import SemanticMemory

        log_event("memory_governance: starting global GC sweep")
        
        # 1. Purge Episodic Vector Orphans
        episodic_purged = EpisodicMemory.run_vector_gc()
        
        # 2. Purge Semantic Vector Orphans
        semantic_purged = SemanticMemory.run_vector_gc()
        
        # 3. Archive Decayed Episodes
        archived_episodes = EpisodicMemory.archive_decayed_episodes(threshold=0.1)

        # 4. Prune expired relationship memory candidates and emotional states
        try:
            from backend.core.relationship_memory import RelationshipMemory
            rel_counts = RelationshipMemory.run_cleanup_sweep()
        except Exception as exc:
            log_event(f"memory_governance: relationship memory cleanup failed: {exc}")
            rel_counts = {"expired_candidates_pruned": 0, "expired_emotions_pruned": 0}

        counts = {
            "episodic_orphans_purged": episodic_purged,
            "semantic_orphans_purged": semantic_purged,
            "decayed_episodes_archived": archived_episodes,
            "expired_candidates_pruned": rel_counts.get("expired_candidates_pruned", 0),
            "expired_emotions_pruned": rel_counts.get("expired_emotions_pruned", 0),
        }

        cls.log_governance_event("GC_SWEEP", details=counts)
        log_event(f"memory_governance: global GC sweep completed: {counts}")
        return counts

    @classmethod
    def start_scheduler(cls) -> None:
        """Starts the central scheduler daemon thread (disables individual loops)."""
        with cls._lock:
            # Stop existing threads if running
            cls.stop_scheduler()
            cls._stop_event.clear()
            cls._scheduler_thread = threading.Thread(target=cls._scheduler_loop, daemon=True)
            cls._scheduler_thread.start()
            log_event("memory_governance: centralized scheduler thread started")

    @classmethod
    def stop_scheduler(cls) -> None:
        """Stops the centralized scheduler thread."""
        with cls._lock:
            cls._stop_event.set()
            if cls._scheduler_thread is not None:
                cls._scheduler_thread.join(timeout=2.0)
                cls._scheduler_thread = None
                log_event("memory_governance: centralized scheduler thread stopped")

    @classmethod
    def _scheduler_loop(cls) -> None:
        """Runs global GC sweep and maintenance validation every 10 minutes (600s)."""
        while not cls._stop_event.is_set():
            # Sleep in 1s increments to respond instantly to stops
            for _ in range(600):
                if cls._stop_event.is_set():
                    break
                time.sleep(1.0)
            if cls._stop_event.is_set():
                break

            try:
                cls.run_global_gc()
                cls.run_cross_layer_validation()
            except Exception as e:
                log_event(f"memory_governance: scheduled global sweeps failed: {e}")

    # ----- Cross-Layer Validation -----

    @classmethod
    def run_cross_layer_validation(cls) -> list[dict[str, Any]]:
        """Verifies referential integrity between SQLite authoritative rows and ChromaDB vectors.
        
        If missing vectors are detected, schedules them for re-indexing (repair).
        """
        from backend.core.episodic_memory import EpisodicMemory
        from backend.core.semantic_memory import SemanticMemory

        diagnostics = []
        
        # 1. Validate Episodic Memory SQLite -> Chroma
        conn = cls._get_sqlite_conn()
        try:
            # Get SQLite episodes
            epi_rows = conn.execute("SELECT id, content FROM hm_episodes").fetchall()
            epi_db_ids = {r["id"] for r in epi_rows}
            epi_content_map = {r["id"]: r["content"] for r in epi_rows}

            # Get Chroma episodic IDs
            try:
                epi_collection = EpisodicMemory._get_chroma_collection()
                if epi_collection.count() > 0:
                    epi_chroma_ids = set(epi_collection.get(include=[])["ids"])
                else:
                    epi_chroma_ids = set()
            except Exception:
                epi_chroma_ids = set()

            # Find items in SQLite but missing in Chroma -> Repair
            missing_epi = epi_db_ids - epi_chroma_ids
            if missing_epi:
                items_to_add = [(eid, epi_content_map[eid]) for eid in missing_epi]
                EpisodicMemory._process_embeddings(items_to_add)
                diag = {"layer": "episodic", "status": "REPAIRED", "missing_count": len(missing_epi)}
                diagnostics.append(diag)
                cls.log_governance_event("REPAIR", details=diag)
            else:
                diagnostics.append({"layer": "episodic", "status": "OK", "missing_count": 0})
        except Exception as e:
            log_event(f"memory_governance: episodic cross-layer check failed: {e}")
        finally:
            conn.close()

        # 2. Validate Semantic Memory SQLite -> Chroma
        conn = cls._get_sqlite_conn()
        try:
            sem_rows = conn.execute("SELECT id, concept, description FROM hm_semantic_nodes").fetchall()
            sem_db_ids = {r["id"] for r in sem_rows}
            sem_content_map = {r["id"]: (r["concept"], r["description"]) for r in sem_rows}

            try:
                sem_collection = SemanticMemory._get_chroma_collection()
                if sem_collection.count() > 0:
                    sem_chroma_ids = set(sem_collection.get(include=[])["ids"])
                else:
                    sem_chroma_ids = set()
            except Exception:
                sem_chroma_ids = set()

            missing_sem = sem_db_ids - sem_chroma_ids
            if missing_sem:
                items_to_add = [(sid, sem_content_map[sid][0], sem_content_map[sid][1]) for sid in missing_sem]
                SemanticMemory._process_embeddings(items_to_add)
                diag = {"layer": "semantic", "status": "REPAIRED", "missing_count": len(missing_sem)}
                diagnostics.append(diag)
                cls.log_governance_event("REPAIR", details=diag)
            else:
                diagnostics.append({"layer": "semantic", "status": "OK", "missing_count": 0})
        except Exception as e:
            log_event(f"memory_governance: semantic cross-layer check failed: {e}")
        finally:
            conn.close()

        return diagnostics
