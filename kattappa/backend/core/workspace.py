from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event


class WorkspaceManager:
    """Manages Workspace context states, saving and restoring active projects, goals, and chat sessions."""

    _schema_ensured = False

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        if not cls._schema_ensured:
            cls._ensure_schema(conn)
            cls._schema_ensured = True
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                workspace_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                project_ids TEXT NOT NULL DEFAULT '[]',
                goal_ids TEXT NOT NULL DEFAULT '[]',
                chat_session_id TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.commit()

    @classmethod
    def create_workspace(
        cls,
        name: str,
        description: Optional[str] = None,
        project_ids: Optional[List[str]] = None,
        goal_ids: Optional[List[str]] = None,
        chat_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a new workspace context."""
        now = time.time()
        w_id = f"workspace_{uuid.uuid4().hex[:8]}"
        p_json = json.dumps(project_ids or [])
        g_json = json.dumps(goal_ids or [])

        conn = cls._get_sqlite_conn()
        try:
            conn.execute(
                """
                INSERT INTO workspaces (workspace_id, name, description, project_ids, goal_ids, chat_session_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (w_id, name.strip(), description, p_json, g_json, chat_session_id, now, now)
            )
            conn.commit()
            log_event("workspace_created", {"workspace_id": w_id, "name": name})
        finally:
            conn.close()

        return cls.get_workspace(w_id)

    @classmethod
    def get_workspace(cls, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves workspace context state by ID."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM workspaces WHERE workspace_id = ?", (workspace_id,)).fetchone()
            if not row:
                return None
            res = dict(row)
            res["project_ids"] = json.loads(res["project_ids"])
            res["goal_ids"] = json.loads(res["goal_ids"])
            return res
        finally:
            conn.close()

    @classmethod
    def list_workspaces(cls) -> List[Dict[str, Any]]:
        """Lists all workspaces in the system."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM workspaces ORDER BY updated_at DESC").fetchall()
            results = []
            for r in rows:
                res = dict(r)
                res["project_ids"] = json.loads(res["project_ids"])
                res["goal_ids"] = json.loads(res["goal_ids"])
                results.append(res)
            return results
        finally:
            conn.close()

    @classmethod
    def update_workspace(
        cls,
        workspace_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        project_ids: Optional[List[str]] = None,
        goal_ids: Optional[List[str]] = None,
        chat_session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Updates an existing workspace's fields."""
        now = time.time()
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM workspaces WHERE workspace_id = ?", (workspace_id,)).fetchone()
            if not row:
                return None

            updates = []
            params = []
            if name is not None:
                updates.append("name = ?")
                params.append(name.strip())
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if project_ids is not None:
                updates.append("project_ids = ?")
                params.append(json.dumps(project_ids))
            if goal_ids is not None:
                updates.append("goal_ids = ?")
                params.append(json.dumps(goal_ids))
            if chat_session_id is not None:
                updates.append("chat_session_id = ?")
                params.append(chat_session_id)

            if updates:
                updates.append("updated_at = ?")
                params.append(now)
                params.append(workspace_id)
                conn.execute(f"UPDATE workspaces SET {', '.join(updates)} WHERE workspace_id = ?", tuple(params))
                conn.commit()
                log_event("workspace_updated", {"workspace_id": workspace_id})
        finally:
            conn.close()

        return cls.get_workspace(workspace_id)

    @classmethod
    def delete_workspace(cls, workspace_id: str) -> bool:
        """Deletes a workspace by ID."""
        conn = cls._get_sqlite_conn()
        try:
            cur = conn.execute("DELETE FROM workspaces WHERE workspace_id = ?", (workspace_id,))
            conn.commit()
            log_event("workspace_deleted", {"workspace_id": workspace_id})
            return cur.rowcount > 0
        finally:
            conn.close()
