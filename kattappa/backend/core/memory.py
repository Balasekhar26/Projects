from __future__ import annotations

import sqlite3
import json
import shutil
from datetime import datetime
from typing import Any
from uuid import uuid4

from backend.core.config import legacy_runtime_path, load_config


PRIMARY_CHAT_SESSION_ID = "kattappa-main-chat"
PRIMARY_CHAT_TITLE = "Kattappa Main Chat"


class MemorySystem:
    def __init__(self) -> None:
        self.config = load_config()
        self._migrate_repo_memory_once()
        self.config.chroma_path.mkdir(parents=True, exist_ok=True)
        self.config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.chroma: Any | None = None
        self.collection: Any | None = None
        self._init_sqlite()

    def _migrate_repo_memory_once(self) -> None:
        legacy_sqlite = legacy_runtime_path(
            "backend/memory/sqlite/kattappa_ai_os.db",
            "backend/memory/sqlite/kattappa_ai_os.db",
        )
        if (
            self.config.sqlite_path != legacy_sqlite
            and legacy_sqlite.exists()
            and not self.config.sqlite_path.exists()
        ):
            self.config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy_sqlite, self.config.sqlite_path)

        legacy_chroma = legacy_runtime_path(
            "backend/memory/chroma", "backend/memory/chroma"
        )
        if (
            self.config.chroma_path != legacy_chroma
            and legacy_chroma.exists()
            and not self.config.chroma_path.exists()
        ):
            self.config.chroma_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(legacy_chroma, self.config.chroma_path)

    def _collection(self) -> Any:
        if self.collection is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

            self.chroma = chromadb.PersistentClient(
                path=str(self.config.chroma_path),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self.collection = self.chroma.get_or_create_collection(
                self.config.memory_collection,
                embedding_function=DefaultEmbeddingFunction(),
            )
        return self.collection

    def _init_sqlite(self) -> None:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    decay_score REAL NOT NULL DEFAULT 1.0,
                    last_accessed TEXT,
                    flagged_for_summary INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._ensure_column(conn, "memories", "decay_score", "REAL NOT NULL DEFAULT 1.0")
            self._ensure_column(conn, "memories", "last_accessed", "TEXT")
            self._ensure_column(
                conn,
                "memories",
                "flagged_for_summary",
                "INTEGER NOT NULL DEFAULT 0",
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    continuation_type TEXT NOT NULL DEFAULT 'manual',
                    continuation_payload TEXT NOT NULL DEFAULT '{}',
                    continued_at TEXT NOT NULL DEFAULT '',
                    continuation_result TEXT NOT NULL DEFAULT ''
                )
                """
            )
            self._ensure_column(conn, "approvals", "continuation_type", "TEXT NOT NULL DEFAULT 'manual'")
            self._ensure_column(conn, "approvals", "continuation_payload", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "approvals", "continued_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "approvals", "continuation_result", "TEXT NOT NULL DEFAULT ''")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS improvement_backlog (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    motive TEXT NOT NULL,
                    proposal TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    steps TEXT NOT NULL,
                    tools TEXT NOT NULL DEFAULT '',
                    risk TEXT NOT NULL,
                    trust TEXT NOT NULL,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    last_reflection TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reflections (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    skill_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_evaluations (
                    id TEXT PRIMARY KEY,
                    skill_id TEXT NOT NULL,
                    result TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS install_jobs (
                    approval_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    agent TEXT DEFAULT '',
                    risk TEXT DEFAULT '',
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS long_tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'normal',
                    progress TEXT NOT NULL DEFAULT '',
                    next_step TEXT NOT NULL DEFAULT '',
                    source_session_id TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_scout_reports (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    source TEXT NOT NULL,
                    license_note TEXT NOT NULL,
                    build_own_plan TEXT NOT NULL,
                    status TEXT NOT NULL,
                    improvement_id TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_adoption_jobs (
                    id TEXT PRIMARY KEY,
                    report_id TEXT NOT NULL,
                    install_approval_id TEXT NOT NULL DEFAULT '',
                    final_approval_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    install_observation TEXT NOT NULL DEFAULT '',
                    build_own_result TEXT NOT NULL DEFAULT '',
                    test_result TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS neuroseed_seeds (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    keywords TEXT NOT NULL DEFAULT '[]',
                    cue TEXT NOT NULL DEFAULT '{}',
                    approved INTEGER NOT NULL DEFAULT 0,
                    consent_status TEXT NOT NULL DEFAULT 'pending',
                    consent_model TEXT NOT NULL DEFAULT '',
                    approved_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    memory_id TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS neuroseed_consent_logs (
                    id TEXT PRIMARY KEY,
                    seed_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    consent_model TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS neuroseed_sessions (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    approved_seed_ids TEXT NOT NULL DEFAULT '[]',
                    uncued_seed_ids TEXT NOT NULL DEFAULT '[]',
                    settings TEXT NOT NULL DEFAULT '{}',
                    safety_boundary TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS neuroseed_cue_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    seed_id TEXT NOT NULL,
                    seed_title TEXT NOT NULL,
                    cue_label TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    cued_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES neuroseed_sessions(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS neuroseed_recall_results (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    session_started_at TEXT,
                    seed_id TEXT NOT NULL,
                    seed_title TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    score REAL NOT NULL,
                    checked_at TEXT NOT NULL,
                    consent_model TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table: str,
        column: str,
        ddl: str,
    ) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def remember(self, text: str, category: str = "general", metadata: str = "{}") -> str:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            return self._remember_with_connection(conn, text, category, metadata)

    def _remember_with_connection(
        self,
        conn: sqlite3.Connection,
        text: str,
        category: str = "general",
        metadata: str = "{}",
    ) -> str:
        memory_id = str(uuid4())
        created_at = datetime.now().isoformat(timespec="seconds")
        self._collection().add(
            ids=[memory_id],
            documents=[text],
            metadatas=[{"category": category, "created_at": created_at}],
        )
        conn.execute(
            """
            INSERT INTO memories(
                id, category, text, created_at, metadata,
                decay_score, last_accessed, flagged_for_summary
            )
            VALUES (?, ?, ?, ?, ?, 1.0, ?, 0)
            """,
            (memory_id, category, text, created_at, metadata, created_at),
        )
        return memory_id

    def recall(self, query: str, n_results: int = 5) -> list[str]:
        collection = self._collection()
        count = collection.count()
        if count == 0:
            return []
        result = collection.query(query_texts=[query], n_results=min(n_results, count))
        ids = [item for item in result.get("ids", [[]])[0] if item]
        if ids:
            now = datetime.now().isoformat(timespec="seconds")
            with sqlite3.connect(self.config.sqlite_path) as conn:
                conn.executemany(
                    "UPDATE memories SET last_accessed = ? WHERE id = ?",
                    [(now, memory_id) for memory_id in ids],
                )
        return [doc for doc in result.get("documents", [[]])[0] if doc]

    def decay_memories(
        self,
        decay_rate: float = 0.10,
        summarize_threshold: float = 0.30,
        prune_threshold: float = 0.05,
    ) -> dict[str, int]:
        if decay_rate < 0 or summarize_threshold < prune_threshold:
            raise ValueError("Invalid memory decay thresholds")

        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                UPDATE memories
                SET decay_score = MAX(decay_score - ?, 0.0)
                """,
                (decay_rate,),
            )
            flagged = conn.execute(
                """
                UPDATE memories
                SET flagged_for_summary = 1
                WHERE decay_score < ? AND decay_score >= ?
                """,
                (summarize_threshold, prune_threshold),
            ).rowcount
            pruned = conn.execute(
                "DELETE FROM memories WHERE decay_score < ?",
                (prune_threshold,),
            ).rowcount
            remaining = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        return {"flagged": int(flagged), "pruned": int(pruned), "remaining": int(remaining)}

    def count(self) -> int:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        return int(row[0]) if row else 0

    def save_neuroseed_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        seeds = [item for item in payload.get("seeds", []) if isinstance(item, dict)]
        sessions = [item for item in payload.get("sessions", []) if isinstance(item, dict)]
        recall_results = [item for item in payload.get("recallResults", []) if isinstance(item, dict)]
        data_model = payload.get("dataModel", {})
        now = datetime.now().isoformat(timespec="seconds")
        reset_requested = isinstance(data_model, dict) and data_model.get("resetRequested") is True

        with sqlite3.connect(self.config.sqlite_path) as conn:
            if reset_requested:
                self._delete_neuroseed_semantic_memories(conn)
                for table in (
                    "neuroseed_recall_results",
                    "neuroseed_cue_events",
                    "neuroseed_sessions",
                    "neuroseed_consent_logs",
                    "neuroseed_seeds",
                ):
                    conn.execute(f"DELETE FROM {table}")
            else:
                approved_seed_ids: set[str] = set()
                ever_approved_seed_ids = self._neuroseed_ever_approved_seed_ids(conn)
                incoming_seed_ids: set[str] = set()
                incoming_session_ids: set[str] = set()
                incoming_recall_ids: set[str] = set()

                for seed in seeds:
                    seed_id = str(seed.get("id") or "").strip()
                    text = str(seed.get("text") or "").strip()
                    if not seed_id or not text:
                        continue
                    incoming_seed_ids.add(seed_id)
                    title = str(seed.get("title") or "Untitled seed").strip()[:160] or "Untitled seed"
                    consent = seed.get("consent") if isinstance(seed.get("consent"), dict) else {}
                    approved = bool(seed.get("approved")) and consent.get("status") == "awake-approved"
                    consent_status = str(consent.get("status") or ("awake-approved" if approved else "pending"))
                    consent_model = str(consent.get("model") or data_model.get("version") or "")
                    approved_at = str(consent.get("approvedAt") or "") or None
                    existing = conn.execute(
                        """
                        SELECT approved, consent_status, memory_id
                        FROM neuroseed_seeds
                        WHERE id = ?
                        """,
                        (seed_id,),
                    ).fetchone()
                    memory_id = str(existing[2] or "") if existing else ""

                    if approved:
                        approved_seed_ids.add(seed_id)
                        ever_approved_seed_ids.add(seed_id)
                        if not memory_id:
                            memory_id = self._remember_with_connection(
                                conn,
                                text,
                                category="neuroseed_approved_seed",
                                metadata=_json_dump(
                                    {
                                        "project": "neuroseed",
                                        "seed_id": seed_id,
                                        "title": title,
                                        "cue": seed.get("cue") or {},
                                        "consent_model": consent_model,
                                        "approved_at": approved_at,
                                    }
                                ),
                            )

                    if (
                        existing is None
                        or bool(existing[0]) != approved
                        or str(existing[1] or "") != consent_status
                    ):
                        conn.execute(
                            """
                            INSERT INTO neuroseed_consent_logs(
                                id, seed_id, action, status, consent_model, note, created_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                str(uuid4()),
                                seed_id,
                                "awake_approval" if approved else "approval_removed",
                                consent_status,
                                consent_model,
                                "User-controlled NeuroSeed consent change.",
                                now,
                            ),
                        )

                    conn.execute(
                        """
                        INSERT INTO neuroseed_seeds(
                            id, title, text, keywords, cue, approved, consent_status,
                            consent_model, approved_at, created_at, updated_at, memory_id
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            title = excluded.title,
                            text = excluded.text,
                            keywords = excluded.keywords,
                            cue = excluded.cue,
                            approved = excluded.approved,
                            consent_status = excluded.consent_status,
                            consent_model = excluded.consent_model,
                            approved_at = excluded.approved_at,
                            updated_at = excluded.updated_at,
                            memory_id = excluded.memory_id
                        """,
                        (
                            seed_id,
                            title,
                            text,
                            _json_dump(seed.get("keywords") or []),
                            _json_dump(seed.get("cue") or {}),
                            1 if approved else 0,
                            consent_status,
                            consent_model,
                            approved_at,
                            str(seed.get("createdAt") or now),
                            now,
                            memory_id,
                        ),
                    )

                for session in sessions:
                    session_id = str(session.get("id") or "").strip()
                    if session_id:
                        incoming_session_ids.add(session_id)
                    self._upsert_neuroseed_session(
                        conn,
                        session,
                        approved_seed_ids=approved_seed_ids,
                        ever_approved_seed_ids=ever_approved_seed_ids,
                        now=now,
                    )

                session_cues = self._neuroseed_session_cue_index(conn)
                for result in recall_results:
                    result_id = str(result.get("id") or "").strip()
                    if result_id:
                        incoming_recall_ids.add(result_id)
                    self._upsert_neuroseed_recall_result(conn, result, session_cues)

                self._delete_absent_neuroseed_seeds(conn, incoming_seed_ids)
                self._delete_absent(conn, "neuroseed_sessions", incoming_session_ids)
                self._delete_absent(conn, "neuroseed_recall_results", incoming_recall_ids)
                if incoming_session_ids:
                    self._delete_absent(conn, "neuroseed_cue_events", incoming_session_ids, column="session_id")
                else:
                    conn.execute("DELETE FROM neuroseed_cue_events")

        return self.get_neuroseed_state()

    def get_neuroseed_state(self) -> dict[str, Any]:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            seed_rows = conn.execute(
                """
                SELECT id, title, text, keywords, cue, approved, consent_status,
                       consent_model, approved_at, created_at
                FROM neuroseed_seeds
                ORDER BY created_at ASC
                """
            ).fetchall()
            session_rows = conn.execute(
                """
                SELECT id, started_at, ended_at, status, approved_seed_ids,
                       uncued_seed_ids, settings, safety_boundary
                FROM neuroseed_sessions
                ORDER BY started_at DESC
                """
            ).fetchall()
            recall_rows = conn.execute(
                """
                SELECT id, session_id, session_started_at, seed_id, seed_title,
                       condition, answer, score, checked_at, consent_model
                FROM neuroseed_recall_results
                ORDER BY checked_at DESC
                """
            ).fetchall()
            consent_rows = conn.execute(
                """
                SELECT id, seed_id, action, status, consent_model, note, created_at
                FROM neuroseed_consent_logs
                ORDER BY created_at DESC
                LIMIT 200
                """
            ).fetchall()
            cue_rows = conn.execute(
                """
                SELECT id, session_id, seed_id, seed_title, cue_label, stage, cued_at
                FROM neuroseed_cue_events
                ORDER BY cued_at ASC
                """
            ).fetchall()

        cue_events_by_session: dict[str, list[dict[str, str]]] = {}
        cued_ids: set[str] = set()
        for row in cue_rows:
            event = {
                "id": str(row[0]),
                "sessionId": str(row[1]),
                "seedId": str(row[2]),
                "seedTitle": str(row[3]),
                "cueLabel": str(row[4]),
                "stage": str(row[5]),
                "cuedAt": str(row[6]),
            }
            cue_events_by_session.setdefault(event["sessionId"], []).append(event)
            cued_ids.add(event["seedId"])

        return {
            "dataModel": {
                "version": "pilot-consent-v1",
                "durableMemory": "universal-ai Chroma + SQLite",
                "exportRequiresUserAction": True,
            },
            "seeds": [
                {
                    "id": str(row[0]),
                    "title": str(row[1]),
                    "text": str(row[2]),
                    "keywords": _json_load(row[3], []),
                    "cue": _json_load(row[4], {}),
                    "approved": bool(row[5]),
                    "consent": {
                        "status": str(row[6]),
                        "model": str(row[7] or ""),
                        "approvedAt": row[8],
                    },
                    "createdAt": str(row[9]),
                }
                for row in seed_rows
            ],
            "logs": [],
            "sessions": [
                {
                    "id": str(row[0]),
                    "startedAt": str(row[1]),
                    "endedAt": row[2],
                    "status": str(row[3]),
                    "approvedSeedIds": _json_load(row[4], []),
                    "cueEvents": cue_events_by_session.get(str(row[0]), []),
                    "uncuedSeedIds": _json_load(row[5], []),
                    "settings": _json_load(row[6], {}),
                    "safetyBoundary": _json_load(row[7], {}),
                }
                for row in session_rows
            ],
            "cuedIds": sorted(cued_ids),
            "activeSessionId": None,
            "recallResults": [
                {
                    "id": str(row[0]),
                    "sessionId": str(row[1]),
                    "sessionStartedAt": row[2],
                    "seedId": str(row[3]),
                    "seedTitle": str(row[4]),
                    "condition": str(row[5]),
                    "answer": str(row[6]),
                    "score": float(row[7]),
                    "checkedAt": str(row[8]),
                    "consentModel": str(row[9] or ""),
                }
                for row in recall_rows
            ],
            "consentLogs": [
                {
                    "id": str(row[0]),
                    "seedId": str(row[1]),
                    "action": str(row[2]),
                    "status": str(row[3]),
                    "consentModel": str(row[4] or ""),
                    "note": str(row[5]),
                    "createdAt": str(row[6]),
                }
                for row in consent_rows
            ],
        }

    def _neuroseed_ever_approved_seed_ids(self, conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute(
            """
            SELECT id FROM neuroseed_seeds WHERE approved = 1
            UNION
            SELECT seed_id FROM neuroseed_consent_logs WHERE status = 'awake-approved'
            """
        ).fetchall()
        return {str(row[0]) for row in rows}

    def _delete_absent(
        self,
        conn: sqlite3.Connection,
        table: str,
        ids: set[str],
        column: str = "id",
    ) -> None:
        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM {table} WHERE {column} NOT IN ({placeholders})", tuple(ids))
        else:
            conn.execute(f"DELETE FROM {table}")

    def _delete_absent_neuroseed_seeds(self, conn: sqlite3.Connection, ids: set[str]) -> None:
        if ids:
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"""
                SELECT memory_id
                FROM neuroseed_seeds
                WHERE id NOT IN ({placeholders}) AND memory_id <> ''
                """,
                tuple(ids),
            ).fetchall()
            self._delete_semantic_memory_ids(conn, [str(row[0]) for row in rows])
            conn.execute(f"DELETE FROM neuroseed_seeds WHERE id NOT IN ({placeholders})", tuple(ids))
        else:
            self._delete_neuroseed_semantic_memories(conn)
            conn.execute("DELETE FROM neuroseed_seeds")

    def _delete_neuroseed_semantic_memories(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT memory_id FROM neuroseed_seeds WHERE memory_id <> ''
            UNION
            SELECT id FROM memories WHERE category = 'neuroseed_approved_seed'
            """
        ).fetchall()
        self._delete_semantic_memory_ids(conn, [str(row[0]) for row in rows])
        conn.execute("DELETE FROM memories WHERE category = 'neuroseed_approved_seed'")

    def _delete_semantic_memory_ids(self, conn: sqlite3.Connection, ids: list[str]) -> None:
        clean_ids = [memory_id for memory_id in ids if memory_id]
        if not clean_ids:
            return
        try:
            self._collection().delete(ids=clean_ids)
        except Exception:
            pass
        placeholders = ",".join("?" for _ in clean_ids)
        conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", tuple(clean_ids))

    def _upsert_neuroseed_session(
        self,
        conn: sqlite3.Connection,
        session: dict[str, Any],
        approved_seed_ids: set[str],
        ever_approved_seed_ids: set[str],
        now: str,
    ) -> None:
        session_id = str(session.get("id") or "").strip()
        started_at = str(session.get("startedAt") or "").strip()
        if not session_id or not started_at:
            return
        requested_seed_ids = [str(item) for item in session.get("approvedSeedIds", [])]
        allowed_seed_ids = [
            seed_id
            for seed_id in requested_seed_ids
            if seed_id in approved_seed_ids or seed_id in ever_approved_seed_ids
        ]
        if requested_seed_ids and not allowed_seed_ids:
            raise ValueError("NeuroSeed session blocked: no awake-approved seeds.")

        cue_events = [item for item in session.get("cueEvents", []) if isinstance(item, dict)]
        cued_seed_ids: set[str] = set()
        for event in cue_events:
            seed_id = str(event.get("seedId") or "")
            if seed_id not in allowed_seed_ids:
                raise ValueError("NeuroSeed cue blocked: seed was not awake-approved for this session.")
            cued_seed_ids.add(seed_id)

        uncued_seed_ids = [seed_id for seed_id in allowed_seed_ids if seed_id not in cued_seed_ids]
        conn.execute(
            """
            INSERT INTO neuroseed_sessions(
                id, started_at, ended_at, status, approved_seed_ids, uncued_seed_ids,
                settings, safety_boundary, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                started_at = excluded.started_at,
                ended_at = excluded.ended_at,
                status = excluded.status,
                approved_seed_ids = excluded.approved_seed_ids,
                uncued_seed_ids = excluded.uncued_seed_ids,
                settings = excluded.settings,
                safety_boundary = excluded.safety_boundary,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                started_at,
                session.get("endedAt"),
                str(session.get("status") or "completed"),
                _json_dump(allowed_seed_ids),
                _json_dump(uncued_seed_ids),
                _json_dump(session.get("settings") or {}),
                _json_dump(session.get("safetyBoundary") or {}),
                now,
                now,
            ),
        )
        conn.execute("DELETE FROM neuroseed_cue_events WHERE session_id = ?", (session_id,))
        for event in cue_events:
            conn.execute(
                """
                INSERT INTO neuroseed_cue_events(
                    id, session_id, seed_id, seed_title, cue_label, stage, cued_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.get("id") or uuid4()),
                    session_id,
                    str(event.get("seedId") or ""),
                    str(event.get("seedTitle") or ""),
                    str(event.get("cueLabel") or ""),
                    str(event.get("stage") or ""),
                    str(event.get("cuedAt") or now),
                ),
            )

    def _neuroseed_session_cue_index(self, conn: sqlite3.Connection) -> dict[str, set[str]]:
        rows = conn.execute("SELECT session_id, seed_id FROM neuroseed_cue_events").fetchall()
        index: dict[str, set[str]] = {}
        for session_id, seed_id in rows:
            index.setdefault(str(session_id), set()).add(str(seed_id))
        return index

    def _upsert_neuroseed_recall_result(
        self,
        conn: sqlite3.Connection,
        result: dict[str, Any],
        session_cues: dict[str, set[str]],
    ) -> None:
        result_id = str(result.get("id") or "").strip()
        seed_id = str(result.get("seedId") or "").strip()
        session_id = str(result.get("sessionId") or "manual").strip() or "manual"
        condition = str(result.get("condition") or "").strip()
        if not result_id or not seed_id:
            return
        if condition not in {"cued", "uncued"}:
            raise ValueError("NeuroSeed recall condition must be cued or uncued.")
        if session_id != "manual":
            expected = "cued" if seed_id in session_cues.get(session_id, set()) else "uncued"
            if condition != expected:
                raise ValueError("NeuroSeed recall condition does not match session cue history.")
        score = float(result.get("score") or 0)
        if score < 0 or score > 1:
            raise ValueError("NeuroSeed recall score must be between 0 and 1.")
        conn.execute(
            """
            INSERT INTO neuroseed_recall_results(
                id, session_id, session_started_at, seed_id, seed_title, condition,
                answer, score, checked_at, consent_model
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                session_id = excluded.session_id,
                session_started_at = excluded.session_started_at,
                seed_id = excluded.seed_id,
                seed_title = excluded.seed_title,
                condition = excluded.condition,
                answer = excluded.answer,
                score = excluded.score,
                checked_at = excluded.checked_at,
                consent_model = excluded.consent_model
            """,
            (
                result_id,
                session_id,
                result.get("sessionStartedAt"),
                seed_id,
                str(result.get("seedTitle") or ""),
                condition,
                str(result.get("answer") or ""),
                score,
                str(result.get("checkedAt") or datetime.now().isoformat(timespec="seconds")),
                str(result.get("consentModel") or ""),
            ),
        )

    def get_or_create_primary_chat_session(self) -> dict[str, str]:
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE id = ?",
                (PRIMARY_CHAT_SESSION_ID,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO chat_sessions(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (PRIMARY_CHAT_SESSION_ID, PRIMARY_CHAT_TITLE, now, now),
                )
                return {
                    "id": PRIMARY_CHAT_SESSION_ID,
                    "title": PRIMARY_CHAT_TITLE,
                    "created_at": now,
                    "updated_at": now,
                }
            if row[1] != PRIMARY_CHAT_TITLE:
                conn.execute(
                    "UPDATE chat_sessions SET title = ? WHERE id = ?",
                    (PRIMARY_CHAT_TITLE, PRIMARY_CHAT_SESSION_ID),
                )
                row = (row[0], PRIMARY_CHAT_TITLE, row[2], row[3])
        return {"id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3]}

    def create_chat_session(self, title: str = "New chat") -> dict[str, str]:
        return self.get_or_create_primary_chat_session()

    def list_chat_sessions(self, limit: int = 50) -> list[dict[str, str]]:
        if limit <= 0:
            return []
        primary = self.get_or_create_primary_chat_session()
        with sqlite3.connect(self.config.sqlite_path) as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE id = ?",
                (primary["id"],),
            ).fetchone()
        if row is None:
            return [primary]
        return [{"id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3]}]

    def rename_primary_chat_from_first_message(self, content: str) -> None:
        primary = self.get_or_create_primary_chat_session()
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                "UPDATE chat_sessions SET title = ? WHERE id = ? AND title = ?",
                (_chat_title(content), primary["id"], PRIMARY_CHAT_TITLE),
            )

    def add_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        agent: str = "",
        risk: str = "",
        metadata: str = "{}",
    ) -> dict[str, str]:
        if role not in {"user", "assistant", "system", "progress"}:
            raise ValueError("role must be user, assistant, system, or progress")
        if not self.get_chat_session(session_id):
            raise ValueError("chat session not found")
        message_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                INSERT INTO chat_messages(id, session_id, role, content, agent, risk, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, session_id, role, content, agent, risk, metadata, now),
            )
            conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        return {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "agent": agent,
            "risk": risk,
            "metadata": metadata,
            "created_at": now,
        }

    def get_chat_session(self, session_id: str) -> dict[str, str] | None:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3]}

    def list_chat_messages(self, session_id: str, limit: int = 500) -> list[dict[str, str]]:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content, agent, risk, metadata, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [
            {
                "id": row[0],
                "session_id": row[1],
                "role": row[2],
                "content": row[3],
                "agent": row[4],
                "risk": row[5],
                "metadata": row[6],
                "created_at": row[7],
            }
            for row in rows
        ]

    def search_chat_messages(
        self,
        query: str,
        limit: int = 8,
        session_id: str | None = None,
        exclude_message_id: str | None = None,
    ) -> list[dict[str, object]]:
        terms = _search_terms(query)
        if not terms:
            return []
        clauses = " OR ".join(["m.content LIKE ?" for _ in terms])
        params = [f"%{term}%" for term in terms]
        filters = [f"({clauses})"]
        if session_id:
            filters.append("m.session_id = ?")
            params.append(session_id)
        if exclude_message_id:
            filters.append("m.id != ?")
            params.append(exclude_message_id)
        fetch_limit = max(limit * 5, 20)
        with sqlite3.connect(self.config.sqlite_path) as conn:
            rows = conn.execute(
                f"""
                SELECT m.id, m.session_id, s.title, m.role, m.content, m.agent, m.risk, m.created_at
                FROM chat_messages m
                JOIN chat_sessions s ON s.id = m.session_id
                WHERE {" AND ".join(filters)}
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                [*params, fetch_limit],
            ).fetchall()
        matches: list[dict[str, object]] = []
        for row in rows:
            content = str(row[4])
            matched_terms = [term for term in terms if term in content.lower()]
            if not matched_terms:
                continue
            score = sum(max(len(term), 3) for term in matched_terms)
            matches.append(
                {
                    "id": row[0],
                    "session_id": row[1],
                    "session_title": row[2],
                    "role": row[3],
                    "content": content,
                    "agent": row[5],
                    "risk": row[6],
                    "created_at": row[7],
                    "matched_terms": matched_terms,
                    "score": score,
                }
            )
        matches.sort(key=lambda item: (int(item["score"]), str(item["created_at"])), reverse=True)
        return matches[:limit]

    def create_long_task(
        self,
        title: str,
        goal: str,
        priority: str = "normal",
        source_session_id: str = "",
    ) -> dict[str, str]:
        if priority not in {"low", "normal", "high"}:
            raise ValueError("priority must be low, normal, or high")
        task_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        clean_title = title.strip()[:100] or _chat_title(goal)
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                INSERT INTO long_tasks(
                    id, title, goal, status, priority, progress, next_step,
                    source_session_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, clean_title, goal.strip(), "active", priority, "", "", source_session_id, now, now),
            )
        return self.get_long_task(task_id) or {}

    def get_long_task(self, task_id: str) -> dict[str, str] | None:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            row = conn.execute(
                """
                SELECT id, title, goal, status, priority, progress, next_step,
                       source_session_id, created_at, updated_at
                FROM long_tasks
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
        return _long_task_row(row) if row else None

    def list_long_tasks(self, status: str | None = None, limit: int = 25) -> list[dict[str, str]]:
        sql = """
            SELECT id, title, goal, status, priority, progress, next_step,
                   source_session_id, created_at, updated_at
            FROM long_tasks
        """
        params: list[object] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END, updated_at DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.config.sqlite_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_long_task_row(row) for row in rows]

    def update_long_task(
        self,
        task_id: str,
        status: str | None = None,
        progress: str | None = None,
        next_step: str | None = None,
    ) -> dict[str, str] | None:
        current = self.get_long_task(task_id)
        if current is None:
            return None
        next_status = status if status is not None else current["status"]
        if next_status not in {"active", "paused", "done", "archived"}:
            raise ValueError("status must be active, paused, done, or archived")
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                UPDATE long_tasks
                SET status = ?, progress = ?, next_step = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_status,
                    current["progress"] if progress is None else progress.strip(),
                    current["next_step"] if next_step is None else next_step.strip(),
                    now,
                    task_id,
                ),
            )
        return self.get_long_task(task_id)

    def find_relevant_long_tasks(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        terms = _search_terms(query)
        params: list[object] = []
        clauses = ["status IN ('active', 'paused')"]
        if terms:
            like_clauses: list[str] = []
            for term in terms:
                like_clauses.append("(title LIKE ? OR goal LIKE ? OR progress LIKE ? OR next_step LIKE ?)")
                pattern = f"%{term}%"
                params.extend([pattern, pattern, pattern, pattern])
            clauses.append("(" + " OR ".join(like_clauses) + ")")
        sql = """
            SELECT id, title, goal, status, priority, progress, next_step,
                   source_session_id, created_at, updated_at
            FROM long_tasks
            WHERE """ + " AND ".join(clauses) + """
            ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, updated_at DESC
            LIMIT ?
        """
        params.append(limit)
        with sqlite3.connect(self.config.sqlite_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_long_task_row(row) for row in rows]

    def create_tool_scout_report(
        self,
        task: str,
        capability: str,
        recommendation: str,
        source: str,
        license_note: str,
        build_own_plan: str,
        status: str = "proposed",
        improvement_id: str = "",
    ) -> dict[str, str]:
        if status not in {"proposed", "approved", "rejected", "built"}:
            raise ValueError("status must be proposed, approved, rejected, or built")
        report_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                INSERT INTO tool_scout_reports(
                    id, task, capability, recommendation, source, license_note,
                    build_own_plan, status, improvement_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    task.strip()[:800],
                    capability.strip()[:160],
                    recommendation.strip()[:1200],
                    source.strip()[:400],
                    license_note.strip()[:500],
                    build_own_plan.strip()[:1600],
                    status,
                    improvement_id,
                    now,
                ),
            )
        return self.get_tool_scout_report(report_id) or {}

    def get_tool_scout_report(self, report_id: str) -> dict[str, str] | None:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            row = conn.execute(
                """
                SELECT id, task, capability, recommendation, source, license_note,
                       build_own_plan, status, improvement_id, created_at
                FROM tool_scout_reports
                WHERE id = ?
                """,
                (report_id,),
            ).fetchone()
        return _tool_scout_row(row) if row else None

    def list_tool_scout_reports(self, status: str | None = None, limit: int = 25) -> list[dict[str, str]]:
        sql = """
            SELECT id, task, capability, recommendation, source, license_note,
                   build_own_plan, status, improvement_id, created_at
            FROM tool_scout_reports
        """
        params: list[object] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.config.sqlite_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_tool_scout_row(row) for row in rows]

    def update_tool_scout_status(self, report_id: str, status: str) -> dict[str, str] | None:
        if status not in {"proposed", "install_requested", "testing", "approved", "rejected", "built"}:
            raise ValueError("invalid tool scout status")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute("UPDATE tool_scout_reports SET status = ? WHERE id = ?", (status, report_id))
        return self.get_tool_scout_report(report_id)

    def create_tool_adoption_job(self, report_id: str, install_approval_id: str) -> dict[str, str]:
        job_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                INSERT INTO tool_adoption_jobs(
                    id, report_id, install_approval_id, final_approval_id, status,
                    install_observation, build_own_result, test_result, created_at, updated_at
                )
                VALUES (?, ?, ?, '', 'waiting_install_approval', '', '', '', ?, ?)
                """,
                (job_id, report_id, install_approval_id, now, now),
            )
        return self.get_tool_adoption_job(job_id) or {}

    def get_tool_adoption_job(self, job_id: str) -> dict[str, str] | None:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            row = conn.execute(
                """
                SELECT id, report_id, install_approval_id, final_approval_id, status,
                       install_observation, build_own_result, test_result, created_at, updated_at
                FROM tool_adoption_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        return _tool_adoption_row(row) if row else None

    def get_tool_adoption_job_by_approval(self, approval_id: str) -> dict[str, str] | None:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            row = conn.execute(
                """
                SELECT id, report_id, install_approval_id, final_approval_id, status,
                       install_observation, build_own_result, test_result, created_at, updated_at
                FROM tool_adoption_jobs
                WHERE install_approval_id = ? OR final_approval_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (approval_id, approval_id),
            ).fetchone()
        return _tool_adoption_row(row) if row else None

    def list_tool_adoption_jobs(self, limit: int = 25) -> list[dict[str, str]]:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            rows = conn.execute(
                """
                SELECT id, report_id, install_approval_id, final_approval_id, status,
                       install_observation, build_own_result, test_result, created_at, updated_at
                FROM tool_adoption_jobs
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_tool_adoption_row(row) for row in rows]

    def update_tool_adoption_job(
        self,
        job_id: str,
        status: str | None = None,
        final_approval_id: str | None = None,
        install_observation: str | None = None,
        build_own_result: str | None = None,
        test_result: str | None = None,
    ) -> dict[str, str] | None:
        current = self.get_tool_adoption_job(job_id)
        if current is None:
            return None
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                UPDATE tool_adoption_jobs
                SET status = ?, final_approval_id = ?, install_observation = ?,
                    build_own_result = ?, test_result = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status if status is not None else current["status"],
                    final_approval_id if final_approval_id is not None else current["final_approval_id"],
                    install_observation if install_observation is not None else current["install_observation"],
                    build_own_result if build_own_result is not None else current["build_own_result"],
                    test_result if test_result is not None else current["test_result"],
                    now,
                    job_id,
                ),
            )
        return self.get_tool_adoption_job(job_id)

    def create_approval(
        self,
        action: str,
        risk: str,
        continuation_type: str = "manual",
        continuation_payload: str = "{}",
    ) -> str:
        approval_id = str(uuid4())
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                INSERT INTO approvals(
                    id, action, risk, status, created_at,
                    continuation_type, continuation_payload, continued_at, continuation_result
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, '', '')
                """,
                (
                    approval_id,
                    action,
                    risk,
                    "pending",
                    datetime.now().isoformat(timespec="seconds"),
                    continuation_type,
                    continuation_payload,
                ),
            )
        return approval_id

    def list_approvals(self, status: str | None = None, limit: int = 25) -> list[dict[str, str]]:
        sql = """
            SELECT id, action, risk, status, created_at,
                   continuation_type, continuation_payload, continued_at, continuation_result
            FROM approvals
        """
        params: list[object] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.config.sqlite_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_approval_row(row) for row in rows]

    def update_approval(self, approval_id: str, status: str) -> dict[str, str] | None:
        if status not in {"approved", "rejected"}:
            raise ValueError("status must be approved or rejected")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute("UPDATE approvals SET status = ? WHERE id = ?", (status, approval_id))
            row = conn.execute(
                """
                SELECT id, action, risk, status, created_at,
                       continuation_type, continuation_payload, continued_at, continuation_result
                FROM approvals
                WHERE id = ?
                """,
                (approval_id,),
            ).fetchone()
        if row is None:
            return None
        return _approval_row(row)

    def get_approval(self, approval_id: str) -> dict[str, str] | None:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            row = conn.execute(
                """
                SELECT id, action, risk, status, created_at,
                       continuation_type, continuation_payload, continued_at, continuation_result
                FROM approvals
                WHERE id = ?
                """,
                (approval_id,),
            ).fetchone()
        if row is None:
            return None
        return _approval_row(row)

    def record_approval_continuation(self, approval_id: str, result: str) -> dict[str, str] | None:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                UPDATE approvals
                SET continued_at = ?, continuation_result = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(timespec="seconds"), result, approval_id),
            )
        return self.get_approval(approval_id)

    def create_install_job(self, approval_id: str, plan: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO install_jobs(approval_id, status, plan, result, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (approval_id, "pending_approval", plan, "", now, now),
            )

    def get_install_job(self, approval_id: str) -> dict[str, str] | None:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            row = conn.execute(
                "SELECT approval_id, status, plan, result, created_at, updated_at FROM install_jobs WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "approval_id": row[0],
            "status": row[1],
            "plan": row[2],
            "result": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }

    def update_install_job(self, approval_id: str, status: str, result: str) -> dict[str, str] | None:
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                "UPDATE install_jobs SET status = ?, result = ?, updated_at = ? WHERE approval_id = ?",
                (status, result, now, approval_id),
            )
        return self.get_install_job(approval_id)

    def create_improvement(self, title: str, motive: str, proposal: str, risk: str = "medium") -> str:
        if risk not in {"low", "medium", "high"}:
            raise ValueError("risk must be low, medium, or high")
        improvement_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                INSERT INTO improvement_backlog(id, title, motive, proposal, risk, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (improvement_id, title, motive, proposal, risk, "pending", now, now),
            )
        return improvement_id

    def list_improvements(self, status: str | None = None, limit: int = 25) -> list[dict[str, str]]:
        sql = """
            SELECT id, title, motive, proposal, risk, status, created_at, updated_at
            FROM improvement_backlog
        """
        params: list[object] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.config.sqlite_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "id": row[0],
                "title": row[1],
                "motive": row[2],
                "proposal": row[3],
                "risk": row[4],
                "status": row[5],
                "created_at": row[6],
                "updated_at": row[7],
            }
            for row in rows
        ]

    def update_improvement(self, improvement_id: str, status: str) -> dict[str, str] | None:
        if status not in {"pending", "approved", "rejected", "done"}:
            raise ValueError("status must be pending, approved, rejected, or done")
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                "UPDATE improvement_backlog SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, improvement_id),
            )
            row = conn.execute(
                """
                SELECT id, title, motive, proposal, risk, status, created_at, updated_at
                FROM improvement_backlog
                WHERE id = ?
                """,
                (improvement_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "title": row[1],
            "motive": row[2],
            "proposal": row[3],
            "risk": row[4],
            "status": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }

    def create_skill(
        self,
        name: str,
        trigger: str,
        steps: str,
        tools: str = "",
        risk: str = "low",
        trust: str = "draft",
        last_reflection: str = "",
    ) -> str:
        if risk not in {"low", "medium", "high"}:
            raise ValueError("risk must be low, medium, or high")
        if trust not in {"draft", "approved", "trusted", "disabled"}:
            raise ValueError("trust must be draft, approved, trusted, or disabled")
        skill_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                INSERT INTO skills(
                    id, name, trigger, steps, tools, risk, trust, success_count, failure_count,
                    last_reflection, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)
                """,
                (skill_id, name, trigger, steps, tools, risk, trust, last_reflection, now, now),
            )
        return skill_id

    def list_skills(self, trust: str | None = None, limit: int = 50) -> list[dict[str, object]]:
        sql = """
            SELECT id, name, trigger, steps, tools, risk, trust, success_count, failure_count,
                   last_reflection, created_at, updated_at
            FROM skills
        """
        params: list[object] = []
        if trust:
            sql += " WHERE trust = ?"
            params.append(trust)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.config.sqlite_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_skill_row(row) for row in rows]

    def get_skill(self, skill_id: str) -> dict[str, object] | None:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            row = conn.execute(
                """
                SELECT id, name, trigger, steps, tools, risk, trust, success_count, failure_count,
                       last_reflection, created_at, updated_at
                FROM skills WHERE id = ?
                """,
                (skill_id,),
            ).fetchone()
        return _skill_row(row) if row else None

    def update_skill_trust(self, skill_id: str, trust: str) -> dict[str, object] | None:
        if trust not in {"draft", "approved", "trusted", "disabled"}:
            raise ValueError("trust must be draft, approved, trusted, or disabled")
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute("UPDATE skills SET trust = ?, updated_at = ? WHERE id = ?", (trust, now, skill_id))
        return self.get_skill(skill_id)

    def record_skill_result(self, skill_id: str, success: bool, reflection: str = "") -> dict[str, object] | None:
        field = "success_count" if success else "failure_count"
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                f"UPDATE skills SET {field} = {field} + 1, last_reflection = ?, updated_at = ? WHERE id = ?",
                (reflection, now, skill_id),
            )
        return self.get_skill(skill_id)

    def create_reflection(
        self,
        task: str,
        outcome: str,
        lesson: str,
        skill_id: str | None = None,
    ) -> str:
        if outcome not in {"success", "failure", "partial"}:
            raise ValueError("outcome must be success, failure, or partial")
        reflection_id = str(uuid4())
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                "INSERT INTO reflections(id, task, outcome, lesson, skill_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (reflection_id, task, outcome, lesson, skill_id, datetime.now().isoformat(timespec="seconds")),
            )
        return reflection_id

    def list_reflections(
        self,
        outcome: str | None = None,
        skill_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, str | None]]:
        sql = "SELECT id, task, outcome, lesson, skill_id, created_at FROM reflections"
        clauses: list[str] = []
        params: list[object] = []
        if outcome:
            clauses.append("outcome = ?")
            params.append(outcome)
        if skill_id:
            clauses.append("skill_id = ?")
            params.append(skill_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.config.sqlite_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {"id": row[0], "task": row[1], "outcome": row[2], "lesson": row[3], "skill_id": row[4], "created_at": row[5]}
            for row in rows
        ]

    def create_skill_evaluation(self, skill_id: str, result: str, score: int, notes: str) -> str:
        if result not in {"pass", "fail", "needs_review"}:
            raise ValueError("result must be pass, fail, or needs_review")
        if not 0 <= score <= 100:
            raise ValueError("score must be between 0 and 100")
        evaluation_id = str(uuid4())
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.execute(
                """
                INSERT INTO skill_evaluations(id, skill_id, result, score, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (evaluation_id, skill_id, result, score, notes, datetime.now().isoformat(timespec="seconds")),
            )
        return evaluation_id

    def list_skill_evaluations(self, skill_id: str | None = None, limit: int = 50) -> list[dict[str, object]]:
        sql = "SELECT id, skill_id, result, score, notes, created_at FROM skill_evaluations"
        params: list[object] = []
        if skill_id:
            sql += " WHERE skill_id = ?"
            params.append(skill_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.config.sqlite_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {"id": row[0], "skill_id": row[1], "result": row[2], "score": row[3], "notes": row[4], "created_at": row[5]}
            for row in rows
        ]


def _skill_row(row: tuple[object, ...]) -> dict[str, object]:
    return {
        "id": row[0],
        "name": row[1],
        "trigger": row[2],
        "steps": row[3],
        "tools": row[4],
        "risk": row[5],
        "trust": row[6],
        "success_count": row[7],
        "failure_count": row[8],
        "last_reflection": row[9],
        "created_at": row[10],
        "updated_at": row[11],
    }


def _long_task_row(row: tuple[object, ...]) -> dict[str, str]:
    return {
        "id": str(row[0]),
        "title": str(row[1]),
        "goal": str(row[2]),
        "status": str(row[3]),
        "priority": str(row[4]),
        "progress": str(row[5]),
        "next_step": str(row[6]),
        "source_session_id": str(row[7] or ""),
        "created_at": str(row[8]),
        "updated_at": str(row[9]),
    }


def _approval_row(row: tuple[object, ...]) -> dict[str, str]:
    return {
        "id": str(row[0]),
        "action": str(row[1]),
        "risk": str(row[2]),
        "status": str(row[3]),
        "created_at": str(row[4]),
        "continuation_type": str(row[5] or "manual"),
        "continuation_payload": str(row[6] or "{}"),
        "continued_at": str(row[7] or ""),
        "continuation_result": str(row[8] or ""),
    }


def _tool_scout_row(row: tuple[object, ...]) -> dict[str, str]:
    return {
        "id": str(row[0]),
        "task": str(row[1]),
        "capability": str(row[2]),
        "recommendation": str(row[3]),
        "source": str(row[4]),
        "license_note": str(row[5]),
        "build_own_plan": str(row[6]),
        "status": str(row[7]),
        "improvement_id": str(row[8] or ""),
        "created_at": str(row[9]),
    }


def _tool_adoption_row(row: tuple[object, ...]) -> dict[str, str]:
    return {
        "id": str(row[0]),
        "report_id": str(row[1]),
        "install_approval_id": str(row[2] or ""),
        "final_approval_id": str(row[3] or ""),
        "status": str(row[4]),
        "install_observation": str(row[5]),
        "build_own_result": str(row[6]),
        "test_result": str(row[7]),
        "created_at": str(row[8]),
        "updated_at": str(row[9]),
    }


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _json_load(value: object, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _chat_title(content: str) -> str:
    title = " ".join(content.strip().split())
    return title[:48] + ("..." if len(title) > 48 else "") if title else "New chat"


def _search_terms(query: str) -> list[str]:
    stop_words = {
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "for", "from",
        "about", "anything", "did", "does", "how", "i", "in", "is", "it", "me", "more",
        "my", "of", "older", "on", "or", "related", "say", "said", "task", "tasks",
        "tell", "that", "the", "this", "to", "what", "with", "work", "you",
    }
    terms: list[str] = []
    for raw in query.lower().replace("\n", " ").split():
        term = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_"})
        if len(term) >= 3 and term not in stop_words and term not in terms:
            terms.append(term)
    return terms[:8]


def _clip(text: str, limit: int = 320) -> str:
    clean = " ".join(text.split())
    return clean[:limit] + ("..." if len(clean) > limit else "")


memory = MemorySystem()


def remember(text: str, category: str = "general") -> str:
    return memory.remember(text, category=category)


def recall(query: str, n_results: int = 5) -> list[str]:
    return memory.recall(query, n_results=n_results)


def build_memory_context(
    prompt: str,
    chat_session_id: str | None = None,
    current_chat_message_id: str | None = None,
    related_messages: list[dict[str, object]] | None = None,
) -> str:
    docs = recall(prompt, n_results=5)
    chat_hits = (
        related_messages
        if related_messages is not None
        else memory.search_chat_messages(
            prompt,
            limit=8,
            session_id=chat_session_id,
            exclude_message_id=current_chat_message_id,
        )
    )
    task_hits = memory.find_relevant_long_tasks(prompt, limit=5)
    sections: list[str] = []
    if docs:
        sections.append("Stored semantic memories:\n" + "\n".join(f"- {_clip(doc)}" for doc in docs))
    if chat_hits:
        sections.append(
            "Related older chat history:\n"
            + "\n".join(
                f"- [{item['created_at']}] {item['role']} "
                + f"(score {item.get('score', 1)}): {_clip(str(item['content']))}"
                for item in chat_hits
            )
        )
    if task_hits:
        sections.append(
            "Active or related long tasks:\n"
            + "\n".join(
                "- "
                + f"{item['title']} ({item['status']}, {item['priority']}): "
                + f"goal={_clip(item['goal'], 180)}; "
                + f"progress={_clip(item['progress'] or 'not recorded yet', 180)}; "
                + f"next={_clip(item['next_step'] or 'ask Bala for the next approved step', 180)}"
                for item in task_hits
            )
        )
    return "\n\n".join(sections)
