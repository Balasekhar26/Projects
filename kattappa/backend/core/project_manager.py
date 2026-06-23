from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event


class ProjectManager:
    """Project Manager Subsystem (Layer 8 - Step 8.6).

    Coordinates multi-agent workflows using a blackboard architecture. Manages task graphs,
    dependency checks, and shared variables to coordinate actions across specialist agents.
    """

    _lock = threading.RLock()
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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS hm_project_tasks (
                    task_id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    assigned_agent TEXT NOT NULL,
                    dependencies TEXT NOT NULL DEFAULT '[]', -- JSON list of task_ids
                    status TEXT NOT NULL DEFAULT 'blocked', -- 'blocked', 'ready', 'running', 'completed', 'failed'
                    context_blackboard TEXT NOT NULL DEFAULT '{}', -- JSON task output parameters
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_project_tasks_name ON hm_project_tasks(project_name);
                CREATE INDEX IF NOT EXISTS idx_project_tasks_status ON hm_project_tasks(status);

                CREATE TABLE IF NOT EXISTS hm_project_blackboard (
                    project_name TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL, -- JSON value
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (project_name, key)
                );
                CREATE INDEX IF NOT EXISTS idx_project_blackboard_name ON hm_project_blackboard(project_name);
                """
            )
            conn.commit()

    @classmethod
    def create_project_task(
        cls,
        task_id: str,
        project_name: str,
        title: str,
        assigned_agent: str,
        dependencies: Optional[List[str]] = None,
    ) -> None:
        """Creates a new multi-agent project task with dependencies."""
        deps = dependencies or []
        deps_str = json.dumps(deps)
        status = "ready" if not deps else "blocked"
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_project_tasks (task_id, project_name, title, assigned_agent, dependencies, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        project_name = excluded.project_name,
                        title = excluded.title,
                        assigned_agent = excluded.assigned_agent,
                        dependencies = excluded.dependencies,
                        status = excluded.status,
                        updated_at = excluded.updated_at
                    """,
                    (task_id.strip(), project_name.strip().lower(), title.strip(), assigned_agent.strip().lower(), deps_str, status, now)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_project_tasks(cls, project_name: str) -> List[Dict[str, Any]]:
        """Retrieves all tasks associated with a project."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hm_project_tasks WHERE project_name = ? ORDER BY updated_at ASC",
                (project_name.lower().strip(),)
            ).fetchall()
            results = []
            for r in rows:
                results.append({
                    "task_id": r["task_id"],
                    "project_name": r["project_name"],
                    "title": r["title"],
                    "assigned_agent": r["assigned_agent"],
                    "dependencies": json.loads(r["dependencies"]),
                    "status": r["status"],
                    "context_blackboard": json.loads(r["context_blackboard"]),
                    "updated_at": r["updated_at"],
                })
            return results
        finally:
            conn.close()

    @classmethod
    def update_task_state(cls, task_id: str, status: str, context_blackboard: Optional[Dict[str, Any]] = None) -> None:
        """Updates the status and context parameters of a task, and updates dependent blocked tasks."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Get current task
                row = conn.execute("SELECT * FROM hm_project_tasks WHERE task_id = ?", (task_id,)).fetchone()
                if not row:
                    raise ValueError(f"Task '{task_id}' not found.")

                project_name = row["project_name"]
                cb = json.loads(row["context_blackboard"])
                if context_blackboard:
                    cb.update(context_blackboard)

                conn.execute(
                    """
                    UPDATE hm_project_tasks
                    SET status = ?, context_blackboard = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (status.strip().lower(), json.dumps(cb), now, task_id)
                )

                # Re-evaluate all tasks in the project to check if blocked ones are now ready
                all_tasks = conn.execute("SELECT * FROM hm_project_tasks WHERE project_name = ?", (project_name,)).fetchall()
                completed_ids = {t["task_id"] for t in all_tasks if t["status"] == "completed"}

                for t in all_tasks:
                    if t["status"] == "blocked":
                        deps = json.loads(t["dependencies"])
                        if deps and all(dep_id in completed_ids for dep_id in deps):
                            conn.execute(
                                "UPDATE hm_project_tasks SET status = 'ready', updated_at = ? WHERE task_id = ?",
                                (now, t["task_id"])
                            )

                conn.commit()
                log_event("project_task_update", {"task_id": task_id, "status": status})
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_ready_tasks(cls, project_name: str) -> List[Dict[str, Any]]:
        """Returns all tasks in a project that are currently in 'ready' status."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hm_project_tasks WHERE project_name = ? AND status = 'ready'",
                (project_name.lower().strip(),)
            ).fetchall()
            results = []
            for r in rows:
                results.append({
                    "task_id": r["task_id"],
                    "project_name": r["project_name"],
                    "title": r["title"],
                    "assigned_agent": r["assigned_agent"],
                    "dependencies": json.loads(r["dependencies"]),
                    "status": r["status"],
                    "context_blackboard": json.loads(r["context_blackboard"]),
                    "updated_at": r["updated_at"],
                })
            return results
        finally:
            conn.close()

    @classmethod
    def write_to_blackboard(cls, project_name: str, key: str, value: Any) -> None:
        """Writes a global key-value pair shared variable to the project blackboard."""
        val_str = json.dumps(value)
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_project_blackboard (project_name, key, value, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(project_name, key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (project_name.strip().lower(), key.strip(), val_str, now)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def read_from_blackboard(cls, project_name: str, key: str) -> Optional[Any]:
        """Reads a shared variable value from the project blackboard."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT value FROM hm_project_blackboard WHERE project_name = ? AND key = ?",
                (project_name.strip().lower(), key.strip())
            ).fetchone()
            if not row:
                return None
            return json.loads(row["value"])
        finally:
            conn.close()
