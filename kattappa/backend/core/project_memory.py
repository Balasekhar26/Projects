from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event


class ProjectMemory:
    """Structured and transactional database backend for Step 8.2 Project V2."""

    _lock = threading.RLock()
    _schema_ensured = False

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = config.sqlite_path.parent / "goal_memory.db"
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        with cls._lock:
            if not cls._schema_ensured:
                cls._ensure_schema(conn)
                cls._schema_ensured = True
            else:
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'")
                if not cursor.fetchone():
                    cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            # Ensure GoalMemory schema is created first to satisfy foreign keys
            from backend.core.goal_memory import GoalMemory
            GoalMemory._ensure_schema(conn)

            # Create project-related tables
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'PROPOSED',
                    completion_percent REAL NOT NULL DEFAULT 0.0,
                    success_rate REAL NOT NULL DEFAULT 1.0,
                    risk_score REAL NOT NULL DEFAULT 0.0,
                    resource_cost REAL NOT NULL DEFAULT 0.0,
                    predicted_finish REAL,
                    actual_finish REAL,
                    created_at REAL NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    milestone_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    assigned_agent TEXT,
                    status TEXT NOT NULL DEFAULT 'PROPOSED',
                    progress REAL NOT NULL DEFAULT 0.0,
                    created_at REAL NOT NULL,
                    completed_at REAL,
                    FOREIGN KEY (milestone_id) REFERENCES milestones(milestone_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS actions (
                    action_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PROPOSED',
                    payload TEXT NOT NULL DEFAULT '{}',
                    result TEXT,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS project_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS project_decisions (
                    decision_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    rationale TEXT,
                    status TEXT NOT NULL DEFAULT 'APPROVED',
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS project_failures (
                    failure_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    component TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    resolved INTEGER NOT NULL DEFAULT 0,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS project_rollbacks (
                    rollback_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    milestone_id TEXT,
                    action_id TEXT,
                    reason TEXT,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS project_dependencies (
                    project_id TEXT NOT NULL,
                    depends_on_project_id TEXT NOT NULL,
                    PRIMARY KEY (project_id, depends_on_project_id),
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
                    FOREIGN KEY (depends_on_project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS resources (
                    resource_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    allocated_amount REAL NOT NULL DEFAULT 0.0,
                    consumed_amount REAL NOT NULL DEFAULT 0.0,
                    remaining_amount REAL NOT NULL DEFAULT 0.0,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS project_memory (
                    memory_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS project_metrics (
                    project_id TEXT PRIMARY KEY,
                    completion_probability REAL NOT NULL DEFAULT 1.0,
                    risk_score REAL NOT NULL DEFAULT 0.0,
                    forecast_delay_days REAL NOT NULL DEFAULT 0.0,
                    resource_burn_rate REAL NOT NULL DEFAULT 0.0,
                    rolling_momentum_score REAL NOT NULL DEFAULT 0.0,
                    health_score REAL NOT NULL DEFAULT 100.0,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS project_scope (
                    scope_id TEXT PRIMARY KEY,
                    project_id TEXT UNIQUE NOT NULL,
                    original_scope TEXT NOT NULL,
                    approved_scope TEXT NOT NULL,
                    blast_radius TEXT,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS project_revisions (
                    revision_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    change_summary TEXT NOT NULL,
                    author TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS project_blockers (
                    blocker_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'MEDIUM',
                    source TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_milestone ON tasks(milestone_id);
                CREATE INDEX IF NOT EXISTS idx_actions_task ON actions(task_id);
                CREATE INDEX IF NOT EXISTS idx_project_events ON project_events(project_id);
                CREATE INDEX IF NOT EXISTS idx_project_decisions ON project_decisions(project_id);
                CREATE INDEX IF NOT EXISTS idx_project_failures ON project_failures(project_id);
                CREATE INDEX IF NOT EXISTS idx_project_rollbacks ON project_rollbacks(project_id);
                """
            )
            conn.commit()

            # Alter goals table to reference projects
            try:
                conn.execute(
                    "ALTER TABLE goals ADD COLUMN project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL"
                )
                conn.commit()
            except sqlite3.OperationalError:
                # Column already exists
                pass

            # Apply ALTER TABLE updates for PPM support
            for table, col, dtype, dflt in [
                ("projects", "linked_goal_id", "TEXT REFERENCES goals(goal_id) ON DELETE SET NULL", "NULL"),
                ("projects", "title", "TEXT", "NULL"),
                ("projects", "health_status", "TEXT", "'GOOD'"),
                ("projects", "calculated_priority", "REAL", "0.0"),
                ("projects", "start_date", "REAL", "NULL"),
                ("projects", "target_finish_date", "REAL", "NULL"),
                ("projects", "expected_finish_date", "REAL", "NULL"),
                ("milestones", "project_id", "TEXT REFERENCES projects(project_id) ON DELETE CASCADE", "NULL"),
                ("milestones", "deadline", "REAL", "NULL"),
                ("tasks", "effort_score", "INTEGER", "0"),
                ("tasks", "deadline", "REAL", "NULL"),
                ("actions", "tool_used", "TEXT", "NULL"),
                ("actions", "result_summary", "TEXT", "NULL"),
                ("actions", "is_successful", "INTEGER", "1"),
                ("project_dependencies", "dependency_id", "TEXT", "NULL"),
                ("project_dependencies", "dependency_type", "TEXT", "'HARD'"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dtype} DEFAULT {dflt}")
                    conn.commit()
                except sqlite3.OperationalError:
                    pass

    @classmethod
    def create_project(
        cls,
        name: str,
        description: Optional[str] = None,
        status: str = "PROPOSED",
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Creates a project and registers the creation event."""
        p_id = project_id or f"proj_{uuid.uuid4().hex[:8]}"
        now = time.time()
        meta_json = json.dumps(metadata or {})
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO projects (project_id, name, description, status, completion_percent, success_rate, risk_score, created_at, metadata)
                    VALUES (?, ?, ?, ?, 0.0, 1.0, 0.0, ?, ?)
                    """,
                    (p_id, name, description, status.upper().strip(), now, meta_json)
                )
                cls._log_event_conn(conn, p_id, "PROJECT_CREATED", {"name": name, "status": status, "created_at": now})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        return cls.get_project(p_id)

    @classmethod
    def get_project(cls, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves details of a project, including goals, event ledgers, and dependency graph links."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Recalculate metrics dynamically on read to ensure freshness
                cls._recalculate_project_metrics_conn(conn, project_id)
                conn.commit()

                prow = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
                if not prow:
                    return None

                # Get goals linked to this project
                grow = conn.execute("SELECT goal_id, title, status, progress, priority_score FROM goals WHERE project_id = ?", (project_id,)).fetchall()
                goals = []
                for g in grow:
                    goals.append({
                        "goal_id": g["goal_id"],
                        "title": g["title"],
                        "status": g["status"],
                        "progress": g["progress"],
                        "priority_score": g["priority_score"]
                    })

                # Get dependencies
                drow = conn.execute("SELECT depends_on_project_id FROM project_dependencies WHERE project_id = ?", (project_id,)).fetchall()
                dependencies = [d["depends_on_project_id"] for d in drow]

                # Get logs
                events = conn.execute("SELECT * FROM project_events WHERE project_id = ? ORDER BY timestamp ASC", (project_id,)).fetchall()
                decisions = conn.execute("SELECT * FROM project_decisions WHERE project_id = ? ORDER BY timestamp ASC", (project_id,)).fetchall()
                failures = conn.execute("SELECT * FROM project_failures WHERE project_id = ? ORDER BY timestamp ASC", (project_id,)).fetchall()
                rollbacks = conn.execute("SELECT * FROM project_rollbacks WHERE project_id = ? ORDER BY timestamp ASC", (project_id,)).fetchall()

                return {
                    "project_id": prow["project_id"],
                    "name": prow["name"],
                    "description": prow["description"],
                    "status": prow["status"],
                    "completion_percent": prow["completion_percent"],
                    "success_rate": prow["success_rate"],
                    "risk_score": prow["risk_score"],
                    "resource_cost": prow["resource_cost"],
                    "predicted_finish": prow["predicted_finish"],
                    "actual_finish": prow["actual_finish"],
                    "created_at": prow["created_at"],
                    "metadata": json.loads(prow["metadata"]),
                    "goals": goals,
                    "dependencies": dependencies,
                    "events": [
                        {"event_type": e["event_type"], "payload": json.loads(e["payload"]), "timestamp": e["timestamp"]}
                        for e in events
                    ],
                    "decisions": [
                        {"decision_id": d["decision_id"], "title": d["title"], "description": d["description"], "rationale": d["rationale"], "status": d["status"], "timestamp": d["timestamp"]}
                        for d in decisions
                    ],
                    "failures": [
                        {"failure_id": f["failure_id"], "component": f["component"], "error_message": f["error_message"], "resolved": bool(f["resolved"]), "timestamp": f["timestamp"]}
                        for f in failures
                    ],
                    "rollbacks": [
                        {"rollback_id": r["rollback_id"], "milestone_id": r["milestone_id"], "action_id": r["action_id"], "reason": r["reason"], "timestamp": r["timestamp"]}
                        for r in rollbacks
                    ]
                }
            finally:
                conn.close()

    @classmethod
    def list_projects(cls) -> List[Dict[str, Any]]:
        """Lists all projects in the system."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute("SELECT project_id FROM projects ORDER BY created_at ASC").fetchall()
            projects = []
            for r in rows:
                p = cls.get_project(r["project_id"])
                if p:
                    projects.append(p)
            return projects
        finally:
            conn.close()

    @classmethod
    def update_project_status(cls, project_id: str, status: str) -> Dict[str, Any]:
        """Updates the status and logs changes."""
        status_clean = status.upper().strip()
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute("UPDATE projects SET status = ? WHERE project_id = ?", (status_clean, project_id))
                if status_clean == "COMPLETED":
                    conn.execute("UPDATE projects SET actual_finish = ? WHERE project_id = ?", (now, project_id))
                cls._log_event_conn(conn, project_id, "PROJECT_STATUS_CHANGED", {"status": status_clean})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        return cls.get_project(project_id)

    @classmethod
    def add_project_dependency(cls, project_id: str, depends_on_project_id: str) -> None:
        """Adds a project-level dependency relation with cycle validation."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                p = conn.execute("SELECT project_id FROM projects WHERE project_id = ?", (project_id,)).fetchone()
                d = conn.execute("SELECT project_id FROM projects WHERE project_id = ?", (depends_on_project_id,)).fetchone()
                if not p or not d:
                    raise ValueError("Both projects must exist to map dependencies.")

                conn.execute(
                    "INSERT OR IGNORE INTO project_dependencies (project_id, depends_on_project_id) VALUES (?, ?)",
                    (project_id, depends_on_project_id)
                )

                if cls._has_dependency_cycle(conn):
                    conn.execute(
                        "DELETE FROM project_dependencies WHERE project_id = ? AND depends_on_project_id = ?",
                        (project_id, depends_on_project_id)
                    )
                    raise ValueError("Project dependency cycle detected!")

                cls._log_event_conn(conn, project_id, "PROJECT_DEPENDENCY_ADDED", {"depends_on": depends_on_project_id})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def associate_goal_to_project(cls, goal_id: str, project_id: str) -> None:
        """Associates an existing goal to a project and triggers project metrics recalculation."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                p = conn.execute("SELECT project_id FROM projects WHERE project_id = ?", (project_id,)).fetchone()
                g = conn.execute("SELECT goal_id FROM goals WHERE goal_id = ?", (goal_id,)).fetchone()
                if not p or not g:
                    raise ValueError("Both project and goal must exist.")

                conn.execute("UPDATE goals SET project_id = ? WHERE goal_id = ?", (project_id, goal_id))
                cls._log_event_conn(conn, project_id, "GOAL_ASSOCIATED", {"goal_id": goal_id})
                cls._recalculate_project_metrics_conn(conn, project_id)
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def log_project_decision(cls, project_id: str, title: str, description: Optional[str] = None, rationale: Optional[str] = None) -> None:
        """Logs an executive decision for a project."""
        d_id = f"dec_{uuid.uuid4().hex[:6]}"
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO project_decisions (decision_id, project_id, title, description, rationale, status, timestamp)
                    VALUES (?, ?, ?, ?, ?, 'APPROVED', ?)
                    """,
                    (d_id, project_id, title, description, rationale, now)
                )
                cls._log_event_conn(conn, project_id, "DECISION_LOGGED", {"decision_id": d_id, "title": title})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def log_project_failure(cls, project_id: str, component: str, error_message: str) -> None:
        """Logs a failure event on a project."""
        f_id = f"fail_{uuid.uuid4().hex[:6]}"
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO project_failures (failure_id, project_id, component, error_message, resolved, timestamp)
                    VALUES (?, ?, ?, ?, 0, ?)
                    """,
                    (f_id, project_id, component, error_message, now)
                )
                cls._log_event_conn(conn, project_id, "FAILURE_LOGGED", {"failure_id": f_id, "component": component, "error": error_message})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def log_project_rollback(cls, project_id: str, milestone_id: Optional[str], action_id: Optional[str], reason: str) -> None:
        """Logs a rollback execution on a project."""
        r_id = f"rb_{uuid.uuid4().hex[:6]}"
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO project_rollbacks (rollback_id, project_id, milestone_id, action_id, reason, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (r_id, project_id, milestone_id, action_id, reason, now)
                )
                cls._log_event_conn(conn, project_id, "ROLLBACK_LOGGED", {"rollback_id": r_id, "milestone_id": milestone_id, "action_id": action_id, "reason": reason})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def create_task(
        cls,
        task_id: str,
        milestone_id: str,
        title: str,
        description: Optional[str] = None,
        assigned_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a Task under a Milestone."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO tasks (task_id, milestone_id, title, description, assigned_agent, status, progress, created_at)
                    VALUES (?, ?, ?, ?, ?, 'PROPOSED', 0.0, ?)
                    """,
                    (task_id, milestone_id, title, description, assigned_agent, now)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        return cls.get_task(task_id)

    @classmethod
    def get_task(cls, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a task details."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                return None
            return {
                "task_id": row["task_id"],
                "milestone_id": row["milestone_id"],
                "title": row["title"],
                "description": row["description"],
                "assigned_agent": row["assigned_agent"],
                "status": row["status"],
                "progress": row["progress"],
                "created_at": row["created_at"],
                "completed_at": row["completed_at"],
            }
        finally:
            conn.close()

    @classmethod
    def update_task_status(cls, task_id: str, status: str, progress: Optional[float] = None) -> Dict[str, Any]:
        """Updates task status/progress and updates derived parent milestones/goals/projects."""
        status_clean = status.upper().strip()
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                updates = ["status = ?"]
                params = [status_clean]
                if progress is not None:
                    updates.append("progress = ?")
                    params.append(max(0.0, min(1.0, float(progress))))
                if status_clean == "COMPLETED":
                    updates.append("completed_at = ?")
                    params.append(now)
                    if progress is None:
                        updates.append("progress = ?")
                        params.append(1.0)

                params.append(task_id)
                conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?", tuple(params))

                # Find milestone & goal and project to trigger updates
                row = conn.execute("SELECT milestone_id FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
                if row:
                    m_id = row["milestone_id"]
                    mrow = conn.execute("SELECT goal_id FROM milestones WHERE milestone_id = ?", (m_id,)).fetchone()
                    if mrow:
                        g_id = mrow["goal_id"]
                        # Auto-update milestone progress by averaging task progress
                        t_rows = conn.execute("SELECT progress FROM tasks WHERE milestone_id = ?", (m_id,)).fetchall()
                        if t_rows:
                            avg_progress = sum(r["progress"] for r in t_rows) / len(t_rows)
                            conn.execute("UPDATE milestones SET progress = ? WHERE milestone_id = ?", (avg_progress, m_id))

                            # Run goal and project progress recalculations
                            from backend.core.goal_memory import GoalMemory
                            GoalMemory._recalculate_progress_conn(conn, g_id, f"Task {task_id} status updated to {status_clean}", now)
                            GoalMemory._recalculate_priority_score_conn(conn, g_id)

                            # Recalculate project metrics if linked
                            grow = conn.execute("SELECT project_id FROM goals WHERE goal_id = ?", (g_id,)).fetchone()
                            if grow and grow["project_id"]:
                                cls._recalculate_project_metrics_conn(conn, grow["project_id"])

                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        return cls.get_task(task_id)

    @classmethod
    def create_action(
        cls,
        action_id: str,
        task_id: str,
        action_type: str,
        payload: Optional[Dict[str, Any]] = None,
        status: str = "PROPOSED",
        result: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Logs an action under a task."""
        now = time.time()
        p_json = json.dumps(payload or {})
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO actions (action_id, task_id, action_type, status, payload, result, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (action_id, task_id, action_type.upper().strip(), status.upper().strip(), p_json, result, now)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        return cls.get_action(action_id)

    @classmethod
    def get_action(cls, action_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves action details."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM actions WHERE action_id = ?", (action_id,)).fetchone()
            if not row:
                return None
            return {
                "action_id": row["action_id"],
                "task_id": row["task_id"],
                "action_type": row["action_type"],
                "status": row["status"],
                "payload": json.loads(row["payload"]),
                "result": row["result"],
                "timestamp": row["timestamp"],
            }
        finally:
            conn.close()

    # -- Internal helpers execution inside open SQLite transaction locks -----

    @staticmethod
    def _log_event_conn(conn: sqlite3.Connection, project_id: str, event_type: str, payload: dict) -> None:
        conn.execute(
            "INSERT INTO project_events (project_id, event_type, payload, timestamp) VALUES (?, ?, ?, ?)",
            (project_id, event_type, json.dumps(payload), time.time())
        )
        log_event("project_event", {"project_id": project_id, "event_type": event_type, **payload})

    @classmethod
    def _recalculate_project_metrics_conn(cls, conn: sqlite3.Connection, project_id: str) -> None:
        # Calculate completion percent (average of goals' progresses, 0.0 to 1.0 -> stored as percentage 0.0 to 100.0)
        grow = conn.execute("SELECT progress, goal_id FROM goals WHERE project_id = ?", (project_id,)).fetchall()
        if not grow:
            comp_val = 0.0
            succ_val = 1.0
            risk_val = 0.0
        else:
            comp_val = round(sum(float(g["progress"]) for g in grow) / len(grow), 4)

            # Get milestones for all linked goals to compute success rate & rollback risk
            g_ids = [g["goal_id"] for g in grow]
            placeholders = ", ".join("?" for _ in g_ids)
            mrow = conn.execute(
                f"SELECT success_probability, rollback_risk FROM milestones WHERE goal_id IN ({placeholders})",
                tuple(g_ids)
            ).fetchall()

            probs = [float(r["success_probability"]) for r in mrow if r["success_probability"] is not None]
            risks = [float(r["rollback_risk"]) for r in mrow if r["rollback_risk"] is not None]

            succ_val = round(sum(probs) / len(probs), 4) if probs else 1.0
            risk_val = round(sum(risks) / len(risks), 4) if risks else 0.0

        conn.execute(
            "UPDATE projects SET completion_percent = ?, success_rate = ?, risk_score = ? WHERE project_id = ?",
            (comp_val, succ_val, risk_val, project_id)
        )
        cls._log_event_conn(conn, project_id, "PROJECT_METRICS_RECALCULATED", {
            "completion_percent": comp_val,
            "success_rate": succ_val,
            "risk_score": risk_val
        })

    @staticmethod
    def _has_dependency_cycle(conn: sqlite3.Connection) -> bool:
        rows = conn.execute("SELECT project_id, depends_on_project_id FROM project_dependencies").fetchall()
        adj: dict[str, set[str]] = {}
        for r in rows:
            adj.setdefault(r["project_id"], set()).add(r["depends_on_project_id"])

        visited: set[str] = set()
        stack: set[str] = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            stack.add(node)
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in stack:
                    return True
            stack.remove(node)
            return False

        for node in adj:
            if node not in visited:
                if dfs(node):
                    return True
        return False

    @classmethod
    def reset(cls) -> None:
        """Reset databases. Helper for test isolation."""
        with cls._lock:
            cls._schema_ensured = False
            conn = cls._get_sqlite_conn()
            try:
                conn.execute("DELETE FROM projects")
                conn.execute("DELETE FROM project_dependencies")
                conn.execute("DELETE FROM tasks")
                conn.execute("DELETE FROM actions")
                conn.execute("DELETE FROM project_events")
                conn.execute("DELETE FROM project_decisions")
                conn.execute("DELETE FROM project_failures")
                conn.execute("DELETE FROM project_rollbacks")
                conn.execute("DELETE FROM resources")
                conn.execute("DELETE FROM project_memory")
                conn.execute("DELETE FROM project_metrics")
                conn.execute("DELETE FROM project_scope")
                conn.execute("DELETE FROM project_revisions")
                conn.execute("DELETE FROM project_blockers")
                conn.execute("UPDATE goals SET project_id = NULL")
                conn.commit()
            finally:
                conn.close()
