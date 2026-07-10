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
            try:
                legacy_sqlite.unlink()
            except Exception:
                pass

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
            try:
                shutil.rmtree(legacy_chroma)
            except Exception:
                pass

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

    def _chat_collection(self) -> Any:
        if not hasattr(self, "chat_col") or self.chat_col is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

            if self.chroma is None:
                self.chroma = chromadb.PersistentClient(
                    path=str(self.config.chroma_path),
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
            self.chat_col = self.chroma.get_or_create_collection(
                "kattappa_chat_messages",
                embedding_function=DefaultEmbeddingFunction(),
            )
            self._sync_chat_messages_to_chroma()
        return self.chat_col

    def _sync_chat_messages_to_chroma(self) -> None:
        try:
            col = self.chat_col
            count = col.count()
            with sqlite3.connect(self.config.sqlite_path) as conn:
                rows = conn.execute("SELECT id, session_id, role, content, agent, risk, created_at FROM chat_messages").fetchall()
            if len(rows) > count:
                ids = []
                docs = []
                metadatas = []
                for row in rows:
                    ids.append(row[0])
                    docs.append(row[3])
                    metadatas.append({
                        "session_id": row[1],
                        "role": row[2],
                        "agent": row[4],
                        "risk": row[5],
                        "created_at": row[6]
                    })
                chunk_size = 200
                for i in range(0, len(ids), chunk_size):
                    col.add(
                        ids=ids[i:i+chunk_size],
                        documents=docs[i:i+chunk_size],
                        metadatas=metadatas[i:i+chunk_size]
                    )
        except Exception:
            pass

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
                CREATE TABLE IF NOT EXISTS sage_concepts (
                    id TEXT PRIMARY KEY,
                    concept TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    connections TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sage_user_profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sage_archetypes (
                    name TEXT PRIMARY KEY,
                    weight REAL NOT NULL DEFAULT 0.2,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # Seed default archetypes if they don't exist
            cursor = conn.execute("SELECT COUNT(*) FROM sage_archetypes")
            if cursor.fetchone()[0] == 0:
                now = datetime.now().isoformat(timespec="seconds")
                defaults = [
                    ("Rama", 0.2, now),
                    ("Krishna", 0.2, now),
                    ("Brahma", 0.2, now),
                    ("Shiva", 0.2, now),
                    ("Kattappa", 0.2, now),
                ]
                conn.executemany(
                    "INSERT INTO sage_archetypes (name, weight, updated_at) VALUES (?, ?, ?)",
                    defaults
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
        documents = result.get("documents", [[]])[0]
        distances = result.get("distances", [[]])[0]

        if not ids:
            return []

        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            conn.executemany(
                "UPDATE memories SET last_accessed = ? WHERE id = ?",
                [(now, memory_id) for memory_id in ids],
            )
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"SELECT id, decay_score FROM memories WHERE id IN ({placeholders})",
                ids
            ).fetchall()
            decay_scores = {r[0]: r[1] for r in rows}

        scored_docs = []
        for memory_id, doc, dist in zip(ids, documents, distances):
            decay = decay_scores.get(memory_id, 1.0)
            score = (1.0 - min(dist, 1.0)) * decay
            scored_docs.append((doc, score))

        scored_docs.sort(key=lambda item: item[1], reverse=True)
        return [doc for doc, _ in scored_docs]


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
        
        try:
            self._chat_collection().add(
                ids=[message_id],
                documents=[content],
                metadatas=[{
                    "session_id": session_id,
                    "role": role,
                    "agent": agent,
                    "risk": risk,
                    "created_at": now
                }]
            )
        except Exception:
            pass

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

    def rate_chat_message(self, message_id: str, rating: int) -> dict[str, str] | None:
        if rating not in {-1, 1}:
            raise ValueError("rating must be 1 or -1")
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.config.sqlite_path) as conn:
            row = conn.execute(
                """
                SELECT id, session_id, role, content, agent, risk, metadata, created_at
                FROM chat_messages
                WHERE id = ?
                """,
                (message_id,),
            ).fetchone()
            if row is None:
                return None
            if row[2] != "assistant":
                raise ValueError("only assistant messages can be rated")
            try:
                metadata = json.loads(row[6] or "{}")
            except json.JSONDecodeError:
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            metadata["sage_feedback_rating"] = rating
            metadata["response_rating"] = rating
            metadata["rated_at"] = now
            stored_metadata = json.dumps(metadata)
            conn.execute(
                "UPDATE chat_messages SET metadata = ? WHERE id = ?",
                (stored_metadata, message_id),
            )
            conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, row[1]))
        return {
            "id": row[0],
            "session_id": row[1],
            "role": row[2],
            "content": row[3],
            "agent": row[4],
            "risk": row[5],
            "metadata": stored_metadata,
            "created_at": row[7],
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

    def list_chat_messages(self, session_id: str, limit: int = 2000) -> list[dict[str, str]]:
        with sqlite3.connect(self.config.sqlite_path) as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content, agent, risk, metadata, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY rowid DESC
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
            for row in reversed(rows)
        ]

    def search_chat_messages(
        self,
        query: str,
        limit: int = 8,
        session_id: str | None = None,
        exclude_message_id: str | None = None,
    ) -> list[dict[str, object]]:
        if not query.strip():
            return []

        try:
            col = self._chat_collection()
            if col.count() == 0:
                return []

            where_filter = {}
            if session_id:
                where_filter["session_id"] = session_id

            results = col.query(
                query_texts=[query],
                n_results=limit + (1 if exclude_message_id else 0),
                where=where_filter if where_filter else None
            )

            matches: list[dict[str, object]] = []
            if results and results.get("documents") and results["documents"][0]:
                documents = results["documents"][0]
                ids = results["ids"][0]
                metadatas = results["metadatas"][0]
                distances = results["distances"][0]

                for doc, msg_id, meta, dist in zip(documents, ids, metadatas, distances):
                    if exclude_message_id and msg_id == exclude_message_id:
                        continue
                    # dist is L2/Cosine, map it to a score [0, 1]
                    score = round(1.0 - min(dist, 1.0), 3)
                    matches.append({
                        "id": msg_id,
                        "session_id": meta["session_id"],
                        "session_title": "Active Chat",
                        "role": meta["role"],
                        "content": doc,
                        "agent": meta["agent"],
                        "risk": meta["risk"],
                        "created_at": meta["created_at"],
                        "score": score
                    })

            matches.sort(key=lambda item: (float(item["score"]), str(item["created_at"])), reverse=True)
            return matches[:limit]
        except Exception:
            return self._search_chat_messages_sqlite_fallback(query, limit, session_id, exclude_message_id)

    def _search_chat_messages_sqlite_fallback(
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


_cached_git_status: str = ""
_last_git_status_time: float = 0.0


def get_git_status() -> str:
    global _cached_git_status, _last_git_status_time
    import time
    now = time.time()
    if now - _last_git_status_time < 30.0 and _cached_git_status:
        return _cached_git_status
    import subprocess
    try:
        config = load_config()
        workspace = config.workspace_dir
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=workspace,
            timeout=3,
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            if not lines:
                _cached_git_status = "Git workspace is clean."
            else:
                _cached_git_status = "Active changes in workspace:\n" + "\n".join(f"- {line}" for line in lines[:15])
            _last_git_status_time = now
            return _cached_git_status
        return "Not a git repository or git command failed."
    except Exception as exc:
        return f"Could not retrieve git status: {exc}"


def build_memory_context(
    prompt: str,
    chat_session_id: str | None = None,
    current_chat_message_id: str | None = None,
    related_messages: list[dict[str, object]] | None = None,
) -> str:
    from backend.core.adaptive_runtime import AdaptiveContext
    profile = memory.config.hardware_profile
    limits = AdaptiveContext.get_dynamic_budget(prompt, profile)
    max_context_tokens = limits["max_context_tokens"]
    history_max_turns = limits["history_max_turns"]

    # Retrieve docs matching budget capacity
    n_results = 2 if max_context_tokens <= 1000 else 5
    docs = recall(prompt, n_results=n_results)
    
    chat_hits = (
        related_messages
        if related_messages is not None
        else memory.search_chat_messages(
            prompt,
            limit=history_max_turns,
            session_id=chat_session_id,
            exclude_message_id=current_chat_message_id,
        )
    )
    task_hits = memory.find_relevant_long_tasks(prompt, limit=5)
    
    recent_messages = []
    if chat_session_id:
        try:
            all_msgs = memory.list_chat_messages(chat_session_id, limit=50)
            filtered = [m for m in all_msgs if m["id"] != current_chat_message_id]
            recent_messages = filtered[-history_max_turns:]
        except Exception:
            pass

    sections: list[str] = []
    if recent_messages:
        sections.append(
            "Recent session thread history (chronological):\n"
            + "\n".join(
                f"- {m['role']}: {_clip(str(m['content']))}"
                for m in recent_messages
            )
        )
    if docs:
        sections.append("Stored semantic memories:\n" + "\n".join(f"- {_clip(doc)}" for doc in docs))
    if chat_hits:
        sections.append(
            "Related older chat history (semantic search hits):\n"
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
        
    git_status = get_git_status()
    sections.append(f"Local Workspace Status:\n{git_status}")
    
    return "\n\n".join(sections)
