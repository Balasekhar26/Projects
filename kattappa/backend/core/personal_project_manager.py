from __future__ import annotations

import json
import sqlite3
import time
import uuid
import math
from typing import Any, Dict, List, Optional

from backend.core.project_memory import ProjectMemory
from backend.core.goal_memory import GoalMemory
from backend.core.logger import log_event


class PersonalProjectManager:
    """Personal Project Manager (PPM) sitting on top of the Goal System."""

    _lock = ProjectMemory._lock

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        return ProjectMemory._get_sqlite_conn()

    @classmethod
    def create_project(
        cls,
        linked_goal_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: str = "PROPOSED",
        target_finish_date: Optional[float] = None,
        original_scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a PPM execution container linked to a single goal."""
        # 1. Zero Self-Creation: Ensure the linked goal exists in the Goal System
        goal = GoalMemory.get_goal(linked_goal_id)
        if not goal:
            raise ValueError(f"Originating goal '{linked_goal_id}' does not exist. Projects cannot self-create goals.")

        # Ensure goal is not completed or archived
        if goal["status"] in {"COMPLETED", "ARCHIVED", "CANCELLED", "ABANDONED"}:
            raise ValueError(f"Cannot link project to a completed/archived goal '{linked_goal_id}'.")

        p_id = f"ppm_proj_{uuid.uuid4().hex[:8]}"
        now = time.time()
        proj_title = title or f"Project: {goal['title']}"
        proj_desc = description or goal.get("description") or ""
        scope_text = original_scope or f"Fulfill goal: {goal['title']}"
        scope_id = f"scope_{uuid.uuid4().hex[:6]}"

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Rule 1: Goal coupling - unique linked_goal_id
                existing = conn.execute("SELECT project_id FROM projects WHERE linked_goal_id = ?", (linked_goal_id,)).fetchone()
                if existing:
                    raise ValueError(f"Goal '{linked_goal_id}' is already linked to project '{existing['project_id']}'.")

                # Insert into projects
                conn.execute(
                    """
                    INSERT INTO projects (
                        project_id, linked_goal_id, name, title, description, status, health_status,
                        calculated_priority, start_date, target_finish_date, expected_finish_date,
                        completion_percent, created_at, metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'GOOD', ?, ?, ?, ?, 0.0, ?, '{}')
                    """,
                    (
                        p_id, linked_goal_id, proj_title, proj_title, proj_desc, status.upper().strip(),
                        float(goal.get("priority_score", 0.0)), now, target_finish_date, target_finish_date, now
                    )
                )

                # Link project_id in goals table
                conn.execute("UPDATE goals SET project_id = ? WHERE goal_id = ?", (p_id, linked_goal_id))

                # Insert scope contract
                conn.execute(
                    "INSERT INTO project_scope (scope_id, project_id, original_scope, approved_scope) VALUES (?, ?, ?, ?)",
                    (scope_id, p_id, scope_text, scope_text)
                )

                # Log event
                ProjectMemory._log_event_conn(conn, p_id, "PROJECT_CREATED", {"title": proj_title, "linked_goal_id": linked_goal_id})
                
                # Initialize metrics
                conn.execute(
                    "INSERT INTO project_metrics (project_id, completion_probability, risk_score, forecast_delay_days, resource_burn_rate, rolling_momentum_score, health_score) VALUES (?, 1.0, 0.0, 0.0, 0.0, 0.0, 100.0)",
                    (p_id,)
                )

                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        return cls.get_project(p_id)

    @classmethod
    def get_project(cls, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves details of a project and syncs health/deadlines/metrics."""
        # Sync zombie state and calculate predictions/health before reading
        cls.sync_zombie_state(project_id)
        cls.recalculate_metrics_and_health(project_id)

        conn = cls._get_sqlite_conn()
        try:
            prow = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
            if not prow:
                return None

            p_dict = dict(prow)
            linked_goal_id = p_dict["linked_goal_id"]

            # Load milestones
            mrows = conn.execute("SELECT * FROM milestones WHERE project_id = ?", (project_id,)).fetchall()
            milestones = []
            for m in mrows:
                m_dict = dict(m)
                # Fetch tasks for this milestone
                trows = conn.execute("SELECT * FROM tasks WHERE milestone_id = ?", (m_dict["milestone_id"],)).fetchall()
                m_dict["tasks"] = [dict(t) for t in trows]
                milestones.append(m_dict)

            # Load dependencies
            drows = conn.execute("SELECT * FROM project_dependencies WHERE project_id = ?", (project_id,)).fetchall()
            dependencies = [dict(d) for d in drows]

            # Load resources
            res_rows = conn.execute("SELECT * FROM resources WHERE project_id = ?", (project_id,)).fetchall()
            resources = [dict(r) for r in res_rows]

            # Load blockers
            blocker_rows = conn.execute("SELECT * FROM project_blockers WHERE project_id = ?", (project_id,)).fetchall()
            blockers = [dict(b) for b in blocker_rows]

            # Load scope
            scope_row = conn.execute("SELECT * FROM project_scope WHERE project_id = ?", (project_id,)).fetchone()
            scope = dict(scope_row) if scope_row else None

            # Load metrics
            metric_row = conn.execute("SELECT * FROM project_metrics WHERE project_id = ?", (project_id,)).fetchone()
            metrics = dict(metric_row) if metric_row else None

            # Load memory logs
            memories = conn.execute("SELECT * FROM project_memory WHERE project_id = ? ORDER BY timestamp ASC", (project_id,)).fetchall()
            memory_list = [dict(m) for m in memories]

            # Load revisions
            revs = conn.execute("SELECT * FROM project_revisions WHERE project_id = ? ORDER BY timestamp ASC", (project_id,)).fetchall()
            revisions = [dict(r) for r in revs]

            return {
                "project_id": p_dict["project_id"],
                "linked_goal_id": linked_goal_id,
                "title": p_dict["title"] or p_dict["name"],
                "description": p_dict["description"],
                "status": p_dict["status"],
                "health_status": p_dict["health_status"],
                "calculated_priority": p_dict["calculated_priority"],
                "start_date": p_dict["start_date"],
                "target_finish_date": p_dict["target_finish_date"],
                "expected_finish_date": p_dict["expected_finish_date"],
                "completion_percent": p_dict["completion_percent"],
                "created_at": p_dict["created_at"],
                "metadata": json.loads(p_dict["metadata"] or "{}"),
                "milestones": milestones,
                "dependencies": dependencies,
                "resources": resources,
                "blockers": blockers,
                "scope": scope,
                "metrics": metrics,
                "memory": memory_list,
                "revisions": revisions
            }
        finally:
            conn.close()

    @classmethod
    def list_projects(cls) -> List[Dict[str, Any]]:
        """Lists all projects, dynamically evaluating health/metrics."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute("SELECT project_id FROM projects ORDER BY created_at ASC").fetchall()
            ids = [r["project_id"] for r in rows]
        finally:
            conn.close()

        projects = []
        for p_id in ids:
            p = cls.get_project(p_id)
            if p:
                projects.append(p)
        return projects

    @classmethod
    def update_project_status(cls, project_id: str, status: str, reason: str = "Status updated") -> Dict[str, Any]:
        """Updates the project status with read-only checks on archived/completed projects."""
        status_clean = status.upper().strip()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                prow = conn.execute("SELECT status FROM projects WHERE project_id = ?", (project_id,)).fetchone()
                if not prow:
                    raise KeyError(f"Project '{project_id}' not found.")

                # Rule 6: Archived/Completed projects are read-only historical memory
                if prow["status"] in {"ARCHIVED", "COMPLETED", "ABANDONED"}:
                    raise ValueError(f"Project is in terminal state '{prow['status']}' and cannot be modified.")

                conn.execute("UPDATE projects SET status = ? WHERE project_id = ?", (status_clean, project_id))
                ProjectMemory._log_event_conn(conn, project_id, "PROJECT_STATUS_CHANGED", {"status": status_clean, "reason": reason})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        return cls.get_project(project_id)

    @classmethod
    def create_milestone(
        cls,
        project_id: str,
        title: str,
        weight: float = 1.0,
        deadline: Optional[float] = None
    ) -> Dict[str, Any]:
        """Creates a milestone under a project and syncs it with the originating goal."""
        m_id = f"ppm_m_{uuid.uuid4().hex[:6]}"
        now = time.time()

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                prow = conn.execute("SELECT linked_goal_id, status FROM projects WHERE project_id = ?", (project_id,)).fetchone()
                if not prow:
                    raise KeyError(f"Project '{project_id}' not found.")

                if prow["status"] in {"ARCHIVED", "COMPLETED", "ABANDONED"}:
                    raise ValueError(f"Cannot add milestones to a read-only project in state '{prow['status']}'.")

                linked_goal_id = prow["linked_goal_id"]

                # Insert into milestones (satisfies both legacy goals and new projects references)
                conn.execute(
                    """
                    INSERT INTO milestones (milestone_id, goal_id, project_id, title, status, weight, progress, created_at, deadline)
                    VALUES (?, ?, ?, ?, 'PENDING', ?, 0.0, ?, ?)
                    """,
                    (m_id, linked_goal_id, project_id, title, float(weight), now, deadline)
                )

                ProjectMemory._log_event_conn(conn, project_id, "MILESTONE_ADDED", {"milestone_id": m_id, "title": title})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        return {"milestone_id": m_id, "project_id": project_id, "title": title, "status": "PENDING", "weight": weight, "deadline": deadline}

    @classmethod
    def create_task(
        cls,
        milestone_id: str,
        title: str,
        description: Optional[str] = None,
        assigned_agent: Optional[str] = None,
        effort_score: int = 1,
        deadline: Optional[float] = None
    ) -> Dict[str, Any]:
        """Creates a Task under a Milestone with resource/status validation."""
        t_id = f"ppm_t_{uuid.uuid4().hex[:6]}"
        now = time.time()

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                mrow = conn.execute("SELECT project_id FROM milestones WHERE milestone_id = ?", (milestone_id,)).fetchone()
                if not mrow:
                    raise KeyError(f"Milestone '{milestone_id}' not found.")

                p_id = mrow["project_id"]
                prow = conn.execute("SELECT status FROM projects WHERE project_id = ?", (p_id,)).fetchone()
                if prow and prow["status"] in {"ARCHIVED", "COMPLETED", "ABANDONED"}:
                    raise ValueError(f"Cannot add tasks to a read-only project in state '{prow['status']}'.")

                conn.execute(
                    """
                    INSERT INTO tasks (task_id, milestone_id, title, description, assigned_agent, status, progress, created_at, effort_score, deadline)
                    VALUES (?, ?, ?, ?, ?, 'QUEUED', 0.0, ?, ?, ?)
                    """,
                    (t_id, milestone_id, title, description, assigned_agent, now, int(effort_score), deadline)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        return {"task_id": t_id, "milestone_id": milestone_id, "title": title, "status": "QUEUED", "assigned_agent": assigned_agent, "effort_score": effort_score, "deadline": deadline}

    @classmethod
    def update_task_status(cls, task_id: str, status: str, progress: Optional[float] = None) -> Dict[str, Any]:
        """Updates task progress status using standard V2 delegation."""
        return ProjectMemory.update_task_status(task_id, status, progress)

    # -- Blocker & Dependency Engines -----------------------------------------

    @classmethod
    def add_blocker(cls, project_id: str, severity: str, source: str) -> Dict[str, Any]:
        """Raises a blocker on a project, triggering health recalculation."""
        b_id = f"block_{uuid.uuid4().hex[:6]}"
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    "INSERT INTO project_blockers (blocker_id, project_id, severity, source, status, timestamp) VALUES (?, ?, ?, ?, 'ACTIVE', ?)",
                    (b_id, project_id, severity.upper().strip(), source, now)
                )
                ProjectMemory._log_event_conn(conn, project_id, "BLOCKER_RAISED", {"blocker_id": b_id, "severity": severity, "source": source})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        return {"blocker_id": b_id, "project_id": project_id, "severity": severity, "source": source, "status": "ACTIVE"}

    @classmethod
    def resolve_blocker(cls, blocker_id: str) -> None:
        """Resolves a raised blocker, restoring project health calculation."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                brow = conn.execute("SELECT project_id, status FROM project_blockers WHERE blocker_id = ?", (blocker_id,)).fetchone()
                if not brow or brow["status"] == "RESOLVED":
                    return

                p_id = brow["project_id"]
                conn.execute("UPDATE project_blockers SET status = 'RESOLVED' WHERE blocker_id = ?", (blocker_id,))
                ProjectMemory._log_event_conn(conn, p_id, "BLOCKER_RESOLVED", {"blocker_id": blocker_id})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def add_project_dependency(cls, project_id: str, depends_on_project_id: str, dependency_type: str = "HARD") -> None:
        """Registers a project dependency check, preventing cycles."""
        dep_id = f"dep_{uuid.uuid4().hex[:6]}"
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Validate existences
                p = conn.execute("SELECT status FROM projects WHERE project_id = ?", (project_id,)).fetchone()
                d = conn.execute("SELECT status FROM projects WHERE project_id = ?", (depends_on_project_id,)).fetchone()
                if not p or not d:
                    raise ValueError("Both projects must exist to establish dependency.")

                conn.execute(
                    "INSERT INTO project_dependencies (dependency_id, project_id, depends_on_project_id, dependency_type) VALUES (?, ?, ?, ?)",
                    (dep_id, project_id, depends_on_project_id, dependency_type.upper().strip())
                )

                if ProjectMemory._has_dependency_cycle(conn):
                    conn.execute("DELETE FROM project_dependencies WHERE dependency_id = ?", (dep_id,))
                    raise ValueError("Project dependency cycle detected!")

                ProjectMemory._log_event_conn(conn, project_id, "PROJECT_DEPENDENCY_ADDED", {"depends_on": depends_on_project_id, "type": dependency_type})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    # -- Resource Engine ------------------------------------------------------

    @classmethod
    def allocate_resource(cls, project_id: str, resource_type: str, allocated: float) -> Dict[str, Any]:
        """Allocates resources to a project container."""
        r_type = resource_type.upper().strip()
        r_id = f"res_{uuid.uuid4().hex[:6]}"

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Check if this resource type already exists
                existing = conn.execute("SELECT resource_id, allocated_amount, consumed_amount FROM resources WHERE project_id = ? AND resource_type = ?", (project_id, r_type)).fetchone()
                if existing:
                    new_allocated = float(allocated)
                    new_remaining = new_allocated - existing["consumed_amount"]
                    conn.execute(
                        "UPDATE resources SET allocated_amount = ?, remaining_amount = ? WHERE resource_id = ?",
                        (new_allocated, new_remaining, existing["resource_id"])
                    )
                    r_id = existing["resource_id"]
                else:
                    conn.execute(
                        "INSERT INTO resources (resource_id, project_id, resource_type, allocated_amount, consumed_amount, remaining_amount) VALUES (?, ?, ?, ?, 0.0, ?)",
                        (r_id, project_id, r_type, float(allocated), float(allocated))
                    )
                ProjectMemory._log_event_conn(conn, project_id, "RESOURCE_ALLOCATED", {"resource_type": r_type, "allocated": float(allocated)})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        return {"resource_id": r_id, "project_id": project_id, "resource_type": r_type, "allocated": float(allocated)}

    @classmethod
    def consume_resource(cls, project_id: str, resource_type: str, amount: float) -> Dict[str, Any]:
        """Consumes resources, throwing ValueError on resource exhaustion (P4 Resource Hallucination)."""
        r_type = resource_type.upper().strip()
        amt = float(amount)

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                res = conn.execute("SELECT * FROM resources WHERE project_id = ? AND resource_type = ?", (project_id, r_type)).fetchone()
                if not res:
                    # Allocate auto with default 0 if not pre-allocated
                    r_id = f"res_{uuid.uuid4().hex[:6]}"
                    conn.execute(
                        "INSERT INTO resources (resource_id, project_id, resource_type, allocated_amount, consumed_amount, remaining_amount) VALUES (?, ?, ?, 0.0, ?, ?)",
                        (r_id, project_id, r_type, amt, -amt)
                    )
                    res = conn.execute("SELECT * FROM resources WHERE resource_id = ?", (r_id,)).fetchone()

                new_consumed = res["consumed_amount"] + amt
                new_remaining = res["allocated_amount"] - new_consumed

                # P4 Resource Hallucination check: resource exhaustion validation
                if new_remaining < 0.0:
                    raise ValueError(f"Resource exhaustion: Consumption of {amt} units of {r_type} exceeds remaining allocated limit.")

                conn.execute(
                    "UPDATE resources SET consumed_amount = ?, remaining_amount = ? WHERE resource_id = ?",
                    (new_consumed, new_remaining, res["resource_id"])
                )
                ProjectMemory._log_event_conn(conn, project_id, "RESOURCE_CONSUMED", {"resource_type": r_type, "consumed": amt})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        return {"resource_type": r_type, "consumed_amount": new_consumed, "remaining_amount": new_remaining}

    # -- Memory logs (Immutable decisions/failures/lessons) -------------------

    @classmethod
    def log_decision(cls, project_id: str, title: str, rationale: str) -> None:
        """Appends a project architecture/configuration decision."""
        cls._log_memory(project_id, "DECISION", f"Title: {title}\nRationale: {rationale}")

    @classmethod
    def log_failure(cls, project_id: str, component: str, details: str) -> None:
        """Appends a project failure trace memory."""
        cls._log_memory(project_id, "FAILURE_LESSON", f"Component: {component}\nFailure trace: {details}")

    @classmethod
    def log_lesson(cls, project_id: str, lesson: str) -> None:
        """Appends a lesson learned from execution."""
        cls._log_memory(project_id, "FAILURE_LESSON", f"Lesson learned: {lesson}")

    @classmethod
    def _log_memory(cls, project_id: str, memory_type: str, content: str) -> None:
        m_id = f"mem_{uuid.uuid4().hex[:6]}"
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    "INSERT INTO project_memory (memory_id, project_id, memory_type, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (m_id, project_id, memory_type.upper().strip(), content, now)
                )
                ProjectMemory._log_event_conn(conn, project_id, f"MEMORY_{memory_type}", {"memory_id": m_id})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    # -- Deadline & Health Engine ----------------------------------------------

    @classmethod
    def calculate_health_and_deadline(cls, project_id: str) -> Dict[str, Any]:
        """Calculates project health score and estimates finish dates based on momentum/blockers."""
        conn = cls._get_sqlite_conn()
        try:
            prow = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
            if not prow:
                return {"health": "CRITICAL", "health_score": 0.0}

            now = time.time()
            expected_finish = prow["expected_finish_date"] or now
            target_finish = prow["target_finish_date"] or now
            delay_days = max(0.0, expected_finish - target_finish) / 86400.0

            # Dynamic momentum calculation
            seven_days_ago = now - (7 * 86400)
            completed_tasks = conn.execute(
                "SELECT COUNT(*) as cnt FROM tasks t JOIN milestones m ON t.milestone_id = m.milestone_id WHERE m.project_id = ? AND t.status = 'COMPLETED' AND t.completed_at >= ?",
                (project_id, seven_days_ago)
            ).fetchone()["cnt"]

            if prow["status"] == "STUCK":
                return {
                    "health_status": "CRITICAL",
                    "health_score": 0.0,
                    "forecast_delay_days": delay_days,
                    "completion_probability": 0.0,
                    "momentum": completed_tasks
                }

            # Deductive Health Model
            h_score = 100.0

            # 1. Blocker Penalties
            blockers = conn.execute("SELECT severity FROM project_blockers WHERE project_id = ? AND status = 'ACTIVE'", (project_id,)).fetchall()
            for b in blockers:
                sev = b["severity"]
                if sev == "BLOCKING":
                    h_score -= 70.0
                elif sev == "HIGH":
                    h_score -= 30.0
                elif sev == "MEDIUM":
                    h_score -= 15.0
                else:
                    h_score -= 5.0

            # 2. Resource Availability Penalties
            res_rows = conn.execute("SELECT allocated_amount, consumed_amount, remaining_amount FROM resources WHERE project_id = ?", (project_id,)).fetchall()
            for r in res_rows:
                if r["remaining_amount"] < 0.0:
                    h_score -= 50.0
                elif r["allocated_amount"] > 0:
                    ratio = r["consumed_amount"] / r["allocated_amount"]
                    if ratio > 0.8:
                        h_score -= 15.0

            # 3. Delay Prediction Penalties
            h_score -= min(40.0, delay_days * 5.0)

            # 4. Dependency Penalties
            deps = conn.execute("SELECT depends_on_project_id FROM project_dependencies WHERE project_id = ?", (project_id,)).fetchall()
            for d in deps:
                d_health = conn.execute("SELECT health_status FROM projects WHERE project_id = ?", (d["depends_on_project_id"],)).fetchone()
                if d_health:
                    if d_health["health_status"] == "CRITICAL":
                        h_score -= 20.0
                    elif d_health["health_status"] == "WARNING":
                        h_score -= 10.0

            # 5. Momentum Penalty (only if project is ACTIVE and has tasks, but 0 completed in last 7 days)
            t_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM tasks t JOIN milestones m ON t.milestone_id = m.milestone_id WHERE m.project_id = ?",
                (project_id,)
            ).fetchone()["cnt"]
            if prow["status"] == "ACTIVE" and t_count > 0 and completed_tasks == 0:
                h_score -= 10.0

            h_score = max(0.0, min(100.0, h_score))

            health_status = "EXCELLENT"
            if h_score < 40.0:
                health_status = "CRITICAL"
            elif h_score < 70.0:
                health_status = "WARNING"
            elif h_score < 90.0:
                health_status = "GOOD"

            return {
                "health_status": health_status,
                "health_score": h_score,
                "forecast_delay_days": delay_days,
                "completion_probability": max(0.0, min(1.0, 1.0 - (delay_days / 10.0) if delay_days > 0 else 1.0)),
                "momentum": completed_tasks
            }
        finally:
            conn.close()

    @classmethod
    def recalculate_metrics_and_health(cls, project_id: str) -> None:
        """Triggers updates on project_metrics and updates projects tables."""
        # 1. Update completion percent (inherited from linked goal progress)
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                prow = conn.execute("SELECT linked_goal_id FROM projects WHERE project_id = ?", (project_id,)).fetchone()
                if prow:
                    goal = conn.execute("SELECT progress FROM goals WHERE goal_id = ?", (prow["linked_goal_id"],)).fetchone()
                    if goal:
                        # Sync progress directly
                        conn.execute("UPDATE projects SET completion_percent = ? WHERE project_id = ?", (goal["progress"], project_id))
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

        # 2. Run Health & Delay Prediction
        health_info = cls.calculate_health_and_deadline(project_id)
        now = time.time()

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Update expected_finish_date to reflect delay
                delay_sec = health_info["forecast_delay_days"] * 86400.0
                prow = conn.execute("SELECT target_finish_date FROM projects WHERE project_id = ?", (project_id,)).fetchone()
                target = prow["target_finish_date"] if prow and prow["target_finish_date"] else now
                expected = target + delay_sec

                conn.execute(
                    "UPDATE projects SET health_status = ?, expected_finish_date = ? WHERE project_id = ?",
                    (health_info["health_status"], expected, project_id)
                )

                # Update metrics
                conn.execute(
                    """
                    UPDATE project_metrics
                    SET completion_probability = ?, risk_score = ?, forecast_delay_days = ?, health_score = ?, rolling_momentum_score = ?
                    WHERE project_id = ?
                    """,
                    (
                        health_info["completion_probability"],
                        float(100.0 - health_info["health_score"]),
                        health_info["forecast_delay_days"],
                        health_info["health_score"],
                        float(health_info["momentum"]),
                        project_id
                    )
                )
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

    # -- Safety Rules checks & constraints ------------------------------------

    @classmethod
    def sync_zombie_state(cls, project_id: str) -> None:
        """P1 Zombie Project: if goal transitions to DORMANT/ARCHIVED, project follows state."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                prow = conn.execute("SELECT linked_goal_id, status FROM projects WHERE project_id = ?", (project_id,)).fetchone()
                if prow:
                    grow = conn.execute("SELECT current_state FROM goals WHERE goal_id = ?", (prow["linked_goal_id"],)).fetchone()
                    if grow:
                        g_state = grow["current_state"]
                        p_state = prow["status"]
                        # Sync dormant or archived state
                        if g_state in {"DORMANT", "ARCHIVED", "ABANDONED"} and p_state != g_state:
                            conn.execute("UPDATE projects SET status = ? WHERE project_id = ?", (g_state, project_id))
                            ProjectMemory._log_event_conn(conn, project_id, "STATE_SYNC_ZOMBIE", {"status": g_state})
                            conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

    @classmethod
    def check_max_replans(cls, project_id: str, max_limit: int = 3) -> None:
        """P3 Endless Replanning: transitions project to STUCK if revisions exceed limit."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cnt = conn.execute("SELECT COUNT(*) as count FROM project_revisions WHERE project_id = ?", (project_id,)).fetchone()["count"]
                if cnt >= max_limit:
                    conn.execute("UPDATE projects SET status = 'STUCK', health_status = 'CRITICAL' WHERE project_id = ?", (project_id,))
                    ProjectMemory._log_event_conn(conn, project_id, "PROJECT_STUCK_REPLANNING", {"revisions": cnt})
                    conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

    @classmethod
    def log_revision(cls, project_id: str, author: str, summary: str) -> None:
        """Logs a scope replanning revision, checking replan limits."""
        rev_id = f"rev_{uuid.uuid4().hex[:6]}"
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Update approved scope to match latest approved revision
                conn.execute(
                    "UPDATE project_scope SET approved_scope = ? WHERE project_id = ?",
                    (summary, project_id)
                )
                conn.execute(
                    "INSERT INTO project_revisions (revision_id, project_id, change_summary, author, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (rev_id, project_id, summary, author, now)
                )
                ProjectMemory._log_event_conn(conn, project_id, "PROJECT_REPLAN_LOGGED", {"author": author})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        # Check max replan bounds
        cls.check_max_replans(project_id)

    @classmethod
    def complete_project(cls, project_id: str, validator: Optional[str] = None, user_confirmed: bool = False) -> Dict[str, Any]:
        """Rule 5: Completion requires independent verification, blocking executor self-grading."""
        conn = cls._get_sqlite_conn()
        try:
            prow = conn.execute("SELECT linked_goal_id FROM projects WHERE project_id = ?", (project_id,)).fetchone()
            if not prow:
                raise KeyError(f"Project '{project_id}' not found.")
            linked_goal_id = prow["linked_goal_id"]
        finally:
            conn.close()

        # Verify completion requires independent verification
        if not validator and not user_confirmed:
            raise ValueError("Project completion validation failed: Projects require an independent validator or user confirmation.")

        # Log completion verification event and propagate to goal system inside same transaction
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                event_payload = {
                    "validator": validator or "User Confirmation",
                    "user_confirmed": user_confirmed
                }
                ProjectMemory._log_event_conn(conn, project_id, "PROJECT_VERIFIED", event_payload)
                
                # Update project to COMPLETED
                conn.execute("UPDATE projects SET status = 'COMPLETED', actual_finish = ? WHERE project_id = ?", (time.time(), project_id))
                
                # Propagate complete to the linked goal system directly in the same SQLite connection
                conn.execute(
                    "UPDATE goals SET status = 'COMPLETED', current_state = 'COMPLETED', state_reason = ?, last_reviewed_at = ? WHERE goal_id = ?",
                    (f"Completed via project container {project_id} validation.", time.time(), linked_goal_id)
                )
                GoalMemory._log_event_conn(conn, linked_goal_id, "GOAL_COMPLETED", {"reason": f"Completed via project container {project_id} validation."})
                GoalMemory._log_progress_conn(conn, linked_goal_id, 1.0, "Completed", time.time())
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        return cls.get_project(project_id)

    # -- Reflection Engine ----------------------------------------------------

    @classmethod
    def reflect_on_project(cls, project_id: str) -> Dict[str, Any]:
        """PPM Reflection Engine: extracts patterns, recurrent blockers, estimates slippages."""
        conn = cls._get_sqlite_conn()
        try:
            # Gather all historical blockers
            blockers = conn.execute("SELECT severity, source, status FROM project_blockers WHERE project_id = ?", (project_id,)).fetchall()
            total_blockers = len(blockers)
            active_blockers = sum(1 for b in blockers if b["status"] == "ACTIVE")

            # Gather failure memory logs
            failures = conn.execute("SELECT content FROM project_memory WHERE project_id = ? AND memory_type = 'FAILURE_LESSON'", (project_id,)).fetchall()
            failure_count = len(failures)

            # Analyze scope creep (number of revisions)
            revisions = conn.execute("SELECT COUNT(*) as cnt FROM project_revisions WHERE project_id = ?", (project_id,)).fetchone()["cnt"]

            insights = []
            if total_blockers > 2:
                insights.append(f"Project slippage warning: recurrent blockers detected ({total_blockers} raised). Recommended: Mitigate knowledge dependency before next milestone.")
            if failure_count > 0:
                insights.append(f"Friction pattern: {failure_count} failure rollbacks logged. Recommended: Review configuration validations.")
            if revisions > 2:
                insights.append("Scope creep detected: replanned multiple times. Recommended: Enforce rigid scope bounds.")

            if not insights:
                insights.append("Project execution is within nominal stability bounds. Momentum is high.")

            report = {
                "timestamp": time.time(),
                "total_blockers": total_blockers,
                "active_blockers": active_blockers,
                "revisions": revisions,
                "insights": insights
            }

            # Append reflection to immutable memory
            cls._log_memory(project_id, "USER_CONVERSATION", f"Project Reflection Report:\n" + "\n".join(insights))

            return report
        finally:
            conn.close()
