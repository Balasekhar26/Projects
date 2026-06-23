from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event


class WorkflowMemory:
    """Workflow Memory Subsystem (Layer 8 - Step 8.1).

    Persists full executed workflows, plan steps, actual outcomes, durations,
    and recovery/rollback actions to detect recurring errors and trace history.
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
            else:
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hm_workflow_memory_runs'")
                if not cursor.fetchone():
                    cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS hm_workflow_memory_runs (
                    workflow_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running', -- 'running', 'completed', 'failed', 'aborted'
                    success BOOLEAN NOT NULL DEFAULT 0,
                    total_duration_ms INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON hm_workflow_memory_runs(status);

                CREATE TABLE IF NOT EXISTS hm_workflow_memory_steps (
                    step_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    agent TEXT NOT NULL,
                    action TEXT NOT NULL,
                    success BOOLEAN NOT NULL DEFAULT 0,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    rollback_executed BOOLEAN NOT NULL DEFAULT 0,
                    rollback_success BOOLEAN, -- NULL if not executed, 1/0 for success/failure
                    error_message TEXT,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (workflow_id) REFERENCES hm_workflow_memory_runs(workflow_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_workflow_steps_run ON hm_workflow_memory_steps(workflow_id);
                """
            )
            conn.commit()

    @classmethod
    def save_workflow_run(
        cls,
        workflow_id: str,
        goal: str,
        status: str,
        success: bool,
        total_duration_ms: int,
        steps: List[Dict[str, Any]],
    ) -> None:
        """Saves a workflow run and all its execution steps to the database."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_workflow_memory_runs (workflow_id, goal, status, success, total_duration_ms, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(workflow_id) DO UPDATE SET
                        status = excluded.status,
                        success = excluded.success,
                        total_duration_ms = excluded.total_duration_ms,
                        updated_at = excluded.updated_at
                    """,
                    (workflow_id, goal.strip(), status, 1 if success else 0, total_duration_ms, now, now)
                )

                # Delete existing steps if updating to prevent duplication
                conn.execute("DELETE FROM hm_workflow_memory_steps WHERE workflow_id = ?", (workflow_id,))

                for index, step in enumerate(steps):
                    step_id = step.get("step_id") or f"{workflow_id}_step_{index}"
                    rollback_success = step.get("rollback_success")
                    if rollback_success is not None:
                        rollback_success_val = 1 if rollback_success else 0
                    else:
                        rollback_success_val = None

                    conn.execute(
                        """
                        INSERT INTO hm_workflow_memory_steps (
                            step_id, workflow_id, step_index, agent, action, success,
                            duration_ms, rollback_executed, rollback_success, error_message, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            step_id,
                            workflow_id,
                            index,
                            step.get("agent", "unknown").lower(),
                            step.get("action", "UNKNOWN").upper(),
                            1 if step.get("success", False) else 0,
                            int(step.get("duration_ms", 0)),
                            1 if step.get("rollback_executed", False) else 0,
                            rollback_success_val,
                            step.get("error_message"),
                            now
                        )
                    )
                conn.commit()
                log_event("workflow_memory", {"workflow_id": workflow_id, "status": status, "success": success})
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_workflow_run(cls, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single workflow run along with its steps."""
        conn = cls._get_sqlite_conn()
        try:
            run_row = conn.execute(
                "SELECT * FROM hm_workflow_memory_runs WHERE workflow_id = ?",
                (workflow_id,)
            ).fetchone()

            if not run_row:
                return None

            step_rows = conn.execute(
                "SELECT * FROM hm_workflow_memory_steps WHERE workflow_id = ? ORDER BY step_index ASC",
                (workflow_id,)
            ).fetchall()

            steps = []
            for s in step_rows:
                steps.append({
                    "step_id": s["step_id"],
                    "step_index": s["step_index"],
                    "agent": s["agent"],
                    "action": s["action"],
                    "success": bool(s["success"]),
                    "duration_ms": s["duration_ms"],
                    "rollback_executed": bool(s["rollback_executed"]),
                    "rollback_success": None if s["rollback_success"] is None else bool(s["rollback_success"]),
                    "error_message": s["error_message"],
                })

            run_dict = dict(run_row)
            run_dict["success"] = bool(run_dict["success"])
            run_dict["steps"] = steps
            return run_dict
        finally:
            conn.close()

    @classmethod
    def search_workflows_by_goal(cls, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Searches past workflows containing matching goal strings."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hm_workflow_memory_runs WHERE goal LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", limit)
            ).fetchall()

            results = []
            for r in rows:
                results.append({
                    "workflow_id": r["workflow_id"],
                    "goal": r["goal"],
                    "status": r["status"],
                    "success": bool(r["success"]),
                    "total_duration_ms": r["total_duration_ms"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                })
            return results
        finally:
            conn.close()

    @classmethod
    def get_recent_workflow_runs(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns the most recent workflow runs."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hm_workflow_memory_runs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()

            results = []
            for r in rows:
                results.append({
                    "workflow_id": r["workflow_id"],
                    "goal": r["goal"],
                    "status": r["status"],
                    "success": bool(r["success"]),
                    "total_duration_ms": r["total_duration_ms"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                })
            return results
        finally:
            conn.close()
