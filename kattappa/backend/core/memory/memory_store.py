from __future__ import annotations
import json
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from backend.core.config import load_config

class MemoryStore:
    _lock = threading.RLock()
    _schema_ensured = False

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = config.sqlite_path.parent / "memory.db"
        conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30.0)
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
        cursor = conn.cursor()
        
        # 1. Entities
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE,
                type TEXT,
                metadata_json TEXT,
                created_at TEXT
            )
        """)
        
        # 2. Relationships
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id TEXT PRIMARY KEY,
                source_id TEXT,
                target_id TEXT,
                predicate TEXT,
                metadata_json TEXT,
                source_chunk_id TEXT,
                extraction_method TEXT,
                created_at TEXT,
                FOREIGN KEY (source_id) REFERENCES entities(id) ON DELETE CASCADE,
                FOREIGN KEY (target_id) REFERENCES entities(id) ON DELETE CASCADE,
                UNIQUE(source_id, target_id, predicate)
            )
        """)
        cursor.execute("PRAGMA table_info(relationships)")
        cols = [row[1] for row in cursor.fetchall()]
        if cols and "source_chunk_id" not in cols:
            cursor.execute("ALTER TABLE relationships ADD COLUMN source_chunk_id TEXT")
        if cols and "extraction_method" not in cols:
            cursor.execute("ALTER TABLE relationships ADD COLUMN extraction_method TEXT")
        
        # 3. Memories
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT,
                type TEXT,
                importance REAL,
                confidence REAL,
                access_count INTEGER DEFAULT 0,
                last_accessed TEXT,
                created_at TEXT,
                expires_at TEXT,
                embedding_json TEXT
            )
        """)
        
        # Check if reflections table has the old schema
        cursor.execute("PRAGMA table_info(reflections)")
        cols = [row[1] for row in cursor.fetchall()]
        if cols and "timestamp" not in cols:
            cursor.execute("DROP TABLE reflections")

        # 4. Reflections
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reflections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                goal TEXT NOT NULL,
                task_id TEXT,
                task_type TEXT,
                outcome TEXT,
                success INTEGER,
                retries INTEGER DEFAULT 0,
                confidence_score REAL,
                failure_reason TEXT,
                recovery_strategy TEXT,
                lesson_learned TEXT,
                execution_time_ms INTEGER,
                world_state_hash TEXT,
                planner_version TEXT,
                promoted_to_memory INTEGER DEFAULT 0
            )
        """)
        
        # 5. Skills
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                trigger_conditions_json TEXT,
                prerequisites_json TEXT,
                action_sequence_json TEXT,
                confidence_score REAL,
                success_count INTEGER,
                created_at TEXT
            )
        """)
        
        # 6. K23 Calibration tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS execution_predictions (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                predicted_confidence REAL,
                predicted_duration REAL,
                predicted_memory_usage REAL,
                predicted_success_probability REAL,
                created_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS execution_outcomes (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                actual_duration REAL,
                actual_memory_usage REAL,
                actual_cpu_usage REAL,
                success INTEGER,
                failure_reason TEXT,
                created_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS confidence_drift (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                prediction_error REAL,
                confidence_error REAL,
                resource_error REAL,
                timestamp TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS self_calibration (
                metric_name TEXT PRIMARY KEY,
                current_bias REAL,
                correction_factor REAL,
                updated_at TEXT
            )
        """)
        
        # 7. K24 RAG tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                title TEXT,
                source TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT,
                chunk_index INTEGER,
                text TEXT,
                embedding_id TEXT,
                token_count INTEGER,
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retrieval_stats (
                chunk_id TEXT PRIMARY KEY,
                retrieval_count INTEGER,
                success_count INTEGER,
                average_score REAL,
                last_accessed TEXT,
                FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id)
            )
        """)
        
        # 8. K24.5 & K25 tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retrieval_feedback (
                id TEXT PRIMARY KEY,
                query TEXT,
                retrieved_chunk_ids TEXT,
                selected_chunk_ids TEXT,
                answer_quality REAL,
                user_feedback INTEGER,
                timestamp TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_mentions (
                mention_id TEXT PRIMARY KEY,
                entity_id TEXT,
                chunk_id TEXT,
                sentence_context TEXT,
                FOREIGN KEY(entity_id) REFERENCES entities(id),
                FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_embeddings (
                entity_id TEXT PRIMARY KEY,
                embedding_json TEXT,
                FOREIGN KEY(entity_id) REFERENCES entities(id)
            )
        """)
        conn.commit()

    @classmethod
    def upsert_entity(cls, entity_id: str, name: str, entity_type: str, metadata: dict | None = None) -> None:
        conn = cls._get_conn()
        meta_str = json.dumps(metadata or {})
        now = datetime.now().isoformat()
        with cls._lock:
            conn.execute("""
                INSERT INTO entities (id, name, type, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    type=excluded.type,
                    metadata_json=excluded.metadata_json
            """, (entity_id, name, entity_type, meta_str, now))
            conn.commit()

    @classmethod
    def add_relationship(cls, rel_id: str, source_id: str, target_id: str, predicate: str, metadata: dict | None = None) -> None:
        conn = cls._get_conn()
        meta_str = json.dumps(metadata or {})
        now = datetime.now().isoformat()
        with cls._lock:
            conn.execute("""
                INSERT INTO relationships (id, source_id, target_id, predicate, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, predicate) DO UPDATE SET
                    metadata_json=excluded.metadata_json
            """, (rel_id, source_id, target_id, predicate, meta_str, now))
            conn.commit()

    @classmethod
    def add_memory(
        cls,
        mem_id: str,
        content: str,
        mem_type: str,
        importance: float,
        confidence: float,
        expires_at: str | None = None,
        embedding: list[float] | None = None
    ) -> None:
        conn = cls._get_conn()
        now = datetime.now().isoformat()
        embed_str = json.dumps(embedding or [])
        with cls._lock:
            conn.execute("""
                INSERT INTO memories (id, content, type, importance, confidence, last_accessed, created_at, expires_at, embedding_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (mem_id, content, mem_type, importance, confidence, now, now, expires_at, embed_str))
            conn.commit()

    @classmethod
    def increment_memory_access(cls, mem_id: str) -> None:
        conn = cls._get_conn()
        now = datetime.now().isoformat()
        with cls._lock:
            conn.execute("""
                UPDATE memories
                SET access_count = access_count + 1,
                    last_accessed = ?
                WHERE id = ?
            """, (now, mem_id))
            conn.commit()

    @classmethod
    def get_all_entities(cls) -> list[dict]:
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM entities")
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def get_all_relationships(cls) -> list[dict]:
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM relationships")
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def get_all_memories(cls) -> list[dict]:
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memories")
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def add_reflection(
        cls,
        goal: str,
        task_id: str | None = None,
        task_type: str | None = None,
        outcome: str | None = None,
        success: int = 1,
        retries: int = 0,
        confidence_score: float = 1.0,
        failure_reason: str | None = None,
        recovery_strategy: str | None = None,
        lesson_learned: str | None = None,
        execution_time_ms: int = 0,
        world_state_hash: str | None = None,
        planner_version: str | None = None,
        promoted_to_memory: int = 0
    ) -> None:
        conn = cls._get_conn()
        now = datetime.now().isoformat()
        with cls._lock:
            conn.execute("""
                INSERT INTO reflections (
                    timestamp, goal, task_id, task_type, outcome, success, retries,
                    confidence_score, failure_reason, recovery_strategy, lesson_learned,
                    execution_time_ms, world_state_hash, planner_version, promoted_to_memory
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now, goal, task_id, task_type, outcome, success, retries,
                confidence_score, failure_reason, recovery_strategy, lesson_learned,
                execution_time_ms, world_state_hash, planner_version, promoted_to_memory
            ))
            conn.commit()

    @classmethod
    def get_all_reflections(cls) -> list[dict]:
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reflections")
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def add_skill(
        cls,
        skill_id: str,
        trigger_conditions: dict,
        prerequisites: dict,
        action_sequence: list[dict],
        confidence_score: float,
        success_count: int
    ) -> None:
        conn = cls._get_conn()
        now = datetime.now().isoformat()
        triggers_str = json.dumps(trigger_conditions)
        prereqs_str = json.dumps(prerequisites)
        actions_str = json.dumps(action_sequence)
        with cls._lock:
            conn.execute("""
                INSERT INTO skills (id, trigger_conditions_json, prerequisites_json, action_sequence_json, confidence_score, success_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    confidence_score=excluded.confidence_score,
                    success_count=excluded.success_count,
                    action_sequence_json=excluded.action_sequence_json
            """, (skill_id, triggers_str, prereqs_str, actions_str, confidence_score, success_count, now))
            conn.commit()

    @classmethod
    def get_all_skills(cls) -> list[dict]:
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skills")
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def add_prediction(
        cls,
        prediction_id: str,
        task_id: str,
        predicted_confidence: float,
        predicted_duration: float,
        predicted_memory_usage: float,
        predicted_success_probability: float
    ) -> None:
        conn = cls._get_conn()
        now = datetime.now().isoformat()
        with cls._lock:
            conn.execute("""
                INSERT INTO execution_predictions (
                    id, task_id, predicted_confidence, predicted_duration,
                    predicted_memory_usage, predicted_success_probability, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (prediction_id, task_id, predicted_confidence, predicted_duration,
                  predicted_memory_usage, predicted_success_probability, now))
            conn.commit()

    @classmethod
    def add_outcome(
        cls,
        outcome_id: str,
        task_id: str,
        actual_duration: float,
        actual_memory_usage: float,
        actual_cpu_usage: float,
        success: int,
        failure_reason: str | None
    ) -> None:
        conn = cls._get_conn()
        now = datetime.now().isoformat()
        with cls._lock:
            conn.execute("""
                INSERT INTO execution_outcomes (
                    id, task_id, actual_duration, actual_memory_usage,
                    actual_cpu_usage, success, failure_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (outcome_id, task_id, actual_duration, actual_memory_usage,
                  actual_cpu_usage, success, failure_reason or "", now))
            conn.commit()

    @classmethod
    def add_drift(
        cls,
        drift_id: str,
        task_id: str,
        prediction_error: float,
        confidence_error: float,
        resource_error: float
    ) -> None:
        conn = cls._get_conn()
        now = datetime.now().isoformat()
        with cls._lock:
            conn.execute("""
                INSERT INTO confidence_drift (
                    id, task_id, prediction_error, confidence_error, resource_error, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (drift_id, task_id, prediction_error, confidence_error, resource_error, now))
            conn.commit()

    @classmethod
    def update_calibration(
        cls,
        metric_name: str,
        current_bias: float,
        correction_factor: float
    ) -> None:
        conn = cls._get_conn()
        now = datetime.now().isoformat()
        with cls._lock:
            conn.execute("""
                INSERT INTO self_calibration (metric_name, current_bias, correction_factor, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(metric_name) DO UPDATE SET
                    current_bias=excluded.current_bias,
                    correction_factor=excluded.correction_factor,
                    updated_at=excluded.updated_at
            """, (metric_name, current_bias, correction_factor, now))
            conn.commit()

    @classmethod
    def get_calibration(cls, metric_name: str) -> dict | None:
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM self_calibration WHERE metric_name = ?", (metric_name,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @classmethod
    def add_document(cls, doc_id: str, title: str, source: str) -> None:
        conn = cls._get_conn()
        now = datetime.now().isoformat()
        with cls._lock:
            conn.execute("""
                INSERT INTO documents (doc_id, title, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    title=excluded.title,
                    source=excluded.source,
                    updated_at=excluded.updated_at
            """, (doc_id, title, source, now, now))
            conn.commit()

    @classmethod
    def add_chunk(
        cls,
        chunk_id: str,
        doc_id: str,
        chunk_index: int,
        text: str,
        embedding_id: str,
        token_count: int
    ) -> None:
        conn = cls._get_conn()
        with cls._lock:
            conn.execute("""
                INSERT INTO chunks (chunk_id, doc_id, chunk_index, text, embedding_id, token_count)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    text=excluded.text,
                    embedding_id=excluded.embedding_id,
                    token_count=excluded.token_count
            """, (chunk_id, doc_id, chunk_index, text, embedding_id, token_count))
            conn.commit()

    @classmethod
    def get_document_chunks(cls, doc_id: str) -> list[dict]:
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chunks WHERE doc_id = ? ORDER BY chunk_index ASC", (doc_id,))
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def get_all_chunks(cls) -> list[dict]:
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chunks")
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def get_all_documents(cls) -> list[dict]:
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents")
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def log_retrieval_stat(cls, chunk_id: str, score: float, success: bool) -> None:
        conn = cls._get_conn()
        now = datetime.now().isoformat()
        succ_val = 1 if success else 0
        with cls._lock:
            conn.execute("""
                INSERT INTO retrieval_stats (chunk_id, retrieval_count, success_count, average_score, last_accessed)
                VALUES (?, 1, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    retrieval_count = retrieval_count + 1,
                    success_count = success_count + excluded.success_count,
                    average_score = (average_score * retrieval_count + excluded.average_score) / (retrieval_count + 1),
                    last_accessed = excluded.last_accessed
            """, (chunk_id, succ_val, score, now))
            conn.commit()

    @classmethod
    def add_retrieval_feedback(
        cls,
        feedback_id: str,
        query: str,
        retrieved_chunk_ids: list[str],
        selected_chunk_ids: list[str],
        answer_quality: float,
        user_feedback: int
    ) -> None:
        conn = cls._get_conn()
        now = datetime.now().isoformat()
        retrieved_str = json.dumps(retrieved_chunk_ids)
        selected_str = json.dumps(selected_chunk_ids)
        with cls._lock:
            conn.execute("""
                INSERT INTO retrieval_feedback (
                    id, query, retrieved_chunk_ids, selected_chunk_ids,
                    answer_quality, user_feedback, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (feedback_id, query, retrieved_str, selected_str, answer_quality, user_feedback, now))
            conn.commit()

    @classmethod
    def get_all_retrieval_feedback(cls) -> list[dict]:
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM retrieval_feedback")
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def add_entity_mention(
        cls,
        mention_id: str,
        entity_id: str,
        chunk_id: str,
        sentence_context: str
    ) -> None:
        conn = cls._get_conn()
        with cls._lock:
            conn.execute("""
                INSERT INTO entity_mentions (mention_id, entity_id, chunk_id, sentence_context)
                VALUES (?, ?, ?, ?)
            """, (mention_id, entity_id, chunk_id, sentence_context))
            conn.commit()

    @classmethod
    def get_entity_mentions(cls, entity_id: str) -> list[dict]:
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM entity_mentions WHERE entity_id = ?", (entity_id,))
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def update_entity_embedding(cls, entity_id: str, embedding: list[float]) -> None:
        conn = cls._get_conn()
        emb_str = json.dumps(embedding)
        with cls._lock:
            conn.execute("""
                INSERT INTO entity_embeddings (entity_id, embedding_json)
                VALUES (?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET embedding_json=excluded.embedding_json
            """, (entity_id, emb_str))
            conn.commit()

    @classmethod
    def add_graph_relationship(
        cls,
        rel_id: str,
        source_id: str,
        target_id: str,
        predicate: str,
        metadata: dict | None,
        source_chunk_id: str,
        extraction_method: str
    ) -> None:
        conn = cls._get_conn()
        meta_str = json.dumps(metadata or {})
        now = datetime.now().isoformat()
        with cls._lock:
            conn.execute("""
                INSERT INTO relationships (
                    id, source_id, target_id, predicate, metadata_json,
                    source_chunk_id, extraction_method, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, predicate) DO UPDATE SET
                    metadata_json=excluded.metadata_json,
                    source_chunk_id=excluded.source_chunk_id,
                    extraction_method=excluded.extraction_method,
                    created_at=excluded.created_at
            """, (rel_id, source_id, target_id, predicate, meta_str,
                  source_chunk_id, extraction_method, now))
            conn.commit()

    @classmethod
    def get_entity_relationships(cls, entity_id: str) -> list[dict]:
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM relationships 
            WHERE source_id = ? OR target_id = ?
        """, (entity_id, entity_id))
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def get_all_relationships(cls) -> list[dict]:
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM relationships")
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def clear_database(cls) -> None:
        conn = cls._get_conn()
        with cls._lock:
            # Child tables first to avoid foreign key errors
            conn.execute("DELETE FROM entity_mentions")
            conn.execute("DELETE FROM entity_embeddings")
            conn.execute("DELETE FROM retrieval_stats")
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM documents")
            
            # Parent/independent tables next
            conn.execute("DELETE FROM relationships")
            conn.execute("DELETE FROM entities")
            conn.execute("DELETE FROM memories")
            conn.execute("DELETE FROM reflections")
            conn.execute("DELETE FROM skills")
            conn.execute("DELETE FROM execution_predictions")
            conn.execute("DELETE FROM execution_outcomes")
            conn.execute("DELETE FROM confidence_drift")
            conn.execute("DELETE FROM self_calibration")
            conn.execute("DELETE FROM retrieval_feedback")
            conn.commit()
