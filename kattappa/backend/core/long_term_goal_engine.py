from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event


class LongTermGoalEngine:
    """Long Term Goal Engine Subsystem (Layer 8 - Step 8.7).

    Manages deep hierarchical goals, executes preconditions checks, and triggers
    success verification criteria rules.
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
                CREATE TABLE IF NOT EXISTS hm_long_term_goals (
                    goal_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    parent_id TEXT,
                    preconditions TEXT NOT NULL DEFAULT '{}', -- JSON preconditions (e.g. {"blackboard_key_present": "ready_flag"})
                    success_criteria TEXT NOT NULL DEFAULT '{}', -- JSON success checks (e.g. {"file_exists": "main.py"})
                    status TEXT NOT NULL DEFAULT 'dormant', -- 'dormant', 'active', 'completed', 'failed'
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (parent_id) REFERENCES hm_long_term_goals(goal_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_lt_goals_parent ON hm_long_term_goals(parent_id);
                CREATE INDEX IF NOT EXISTS idx_lt_goals_status ON hm_long_term_goals(status);
                """
            )
            conn.commit()

    @classmethod
    def register_goal(
        cls,
        goal_id: str,
        title: str,
        description: str,
        parent_id: Optional[str] = None,
        preconditions: Optional[Dict[str, Any]] = None,
        success_criteria: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registers a goal in the long-term hierarchy."""
        pre = preconditions or {}
        succ = success_criteria or {}
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # If parent_id provided, ensure it exists
                if parent_id:
                    parent = conn.execute("SELECT goal_id FROM hm_long_term_goals WHERE goal_id = ?", (parent_id,)).fetchone()
                    if not parent:
                        raise ValueError(f"Parent goal '{parent_id}' does not exist.")

                conn.execute(
                    """
                    INSERT INTO hm_long_term_goals (goal_id, title, description, parent_id, preconditions, success_criteria, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'dormant', ?, ?)
                    ON CONFLICT(goal_id) DO UPDATE SET
                        title = excluded.title,
                        description = excluded.description,
                        parent_id = excluded.parent_id,
                        preconditions = excluded.preconditions,
                        success_criteria = excluded.success_criteria,
                        updated_at = excluded.updated_at
                    """,
                    (goal_id.strip(), title.strip(), description.strip(), parent_id, json.dumps(pre), json.dumps(succ), now, now)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_goal(cls, goal_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single long-term goal's details."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM hm_long_term_goals WHERE goal_id = ?", (goal_id,)).fetchone()
            if not row:
                return None
            return {
                "goal_id": row["goal_id"],
                "title": row["title"],
                "description": row["description"],
                "parent_id": row["parent_id"],
                "preconditions": json.loads(row["preconditions"]),
                "success_criteria": json.loads(row["success_criteria"]),
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        finally:
            conn.close()

    @classmethod
    def get_goal_hierarchy(cls) -> List[Dict[str, Any]]:
        """Assembles and returns the full tree hierarchy of goals."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM hm_long_term_goals ORDER BY created_at ASC").fetchall()
            goals = [dict(r) for r in rows]

            for g in goals:
                g["preconditions"] = json.loads(g["preconditions"])
                g["success_criteria"] = json.loads(g["success_criteria"])
                g["children"] = []

            by_id = {g["goal_id"]: g for g in goals}
            roots = []

            for g in goals:
                p_id = g["parent_id"]
                if p_id and p_id in by_id:
                    by_id[p_id]["children"].append(g)
                else:
                    roots.append(g)

            return roots
        finally:
            conn.close()

    @classmethod
    def evaluate_preconditions(cls, goal_id: str, context: Dict[str, Any]) -> bool:
        """Evaluates whether all precondition rules for starting a goal are satisfied by the context."""
        goal = cls.get_goal(goal_id)
        if not goal:
            return False

        preconditions = goal["preconditions"]
        if not preconditions:
            return True

        # Check required blackboard keys
        req_blackboard_key = preconditions.get("blackboard_key_present")
        if req_blackboard_key:
            project_name = context.get("project_name")
            if not project_name:
                return False
            try:
                from backend.core.project_manager import ProjectManager
                val = ProjectManager.read_from_blackboard(project_name, req_blackboard_key)
                if val is None:
                    return False
            except Exception:
                return False

        # Check context values directly
        for key, expected_value in preconditions.items():
            if key == "blackboard_key_present":
                continue
            if context.get(key) != expected_value:
                return False

        return True

    @classmethod
    def check_goal_success(cls, goal_id: str, context: Dict[str, Any]) -> bool:
        """Checks if a goal's verification criteria are met."""
        goal = cls.get_goal(goal_id)
        if not goal:
            return False

        success_criteria = goal["success_criteria"]
        if not success_criteria:
            return True

        # Check required files exist
        req_file = success_criteria.get("file_exists")
        if req_file:
            from pathlib import Path
            file_path = Path(req_file)
            if not file_path.is_absolute() and "workspace_dir" in context:
                file_path = Path(context["workspace_dir"]) / file_path
            if not file_path.exists():
                return False

        # Check variables match expected outcome values
        for key, expected_value in success_criteria.items():
            if key == "file_exists":
                continue
            if context.get(key) != expected_value:
                return False

        return True

    @classmethod
    def update_goal_status(cls, goal_id: str, status: str) -> None:
        """Updates the operational status of a goal."""
        allowed_statuses = {"dormant", "active", "completed", "failed"}
        clean_status = status.strip().lower()
        if clean_status not in allowed_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of {allowed_statuses}")

        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    "UPDATE hm_long_term_goals SET status = ?, updated_at = ? WHERE goal_id = ?",
                    (clean_status, now, goal_id)
                )
                conn.commit()
                log_event("long_term_goal_status", {"goal_id": goal_id, "status": clean_status})
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
