from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event


class WorkingMemory:
    """Working Memory Subsystem (Layer 2).
    
    Provides a transient workspace tracking goals, task stacks, tool decisions,
    intermediate plans, thoughts, and context state summaries during execution.
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
                CREATE TABLE IF NOT EXISTS hm_working_memory_sessions (
                    id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active' -- 'active', 'archived'
                );

                CREATE TABLE IF NOT EXISTS hm_working_memory_goals (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    goal_text TEXT NOT NULL,
                    parent_goal_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'completed', 'suspended'
                    created_at REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES hm_working_memory_sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY (parent_goal_id) REFERENCES hm_working_memory_goals(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_hm_wm_goals_session ON hm_working_memory_goals(session_id);

                CREATE TABLE IF NOT EXISTS hm_working_memory_tasks (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    task_description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'running', 'completed', 'failed'
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (goal_id) REFERENCES hm_working_memory_goals(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_hm_wm_tasks_goal ON hm_working_memory_tasks(goal_id);

                CREATE TABLE IF NOT EXISTS hm_working_memory_traces (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    goal_id TEXT,
                    task_id TEXT,
                    trace_type TEXT NOT NULL, -- 'thought', 'tool_call', 'tool_response', 'plan_update'
                    content TEXT NOT NULL,
                    active_guardrails TEXT NOT NULL DEFAULT '[]', -- JSON list of guardrail IDs active during step
                    created_at REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES hm_working_memory_sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY (goal_id) REFERENCES hm_working_memory_goals(id) ON DELETE CASCADE,
                    FOREIGN KEY (task_id) REFERENCES hm_working_memory_tasks(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_hm_wm_traces_session ON hm_working_memory_traces(session_id);
                """
            )
            conn.commit()

    @classmethod
    def initialize_session(cls, session_id: str) -> None:
        """Initializes or touches a working memory session."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_working_memory_sessions (id, created_at, updated_at, status)
                    VALUES (?, ?, ?, 'active')
                    ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
                    """,
                    (session_id, now, now)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def push_goal(cls, session_id: str, goal_text: str, parent_goal_id: Optional[str] = None) -> str:
        """Pushes a goal onto the stack for a session."""
        cls.initialize_session(session_id)
        goal_id = str(uuid.uuid4())
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                if parent_goal_id:
                    parent = conn.execute("SELECT id FROM hm_working_memory_goals WHERE id = ?", (parent_goal_id,)).fetchone()
                    if not parent:
                        raise ValueError(f"Parent goal {parent_goal_id} does not exist.")
                
                conn.execute(
                    """
                    INSERT INTO hm_working_memory_goals (id, session_id, goal_text, parent_goal_id, status, created_at)
                    VALUES (?, ?, ?, ?, 'active', ?)
                    """,
                    (goal_id, session_id, goal_text.strip(), parent_goal_id, now)
                )
                conn.commit()
                return goal_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def complete_goal(cls, goal_id: str) -> bool:
        """Marks a goal as completed."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cur = conn.execute(
                    "UPDATE hm_working_memory_goals SET status = 'completed' WHERE id = ?",
                    (goal_id,)
                )
                conn.commit()
                return cur.rowcount > 0
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()

    @classmethod
    def push_task(cls, goal_id: str, task_description: str) -> str:
        """Pushes an execution task under a goal node."""
        task_id = str(uuid.uuid4())
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Verify goal exists
                goal = conn.execute("SELECT id FROM hm_working_memory_goals WHERE id = ?", (goal_id,)).fetchone()
                if not goal:
                    raise ValueError(f"Goal {goal_id} not found.")

                conn.execute(
                    """
                    INSERT INTO hm_working_memory_tasks (id, goal_id, task_description, status, created_at, updated_at)
                    VALUES (?, ?, ?, 'pending', ?, ?)
                    """,
                    (task_id, goal_id, task_description.strip(), now, now)
                )
                conn.commit()
                return task_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def update_task_status(cls, task_id: str, status: str) -> bool:
        """Updates task status."""
        allowed_statuses = {"pending", "running", "completed", "failed"}
        if status not in allowed_statuses:
            raise ValueError(f"Invalid task status: {status}. Must be one of {allowed_statuses}")
            
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cur = conn.execute(
                    "UPDATE hm_working_memory_tasks SET status = ?, updated_at = ? WHERE id = ?",
                    (status, now, task_id)
                )
                conn.commit()
                return cur.rowcount > 0
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()

    @classmethod
    def log_trace(cls, session_id: str, goal_id: Optional[str], task_id: Optional[str], trace_type: str, content: str) -> str:
        """Logs an execution reasoning trace, capturing currently active guardrail IDs for causal tracking."""
        trace_id = str(uuid.uuid4())
        now = time.time()
        
        # Dynamic lookup of active guardrails to prevent feedback loops
        active_guardrail_ids: list[str] = []
        try:
            from backend.core.reflection_memory import ReflectionMemory
            active_guardrails = ReflectionMemory.list_active_guardrails()
            active_guardrail_ids = [g["id"] for g in active_guardrails]
        except Exception:
            # Handle situations during initialization or testing where ReflectionMemory is unavailable
            pass
            
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Verify session
                session = conn.execute("SELECT id FROM hm_working_memory_sessions WHERE id = ?", (session_id,)).fetchone()
                if not session:
                    cls.initialize_session(session_id)
                    
                conn.execute(
                    """
                    INSERT INTO hm_working_memory_traces (
                        id, session_id, goal_id, task_id, trace_type, content, active_guardrails, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (trace_id, session_id, goal_id, task_id, trace_type, content.strip(), json.dumps(active_guardrail_ids), now)
                )
                conn.commit()
                return trace_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_active_workspace_context(cls, session_id: str) -> dict[str, Any]:
        """Assembles active short-term context context (goals, tasks, traces) for task planner prompt builders."""
        conn = cls._get_sqlite_conn()
        try:
            # Active Goals
            goals = conn.execute(
                "SELECT * FROM hm_working_memory_goals WHERE session_id = ? AND status = 'active' ORDER BY created_at ASC",
                (session_id,)
            ).fetchall()
            
            goal_list = [dict(g) for g in goals]
            goal_ids = [g["id"] for g in goal_list]
            
            # Tasks under active goals
            task_list = []
            if goal_ids:
                placeholders = ", ".join("?" for _ in goal_ids)
                tasks = conn.execute(
                    f"SELECT * FROM hm_working_memory_tasks WHERE goal_id IN ({placeholders}) ORDER BY created_at ASC",
                    goal_ids
                ).fetchall()
                task_list = [dict(t) for t in tasks]
                
            # Recent traces
            traces = conn.execute(
                "SELECT * FROM hm_working_memory_traces WHERE session_id = ? ORDER BY created_at DESC LIMIT 30",
                (session_id,)
            ).fetchall()
            trace_list = [dict(tr) for tr in reversed(traces)]
            for tr in trace_list:
                tr["active_guardrails"] = json.loads(tr["active_guardrails"])
                
            return {
                "session_id": session_id,
                "active_goals": goal_list,
                "tasks": task_list,
                "traces": trace_list
            }
        finally:
            conn.close()

    @classmethod
    def clear_session(cls, session_id: str) -> bool:
        """Cascading delete of a session and all its working memory details."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT id FROM hm_working_memory_sessions WHERE id = ?", (session_id,)).fetchone()
                if not row:
                    return False
                
                # Query goals to explicitly delete tasks first
                goal_rows = conn.execute("SELECT id FROM hm_working_memory_goals WHERE session_id = ?", (session_id,)).fetchall()
                goal_ids = [g["id"] for g in goal_rows]
                
                if goal_ids:
                    placeholders = ", ".join("?" for _ in goal_ids)
                    conn.execute(f"DELETE FROM hm_working_memory_tasks WHERE goal_id IN ({placeholders})", goal_ids)
                
                conn.execute("DELETE FROM hm_working_memory_traces WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM hm_working_memory_goals WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM hm_working_memory_sessions WHERE id = ?", (session_id,))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()
