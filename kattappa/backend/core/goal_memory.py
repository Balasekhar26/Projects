from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
import math
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event


class GoalMemory:
    """Structured and append-only Goal database backend (Step 8.1 / Human-Like Goal System Step 8.3)."""

    _lock = threading.RLock()
    _schema_ensured = False

    ABSOLUTE_POLICIES = [
        {
            "policy_id": "ABS-POL-CORE-SHIELD",
            "title": "Unmodifiable Core Infrastructure",
            "description": "Block editing or overwriting the Goal System, Value Engine, Consensus Engine, or Policy Engine modules.",
            "forbidden_patterns": [r"backend/core/goal_memory\.py", r"backend/core/value_engine\.py", r"backend/core/validators\.py", r"backend/core/consensus_engine\.py"]
        },
        {
            "policy_id": "ABS-POL-ROOT-SHIELD",
            "title": "No Root Privilege Escalation",
            "description": "Do not execute sudo or root level command operations.",
            "forbidden_patterns": [r"\bsudo\b", r"\bchown\b", r"\bchmod\s+777\b"]
        }
    ]

    @classmethod
    def validate_against_absolute_policies(cls, title: str, description: Optional[str] = None) -> Optional[str]:
        """Checks if a goal violates any absolute safety policies.
        Returns the policy_id of the violated constraint, or None if safe.
        """
        import re
        text = f"{title} {description or ''}"
        for policy in cls.ABSOLUTE_POLICIES:
            for pattern in policy["forbidden_patterns"]:
                if re.search(pattern, text, re.IGNORECASE):
                    return policy["policy_id"]
        return None

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = config.sqlite_path.parent / "goal_memory.db"
        conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        with cls._lock:
            if not cls._schema_ensured:
                cls._ensure_schema(conn)
                cls._schema_ensured = True
            else:
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='goals'")
                if not cursor.fetchone():
                    cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS goals (
                    goal_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    priority TEXT NOT NULL DEFAULT 'MEDIUM',
                    status TEXT NOT NULL DEFAULT 'PROPOSED',
                    created_at REAL NOT NULL,
                    target_date TEXT,
                    progress REAL NOT NULL DEFAULT 0.0,
                    success_criteria TEXT NOT NULL DEFAULT '[]',
                    owner TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    importance REAL NOT NULL DEFAULT 5.0,
                    urgency REAL NOT NULL DEFAULT 5.0,
                    strategic_alignment REAL NOT NULL DEFAULT 5.0,
                    resource_cost REAL NOT NULL DEFAULT 2.0,
                    priority_score REAL NOT NULL DEFAULT 1.0
                );

                CREATE TABLE IF NOT EXISTS milestones (
                    milestone_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'PROPOSED',
                    weight REAL NOT NULL DEFAULT 1.0,
                    progress REAL NOT NULL DEFAULT 0.0,
                    created_at REAL NOT NULL,
                    completed_at REAL,
                    expected_duration_sec REAL,
                    success_probability REAL,
                    rollback_risk REAL,
                    FOREIGN KEY (goal_id) REFERENCES goals(goal_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS goal_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS goal_progress (
                    progress_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id TEXT NOT NULL,
                    progress REAL NOT NULL,
                    reason TEXT,
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS goal_dependencies (
                    goal_id TEXT NOT NULL,
                    depends_on_goal_id TEXT NOT NULL,
                    PRIMARY KEY (goal_id, depends_on_goal_id),
                    FOREIGN KEY (goal_id) REFERENCES goals(goal_id) ON DELETE CASCADE,
                    FOREIGN KEY (depends_on_goal_id) REFERENCES goals(goal_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS goal_values (
                    value_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    core_policy_constraint TEXT NOT NULL,
                    alignment_status TEXT NOT NULL DEFAULT 'PASSED',
                    FOREIGN KEY (goal_id) REFERENCES goals(goal_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS goal_conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    goal_a_id TEXT NOT NULL,
                    goal_b_id TEXT NOT NULL,
                    conflict_topology TEXT NOT NULL,
                    severity_rating REAL NOT NULL DEFAULT 50.0,
                    resolution_status TEXT NOT NULL DEFAULT 'UNRESOLVED',
                    FOREIGN KEY (goal_a_id) REFERENCES goals(goal_id) ON DELETE CASCADE,
                    FOREIGN KEY (goal_b_id) REFERENCES goals(goal_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS goal_metrics (
                    goal_id TEXT PRIMARY KEY,
                    historical_success_rate REAL NOT NULL DEFAULT 1.0,
                    average_execution_duration REAL NOT NULL DEFAULT 0.0,
                    rollback_frequency REAL NOT NULL DEFAULT 0.0,
                    simulation_prediction_accuracy REAL NOT NULL DEFAULT 1.0,
                    actual_token_resource_cost INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (goal_id) REFERENCES goals(goal_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_milestones_goal ON milestones(goal_id);
                CREATE INDEX IF NOT EXISTS idx_goal_events ON goal_events(goal_id);
                CREATE INDEX IF NOT EXISTS idx_goal_progress ON goal_progress(goal_id);
                """
            )
            conn.commit()

            # Apply ALTER TABLE updates for priority columns if they do not exist
            for col, dtype, dflt in [
                ("importance", "REAL", "5.0"),
                ("urgency", "REAL", "5.0"),
                ("strategic_alignment", "REAL", "5.0"),
                ("resource_cost", "REAL", "2.0"),
                ("priority_score", "REAL", "1.0"),
                # Human-Like additions:
                ("parent_goal_id", "TEXT", "NULL"),
                ("owner_agent", "TEXT", "NULL"),
                ("horizon_type", "TEXT", "'SHORT_TERM'"),
                ("current_state", "TEXT", "'IDEA'"),
                ("state_reason", "TEXT", "NULL"),
                ("importance_score", "REAL", "50.0"),
                ("urgency_score", "REAL", "50.0"),
                ("estimated_value", "REAL", "50.0"),
                ("confidence_score", "REAL", "100.0"),
                ("energy_required", "TEXT", "'MEDIUM'"),
                ("risk_profile", "REAL", "10.0"),
                ("attention_score", "REAL", "1.0"),
                ("decay_rate", "REAL", "0.0"),
                ("last_reviewed_at", "REAL", "NULL"),
                ("provenance", "TEXT", "'STATED'"),
                ("original_goal_text", "TEXT", "NULL"),
                ("definition_of_done", "TEXT", "NULL"),
                ("ttl", "REAL", "NULL"),
                ("last_reaffirmed_at", "REAL", "NULL"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE goals ADD COLUMN {col} {dtype} DEFAULT {dflt}")
                    conn.commit()
                except sqlite3.OperationalError:
                    # Column already exists
                    pass

            for col, dtype, dflt in [
                ("dependency_type", "TEXT", "'HARD'"),
                ("degradation_delta", "REAL", "0.0"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE goal_dependencies ADD COLUMN {col} {dtype} DEFAULT {dflt}")
                    conn.commit()
                except sqlite3.OperationalError:
                    pass

            # Initialize default policy ledger if it doesn't exist
            try:
                from backend.core.config import runtime_data_root
                ledger_path = runtime_data_root() / "backend" / "data" / "policy_ledger.json"
                if not ledger_path.exists():
                    ledger_path.parent.mkdir(parents=True, exist_ok=True)
                    default_policies = [
                        {
                            "policy_id": "POL-DESKTOP-DEFER",
                            "status": "ACTIVE",
                            "title": "Defer unreliable desktop opens",
                            "condition": {"agent": "desktop", "action_type": "DESKTOP_OPEN_APP"},
                            "effect": {"action": "defer", "cooldown_sec": 2},
                        },
                        {
                            "policy_id": "POL-104",
                            "status": "ACTIVE",
                            "title": "Mandatory simulation review before deployment when rollback frequency > 30%",
                            "condition": {"milestone_category": "deployment", "rollback_frequency_threshold": 0.3},
                            "effect": {"action": "mandatory_simulation_review"},
                        }
                    ]
                    ledger_path.write_text(json.dumps(default_policies, indent=2), encoding="utf-8")
            except Exception:
                pass

    @classmethod
    def create_goal(
        cls,
        title: str,
        description: Optional[str] = None,
        priority: str = "MEDIUM",
        target_date: Optional[str] = None,
        success_criteria: Optional[List[str]] = None,
        owner: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        goal_id: Optional[str] = None,
        importance: float = 5.0,
        urgency: float = 5.0,
        strategic_alignment: float = 5.0,
        resource_cost: float = 2.0,
        parent_goal_id: Optional[str] = None,
        owner_agent: Optional[str] = None,
        horizon_type: str = "SHORT_TERM",
        current_state: str = "PROPOSED",
        state_reason: Optional[str] = None,
        importance_score: float = 50.0,
        urgency_score: float = 50.0,
        estimated_value: float = 50.0,
        confidence_score: float = 100.0,
        energy_required: str = "MEDIUM",
        risk_profile: float = 10.0,
        attention_score: float = 1.0,
        decay_rate: float = 0.0,
        provenance: str = "STATED",
        original_goal_text: Optional[str] = None,
        definition_of_done: Optional[str] = None,
        ttl: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Creates a goal with Human-Like Goal System cognitive attributes and logs the creation event."""
        now = time.time()
        g_id = goal_id or f"goal_{uuid.uuid4().hex[:8]}"
        sc_json = json.dumps(success_criteria or [])

        # Determine if this is a cognitive goal based on custom inputs
        is_cognitive = False
        if (
            importance_score != 50.0 or
            urgency_score != 50.0 or
            estimated_value != 50.0 or
            confidence_score != 100.0 or
            decay_rate != 0.0 or
            ttl is not None or
            provenance != "STATED" or
            owner_agent is not None or
            parent_goal_id is not None or
            horizon_type != "SHORT_TERM" or
            current_state != "PROPOSED"
        ):
            is_cognitive = True

        meta_dict = dict(metadata or {})
        if is_cognitive:
            meta_dict["cognitive"] = True
        meta_json = json.dumps(meta_dict)

        orig_text = original_goal_text or f"{title}\n{description or ''}"
        def_done = definition_of_done or sc_json
        last_reaff = now

        # Validate against absolute safety constraints
        violation = cls.validate_against_absolute_policies(title, description)
        if violation:
            current_state = "ABANDONED"
            state_reason = f"Violates absolute safety policy: {violation}"

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO goals (
                        goal_id, title, description, priority, status, created_at, target_date, progress, success_criteria, owner, metadata,
                        importance, urgency, strategic_alignment, resource_cost, priority_score,
                        parent_goal_id, owner_agent, horizon_type, current_state, state_reason,
                        importance_score, urgency_score, estimated_value, confidence_score, energy_required, risk_profile,
                        attention_score, decay_rate, last_reviewed_at, provenance, original_goal_text, definition_of_done,
                        ttl, last_reaffirmed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        g_id, title, description, priority, current_state, now, target_date, sc_json, owner, meta_json,
                        float(importance), float(urgency), float(strategic_alignment), float(resource_cost),
                        parent_goal_id, owner_agent, horizon_type, current_state, state_reason,
                        float(importance_score), float(urgency_score), float(estimated_value), float(confidence_score), energy_required, float(risk_profile),
                        float(attention_score), float(decay_rate), now, provenance, orig_text, def_done,
                        ttl, last_reaff
                    )
                )
                cls._log_event_conn(conn, g_id, "GOAL_CREATED", {"title": title, "priority": priority, "created_at": now})
                if violation:
                    cls._log_event_conn(conn, g_id, "GOAL_VIOLATION", {"policy_id": violation, "reason": state_reason})
                cls._log_progress_conn(conn, g_id, 0.0, "Initial proposed state", now)
                
                # Initialize default metric row
                conn.execute(
                    "INSERT OR IGNORE INTO goal_metrics (goal_id, historical_success_rate, average_execution_duration, rollback_frequency, simulation_prediction_accuracy, actual_token_resource_cost) VALUES (?, 1.0, 0.0, 0.0, 1.0, 0)",
                    (g_id,)
                )

                # Recalculate derived priority score based on new values
                cls._recalculate_priority_score_conn(conn, g_id)
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        return cls.get_goal(g_id)

    @classmethod
    def add_milestones(cls, goal_id: str, milestones_list: List[Dict[str, Any]]) -> None:
        """Adds a batch of milestones to a specific goal."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                for m in milestones_list:
                    m_id = m.get("milestone_id") or f"m_{uuid.uuid4().hex[:6]}"
                    weight = float(m.get("weight", 1.0))
                    conn.execute(
                        """
                        INSERT INTO milestones (milestone_id, goal_id, title, description, status, weight, progress, created_at)
                        VALUES (?, ?, ?, ?, 'PROPOSED', ?, 0.0, ?)
                        """,
                        (m_id, goal_id, m["title"], m.get("description"), weight, now)
                    )
                    cls._log_event_conn(conn, goal_id, "MILESTONE_ADDED", {"milestone_id": m_id, "title": m["title"], "weight": weight})
                cls._recalculate_progress_conn(conn, goal_id, "Milestones added", now)
                cls._recalculate_priority_score_conn(conn, goal_id)
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def update_goal_status(cls, goal_id: str, status: str, reason: str = "Status update") -> Dict[str, Any]:
        """Updates goal status/state, restricted to Executive transitions."""
        allowed = {"PROPOSED", "APPROVED", "ACTIVE", "BLOCKED", "COMPLETED", "FAILED", "ARCHIVED", "CANCELLED",
                   "IDEA", "CONSIDERING", "PLANNING", "WAITING", "ABANDONED", "DORMANT", "STALE_CONTEXT", "STUCK", "CONFLICTED"}
        status_clean = status.upper().strip()
        if status_clean not in allowed:
            raise ValueError(f"Invalid goal status: {status}. Must be one of {allowed}")

        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Promote INFERRED / PROPOSED to STATED on approval/activation
                grow = conn.execute("SELECT provenance FROM goals WHERE goal_id = ?", (goal_id,)).fetchone()
                provenance_clause = ""
                if grow and grow["provenance"] in {"INFERRED", "PROPOSED"} and status_clean in {"APPROVED", "ACTIVE"}:
                    provenance_clause = ", provenance = 'STATED'"
                
                conn.execute(
                    f"UPDATE goals SET status = ?, current_state = ?, state_reason = ?, last_reviewed_at = ? {provenance_clause} WHERE goal_id = ?",
                    (status_clean, status_clean, reason, now, goal_id)
                )
                cls._log_event_conn(conn, goal_id, "GOAL_STATUS_CHANGED", {"status": status_clean, "reason": reason})
                cls._recalculate_progress_conn(conn, goal_id, f"Status updated to {status_clean}", now)
                cls._recalculate_priority_score_conn(conn, goal_id)
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        return cls.get_goal(goal_id)

    @classmethod
    def update_milestone(
        cls,
        milestone_id: str,
        progress: Optional[float] = None,
        status: Optional[str] = None,
        expected_duration_sec: Optional[float] = None,
        success_probability: Optional[float] = None,
        rollback_risk: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Updates milestone progress/status and triggers overall goal progress updates."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Retrieve current milestone details
                row = conn.execute("SELECT * FROM milestones WHERE milestone_id = ?", (milestone_id,)).fetchone()
                if not row:
                    raise KeyError(f"Milestone '{milestone_id}' not found.")

                goal_id = row["goal_id"]
                updates = []
                params = []

                if progress is not None:
                    prog_val = max(0.0, min(1.0, float(progress)))
                    updates.append("progress = ?")
                    params.append(prog_val)
                if status is not None:
                    st_val = status.upper().strip()
                    updates.append("status = ?")
                    params.append(st_val)
                    if st_val == "COMPLETED":
                        updates.append("completed_at = ?")
                        params.append(now)
                        updates.append("progress = ?")
                        params.append(1.0)
                if expected_duration_sec is not None:
                    updates.append("expected_duration_sec = ?")
                    params.append(float(expected_duration_sec))
                if success_probability is not None:
                    updates.append("success_probability = ?")
                    params.append(float(success_probability))
                if rollback_risk is not None:
                    updates.append("rollback_risk = ?")
                    params.append(float(rollback_risk))

                if updates:
                    params.append(milestone_id)
                    conn.execute(
                        f"UPDATE milestones SET {', '.join(updates)} WHERE milestone_id = ?",
                        tuple(params)
                    )
                    cls._log_event_conn(
                        conn,
                        goal_id,
                        "MILESTONE_UPDATED",
                        {
                            "milestone_id": milestone_id,
                            "progress": progress,
                            "status": status,
                        }
                    )

                # Recompute derived progress
                cls._recalculate_progress_conn(conn, goal_id, f"Milestone {milestone_id} update", now)
                cls._recalculate_priority_score_conn(conn, goal_id)
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        return cls.get_goal(goal_id)

    @classmethod
    def add_dependency(cls, goal_id: str, depends_on_goal_id: str, dependency_type: str = "HARD", degradation_delta: float = 0.0) -> None:
        """Adds a dependency mapping between goals, checking for cycle regressions."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Verify existence
                g = conn.execute("SELECT goal_id FROM goals WHERE goal_id = ?", (goal_id,)).fetchone()
                d = conn.execute("SELECT goal_id FROM goals WHERE goal_id = ?", (depends_on_goal_id,)).fetchone()
                if not g or not d:
                    raise ValueError("Both goals must exist to map dependencies.")

                conn.execute(
                    "INSERT OR REPLACE INTO goal_dependencies (goal_id, depends_on_goal_id, dependency_type, degradation_delta) VALUES (?, ?, ?, ?)",
                    (goal_id, depends_on_goal_id, dependency_type.upper().strip(), float(degradation_delta))
                )

                # Check cycle
                if cls._has_dependency_cycle(conn):
                    conn.execute(
                        "DELETE FROM goal_dependencies WHERE goal_id = ? AND depends_on_goal_id = ?",
                        (goal_id, depends_on_goal_id)
                    )
                    raise ValueError("Dependency cycle detected!")

                cls._log_event_conn(conn, goal_id, "DEPENDENCY_ADDED", {"depends_on": depends_on_goal_id, "dependency_type": dependency_type})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_goal(cls, goal_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves complete details of a single goal including milestones, dependencies, values, conflicts, and metrics."""
        cls.check_goal_ttl(goal_id)

        conn = cls._get_sqlite_conn()
        try:
            cls._recalculate_priority_score_conn(conn, goal_id)
            grow = conn.execute("SELECT * FROM goals WHERE goal_id = ?", (goal_id,)).fetchone()
            if not grow:
                return None

            mrows = conn.execute("SELECT * FROM milestones WHERE goal_id = ? ORDER BY created_at ASC", (goal_id,)).fetchall()
            drows = conn.execute("SELECT * FROM goal_dependencies WHERE goal_id = ?", (goal_id,)).fetchall()
            val_rows = conn.execute("SELECT * FROM goal_values WHERE goal_id = ?", (goal_id,)).fetchall()
            conflict_rows = conn.execute("SELECT * FROM goal_conflicts WHERE goal_a_id = ? OR goal_b_id = ?", (goal_id, goal_id)).fetchall()
            metric_row = conn.execute("SELECT * FROM goal_metrics WHERE goal_id = ?", (goal_id,)).fetchone()

            milestones = []
            for m in mrows:
                milestones.append({
                    "milestone_id": m["milestone_id"],
                    "goal_id": m["goal_id"],
                    "title": m["title"],
                    "description": m["description"],
                    "status": m["status"],
                    "weight": m["weight"],
                    "progress": m["progress"],
                    "created_at": m["created_at"],
                    "completed_at": m["completed_at"],
                    "expected_duration_sec": m["expected_duration_sec"],
                    "success_probability": m["success_probability"],
                    "rollback_risk": m["rollback_risk"],
                })

            dependencies = [d["depends_on_goal_id"] for d in drows]
            dep_details = []
            for d in drows:
                d_dict = dict(d)
                dep_details.append({
                    "depends_on_goal_id": d_dict["depends_on_goal_id"],
                    "dependency_type": d_dict.get("dependency_type", "HARD"),
                    "degradation_delta": d_dict.get("degradation_delta", 0.0)
                })

            return {
                "goal_id": grow["goal_id"],
                "title": grow["title"],
                "description": grow["description"],
                "priority": grow["priority"],
                "status": grow["status"],
                "created_at": grow["created_at"],
                "target_date": grow["target_date"],
                "progress": grow["progress"],
                "success_criteria": json.loads(grow["success_criteria"]),
                "owner": grow["owner"],
                "metadata": json.loads(grow["metadata"]),
                "importance": grow["importance"],
                "urgency": grow["urgency"],
                "strategic_alignment": grow["strategic_alignment"],
                "resource_cost": grow["resource_cost"],
                "priority_score": grow["priority_score"],
                "milestones": milestones,
                "dependencies": dependencies,
                "dependency_details": dep_details,
                # Human-Like additions:
                "parent_goal_id": grow["parent_goal_id"],
                "owner_agent": grow["owner_agent"],
                "horizon_type": grow["horizon_type"],
                "current_state": grow["current_state"],
                "state_reason": grow["state_reason"],
                "importance_score": grow["importance_score"],
                "urgency_score": grow["urgency_score"],
                "estimated_value": grow["estimated_value"],
                "confidence_score": grow["confidence_score"],
                "energy_required": grow["energy_required"],
                "risk_profile": grow["risk_profile"],
                "attention_score": grow["attention_score"],
                "decay_rate": grow["decay_rate"],
                "last_reviewed_at": grow["last_reviewed_at"],
                "provenance": grow["provenance"],
                "original_goal_text": grow["original_goal_text"],
                "definition_of_done": grow["definition_of_done"],
                "ttl": grow["ttl"],
                "last_reaffirmed_at": grow["last_reaffirmed_at"],
                "conflicts": [dict(c) for c in conflict_rows],
                "values": [dict(v) for v in val_rows],
                "metrics": dict(metric_row) if metric_row else None
            }
        finally:
            conn.close()

    @classmethod
    def list_goals(cls, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all goals, optionally filtered by status."""
        conn = cls._get_sqlite_conn()
        try:
            # Batch TTL checks for active/dormant goals
            now = time.time()
            rows_ttl = conn.execute(
                "SELECT goal_id, ttl, last_reaffirmed_at, current_state FROM goals WHERE ttl IS NOT NULL AND current_state NOT IN ('COMPLETED', 'ABANDONED', 'ARCHIVED')"
            ).fetchall()
        finally:
            conn.close()

        for r in rows_ttl:
            elapsed = now - r["last_reaffirmed_at"]
            if (r["current_state"] != "DORMANT" and elapsed > r["ttl"]) or (r["current_state"] == "DORMANT" and elapsed > r["ttl"] * 2):
                cls.check_goal_ttl(r["goal_id"])

        conn = cls._get_sqlite_conn()
        try:
            query = "SELECT goal_id FROM goals"
            params = []
            if status:
                query += " WHERE status = ?"
                params.append(status.upper().strip())

            rows = conn.execute(query, tuple(params)).fetchall()
            results = []
            for r in rows:
                g = cls.get_goal(r["goal_id"])
                if g:
                    results.append(g)
            return results
        finally:
            conn.close()

    @classmethod
    def get_events(cls, goal_id: str) -> List[Dict[str, Any]]:
        """Fetches the append-only event trail for a goal."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM goal_events WHERE goal_id = ? ORDER BY timestamp ASC",
                (goal_id,)
            ).fetchall()
            return [
                {
                    "event_id": r["event_id"],
                    "goal_id": r["goal_id"],
                    "event_type": r["event_type"],
                    "payload": json.loads(r["payload"]),
                    "timestamp": r["timestamp"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    @classmethod
    def get_progress_history(cls, goal_id: str) -> List[Dict[str, Any]]:
        """Fetches the historical progress log."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM goal_progress WHERE goal_id = ? ORDER BY timestamp ASC",
                (goal_id,)
            ).fetchall()
            return [
                {
                    "progress_id": r["progress_id"],
                    "goal_id": r["goal_id"],
                    "progress": r["progress"],
                    "reason": r["reason"],
                    "timestamp": r["timestamp"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    # -- Human-Like Goal System methods --------------------------------------

    @classmethod
    def add_conflict(cls, goal_a_id: str, goal_b_id: str, conflict_topology: str, severity_rating: float = 50.0) -> Dict[str, Any]:
        """Logs a conflict between two goals."""
        c_id = f"conflict_{uuid.uuid4().hex[:8]}"
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    "INSERT INTO goal_conflicts (conflict_id, goal_a_id, goal_b_id, conflict_topology, severity_rating, resolution_status) VALUES (?, ?, ?, ?, ?, 'UNRESOLVED')",
                    (c_id, goal_a_id, goal_b_id, conflict_topology.upper().strip(), float(severity_rating))
                )
                cls._log_event_conn(conn, goal_a_id, "GOAL_CONFLICT_DETECTED", {"conflict_id": c_id, "goal_b_id": goal_b_id, "topology": conflict_topology})
                cls._log_event_conn(conn, goal_b_id, "GOAL_CONFLICT_DETECTED", {"conflict_id": c_id, "goal_a_id": goal_a_id, "topology": conflict_topology})

                # Update states of both goals to CONFLICTED
                conn.execute("UPDATE goals SET status = 'CONFLICTED', current_state = 'CONFLICTED', state_reason = ? WHERE goal_id = ? AND status NOT IN ('COMPLETED', 'ABANDONED', 'ARCHIVED')",
                             (f"Conflict {c_id} with {goal_b_id}", goal_a_id))
                conn.execute("UPDATE goals SET status = 'CONFLICTED', current_state = 'CONFLICTED', state_reason = ? WHERE goal_id = ? AND status NOT IN ('COMPLETED', 'ABANDONED', 'ARCHIVED')",
                             (f"Conflict {c_id} with {goal_a_id}", goal_b_id))

                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        return {"conflict_id": c_id, "goal_a_id": goal_a_id, "goal_b_id": goal_b_id, "conflict_topology": conflict_topology, "severity_rating": severity_rating, "resolution_status": "UNRESOLVED"}

    @classmethod
    def resolve_conflict(cls, conflict_id: str, status: str = "MITIGATED") -> None:
        """Resolves a logged conflict."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT goal_a_id, goal_b_id FROM goal_conflicts WHERE conflict_id = ?", (conflict_id,)).fetchone()
                if not row:
                    return
                goal_a, goal_b = row["goal_a_id"], row["goal_b_id"]
                conn.execute(
                    "UPDATE goal_conflicts SET resolution_status = ? WHERE conflict_id = ?",
                    (status.upper().strip(), conflict_id)
                )
                cls._log_event_conn(conn, goal_a, "GOAL_CONFLICT_RESOLVED", {"conflict_id": conflict_id, "status": status})
                cls._log_event_conn(conn, goal_b, "GOAL_CONFLICT_RESOLVED", {"conflict_id": conflict_id, "status": status})

                # Check if there are other unresolved conflicts. If none, restore to ACTIVE
                for g_id in (goal_a, goal_b):
                    other = conn.execute("SELECT COUNT(*) as count FROM goal_conflicts WHERE (goal_a_id = ? OR goal_b_id = ?) AND resolution_status = 'UNRESOLVED'", (g_id, g_id)).fetchone()
                    if other["count"] == 0:
                        conn.execute("UPDATE goals SET status = 'ACTIVE', current_state = 'ACTIVE', state_reason = 'Conflict resolved' WHERE goal_id = ? AND status = 'CONFLICTED'", (g_id,))

                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def add_value_alignment(cls, goal_id: str, core_policy_constraint: str, alignment_status: str) -> None:
        """Appends value/policy alignment status check to a goal."""
        v_id = f"val_{uuid.uuid4().hex[:8]}"
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    "INSERT INTO goal_values (value_id, goal_id, core_policy_constraint, alignment_status) VALUES (?, ?, ?, ?)",
                    (v_id, goal_id, core_policy_constraint.upper().strip(), alignment_status.upper().strip())
                )
                cls._log_event_conn(conn, goal_id, "VALUE_ALIGNMENT_CHECK", {"core_policy_constraint": core_policy_constraint, "alignment_status": alignment_status})

                # If alignment status is VIOLATING, reject/abandon the goal
                if alignment_status.upper().strip() == "VIOLATING":
                    conn.execute("UPDATE goals SET status = 'ABANDONED', current_state = 'ABANDONED', state_reason = ? WHERE goal_id = ?",
                                 (f"Violates core policy: {core_policy_constraint}", goal_id))

                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_conflicts(cls, goal_id: str) -> List[Dict[str, Any]]:
        """Returns all conflicts mapped to a goal."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM goal_conflicts WHERE goal_a_id = ? OR goal_b_id = ?", (goal_id, goal_id)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def get_values(cls, goal_id: str) -> List[Dict[str, Any]]:
        """Returns all value checks mapped to a goal."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM goal_values WHERE goal_id = ?", (goal_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def _check_goal_drift_conn(cls, conn: sqlite3.Connection, goal_id: str) -> Dict[str, Any]:
        row = conn.execute("SELECT title, description, original_goal_text FROM goals WHERE goal_id = ?", (goal_id,)).fetchone()
        if not row:
            return {"drift_detected": False, "drift_score": 0.0}

        title = row["title"] or ""
        desc = row["description"] or ""
        orig = row["original_goal_text"] or f"{title}\n{desc}"

        curr_text = f"{title} {desc}"

        words_orig = {w.lower().strip(".,!?()\"'") for w in orig.split() if len(w) > 2}
        words_curr = {w.lower().strip(".,!?()\"'") for w in curr_text.split() if len(w) > 2}

        if not words_orig or not words_curr:
            drift_score = 0.0
            drift_detected = False
        else:
            intersection = words_orig.intersection(words_curr)
            union = words_orig.union(words_curr)
            similarity = len(intersection) / len(union)
            drift_score = round(1.0 - similarity, 2)
            drift_detected = drift_score > 0.5

        return {
            "drift_detected": drift_detected,
            "drift_score": drift_score,
            "original_goal_text": orig,
            "current_text": curr_text
        }

    @classmethod
    def check_goal_drift(cls, goal_id: str) -> Dict[str, Any]:
        """Performs Jaccard similarity word overlap check against the immutable original text to detect semantic drift."""
        conn = cls._get_sqlite_conn()
        try:
            res = cls._check_goal_drift_conn(conn, goal_id)
            if res["drift_detected"]:
                cls._log_event_conn(conn, goal_id, "DRIFT_ALERT", {"drift_score": res["drift_score"]})
                # Auto-transition to STALE_CONTEXT
                conn.execute(
                    "UPDATE goals SET status = 'CONFLICTED', current_state = 'STALE_CONTEXT', state_reason = ? WHERE goal_id = ? AND status NOT IN ('COMPLETED', 'ABANDONED', 'ARCHIVED')",
                    (f"Goal drifted significantly (score {res['drift_score']})", goal_id)
                )
                conn.commit()
            return res
        finally:
            conn.close()

    @classmethod
    def update_goal_content(cls, goal_id: str, title: str, description: Optional[str] = None) -> Dict[str, Any]:
        """Updates a goal's title and description, saving revision history in metadata and calculating drift."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT title, description, metadata, original_goal_text FROM goals WHERE goal_id = ?", (goal_id,)).fetchone()
                if not row:
                    raise KeyError(f"Goal '{goal_id}' not found.")
                
                old_title = row["title"]
                old_desc = row["description"]
                try:
                    meta = json.loads(row["metadata"] or "{}")
                except Exception:
                    meta = {}
                
                # Append to revisions list in metadata
                revisions = meta.setdefault("revisions", [])
                revisions.append({
                    "timestamp": now,
                    "previous_title": old_title,
                    "previous_description": old_desc
                })
                
                meta_json = json.dumps(meta)
                
                # Update text in database
                conn.execute(
                    "UPDATE goals SET title = ?, description = ?, metadata = ?, last_reviewed_at = ? WHERE goal_id = ?",
                    (title.strip(), description, meta_json, now, goal_id)
                )
                cls._log_event_conn(conn, goal_id, "GOAL_CONTENT_UPDATED", {"timestamp": now, "title": title})
                
                # Re-calculate drift score
                drift_res = cls._check_goal_drift_conn(conn, goal_id)
                
                # If drift > 0.5, transition goal to CONFLICTED / STALE_CONTEXT
                if drift_res["drift_detected"]:
                    conn.execute(
                        "UPDATE goals SET status = 'CONFLICTED', current_state = 'STALE_CONTEXT', state_reason = ? WHERE goal_id = ? AND status NOT IN ('COMPLETED', 'ABANDONED', 'ARCHIVED')",
                        (f"Goal drifted significantly (score {drift_res['drift_score']}) from original statement", goal_id)
                    )
                    cls._log_event_conn(conn, goal_id, "DRIFT_HALT", {"drift_score": drift_res["drift_score"]})
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        return cls.get_goal(goal_id)

    @classmethod
    def reaffirm_goal(cls, goal_id: str) -> Dict[str, Any]:
        """Reaffirms a goal, updating reaffirm timestamp and restoring DORMANT status."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT current_state, status FROM goals WHERE goal_id = ?", (goal_id,)).fetchone()
                if not row:
                    raise KeyError(f"Goal '{goal_id}' not found.")

                current_state = row["current_state"]
                new_state = current_state
                if current_state == "DORMANT":
                    new_state = "ACTIVE"

                conn.execute(
                    "UPDATE goals SET last_reaffirmed_at = ?, current_state = ?, status = ?, last_reviewed_at = ? WHERE goal_id = ?",
                    (now, new_state, new_state, now, goal_id)
                )
                cls._log_event_conn(conn, goal_id, "GOAL_REAFFIRMED", {"timestamp": now, "previous_state": current_state})
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        return cls.get_goal(goal_id)

    @classmethod
    def update_goal_metadata(cls, goal_id: str, metadata: dict) -> None:
        """Updates a goal's metadata."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    "UPDATE goals SET metadata = ? WHERE goal_id = ?",
                    (json.dumps(metadata), goal_id)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def check_goal_ttl(cls, goal_id: str) -> bool:
        """Checks if the goal's TTL has expired. Handles ACTIVE -> DORMANT and DORMANT -> ARCHIVED transitions."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT current_state, ttl, last_reaffirmed_at FROM goals WHERE goal_id = ?", (goal_id,)).fetchone()
                if not row:
                    return False
                current_state = row["current_state"]
                ttl = row["ttl"]
                last_reaff = row["last_reaffirmed_at"]

                if ttl is not None and last_reaff is not None:
                    elapsed = now - last_reaff
                    if elapsed > ttl:
                        if current_state not in {"DORMANT", "COMPLETED", "ABANDONED", "ARCHIVED"}:
                            # Transition to DORMANT
                            conn.execute(
                                "UPDATE goals SET status = 'DORMANT', current_state = 'DORMANT', state_reason = 'TTL expired without reaffirmation', last_reviewed_at = ? WHERE goal_id = ?",
                                (now, goal_id)
                            )
                            cls._log_event_conn(conn, goal_id, "DECAY_ALERT", {"reason": "Goal became DORMANT due to TTL expiration"})
                            cls._log_progress_conn(conn, goal_id, 0.0, "Dormant transition", now)
                            conn.commit()
                            return True
                        elif current_state == "DORMANT" and elapsed > ttl * 2:
                            # Transition to ARCHIVED
                            conn.execute(
                                "UPDATE goals SET status = 'ARCHIVED', current_state = 'ARCHIVED', state_reason = 'TTL expired dormant goal archived', last_reviewed_at = ? WHERE goal_id = ?",
                                (now, goal_id)
                            )
                            cls._log_event_conn(conn, goal_id, "GOAL_ARCHIVED", {"reason": "Dormant goal archived due to prolonged inactivity"})
                            conn.commit()
                            return True
            except Exception:
                pass
            finally:
                conn.close()
        return False

    # -- Internal helpers execution inside open SQLite transaction locks -----

    @staticmethod
    def _log_event_conn(conn: sqlite3.Connection, goal_id: str, event_type: str, payload: dict) -> None:
        conn.execute(
            "INSERT INTO goal_events (goal_id, event_type, payload, timestamp) VALUES (?, ?, ?, ?)",
            (goal_id, event_type, json.dumps(payload), time.time())
        )
        log_event("goal_event", {"goal_id": goal_id, "event_type": event_type, **payload})

    @staticmethod
    def _log_progress_conn(conn: sqlite3.Connection, goal_id: str, progress: float, reason: str, timestamp: float) -> None:
        conn.execute(
            "INSERT INTO goal_progress (goal_id, progress, reason, timestamp) VALUES (?, ?, ?, ?)",
            (goal_id, progress, reason, timestamp)
        )

    @classmethod
    def _recalculate_progress_conn(cls, conn: sqlite3.Connection, goal_id: str, reason: str, timestamp: float, visited: Optional[set[str]] = None) -> None:
        if visited is None:
            visited = set()
        if goal_id in visited:
            return
        visited.add(goal_id)

        # Get all milestones weights & progress
        mrows = conn.execute("SELECT progress, weight, status FROM milestones WHERE goal_id = ?", (goal_id,)).fetchall()

        goal_row = conn.execute("SELECT status, progress, metadata FROM goals WHERE goal_id = ?", (goal_id,)).fetchone()
        if not goal_row:
            return

        current_status = goal_row["status"]
        current_progress = goal_row["progress"]

        # Check child subgoals
        subgoals = []
        all_rows = conn.execute("SELECT goal_id, status, progress, metadata FROM goals").fetchall()
        for r in all_rows:
            if r["goal_id"] == goal_id:
                continue
            try:
                meta = json.loads(r["metadata"] or "{}")
                if meta.get("parent_id") == goal_id:
                    subgoals.append(r)
            except Exception:
                pass

        if subgoals:
            derived = round(sum(float(g["progress"]) for g in subgoals) / len(subgoals), 4)
        elif not mrows:
            derived = 1.0 if current_status == "COMPLETED" else 0.0
        else:
            total_weight = sum(float(r["weight"]) for r in mrows)
            weighted_prog = sum(float(r["progress"]) * float(r["weight"]) for r in mrows)
            derived = round(weighted_prog / total_weight, 4) if total_weight else 0.0

        # Update progress
        conn.execute(
            "UPDATE goals SET progress = ? WHERE goal_id = ?",
            (derived, goal_id)
        )

        # Autocomplete goal if all milestones/subgoals are completed and goal is active/approved
        all_milestones_done = len(mrows) > 0 and all(r["status"] == "COMPLETED" for r in mrows)
        all_subgoals_done = len(subgoals) > 0 and all(r["status"] == "COMPLETED" for r in subgoals)
        all_done = all_milestones_done or all_subgoals_done
        if all_done and current_status in {"APPROVED", "ACTIVE"}:
            conn.execute(
                "UPDATE goals SET status = 'COMPLETED', progress = 1.0 WHERE goal_id = ?",
                (goal_id,)
            )
            cls._log_event_conn(conn, goal_id, "GOAL_COMPLETED", {"reason": "All milestones/subgoals completed successfully"})
            cls._log_progress_conn(conn, goal_id, 1.0, "Auto-completed", timestamp)
            derived = 1.0
        elif abs(derived - current_progress) > 1e-4:
            cls._log_event_conn(conn, goal_id, "GOAL_PROGRESS_UPDATED", {"progress": derived, "reason": reason})
            cls._log_progress_conn(conn, goal_id, derived, reason, timestamp)

        # Propagate to parent if exists
        try:
            meta = json.loads(goal_row["metadata"] or "{}")
            parent_id = meta.get("parent_id")
            if parent_id:
                cls._recalculate_progress_conn(conn, parent_id, f"Child {goal_id} progress updated", timestamp, visited)
        except Exception:
            pass

    @staticmethod
    def _has_dependency_cycle(conn: sqlite3.Connection) -> bool:
        rows = conn.execute("SELECT goal_id, depends_on_goal_id FROM goal_dependencies").fetchall()
        adj: dict[str, set[str]] = {}
        for r in rows:
            adj.setdefault(r["goal_id"], set()).add(r["depends_on_goal_id"])

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
    def _recalculate_priority_score_conn(cls, conn: sqlite3.Connection, goal_id: str) -> None:
        grow = conn.execute(
            """
            SELECT created_at, importance, urgency, strategic_alignment, resource_cost,
                   importance_score, urgency_score, estimated_value, confidence_score,
                   energy_required, risk_profile, decay_rate, last_reviewed_at, current_state, metadata
            FROM goals WHERE goal_id = ?
            """,
            (goal_id,)
        ).fetchone()
        if not grow:
            return

        if grow["current_state"] == "DORMANT":
            conn.execute("UPDATE goals SET priority_score = 0.0 WHERE goal_id = ?", (goal_id,))
            return

        try:
            meta = json.loads(grow["metadata"] or "{}")
        except Exception:
            meta = {}

        if meta.get("cognitive", False):
            # Advanced Human-Like priority score calculation
            importance_val = float(grow["importance_score"] if grow["importance_score"] is not None else float(grow["importance"]) * 10.0)
            urgency_val = float(grow["urgency_score"] if grow["urgency_score"] is not None else float(grow["urgency"]) * 10.0)
            alignment_val = float(grow["strategic_alignment"]) * 10.0 if grow["strategic_alignment"] is not None else 50.0
            value_val = float(grow["estimated_value"] if grow["estimated_value"] is not None else 50.0)
            confidence_val = float(grow["confidence_score"] if grow["confidence_score"] is not None else 100.0) / 100.0

            energy_req = grow["energy_required"] or "MEDIUM"
            energy_val = 1.0 if energy_req == "LOW" else 4.0 if energy_req == "HIGH" else 2.0
            risk_val = max(1.0, float(grow["risk_profile"] if grow["risk_profile"] is not None else 10.0))

            last_ref = grow["last_reviewed_at"] if grow["last_reviewed_at"] is not None else grow["created_at"]
            elapsed_days = max(0.0, time.time() - last_ref) / 86400.0
            decay_rate = float(grow["decay_rate"] if grow["decay_rate"] is not None else 0.0)
            decay_coeff = math.exp(decay_rate * elapsed_days)

            numerator = importance_val * urgency_val * alignment_val * value_val * confidence_val
            denominator = energy_val * risk_val * decay_coeff
            priority_score = round(numerator / denominator, 2)
        else:
            # Legacy priority score calculation
            importance = float(grow["importance"])
            urgency = float(grow["urgency"])
            alignment = float(grow["strategic_alignment"])
            cost = max(0.1, float(grow["resource_cost"]))

            mrows = conn.execute("SELECT success_probability FROM milestones WHERE goal_id = ?", (goal_id,)).fetchall()
            probs = [float(r["success_probability"]) for r in mrows if r["success_probability"] is not None]
            success_prob = sum(probs) / len(probs) if probs else 1.0

            priority_score = round((importance * urgency * alignment * success_prob) / cost, 2)

        conn.execute("UPDATE goals SET priority_score = ? WHERE goal_id = ?", (priority_score, goal_id))

    @classmethod
    def reset(cls) -> None:
        """Reset databases. Purely helper for test setup isolation."""
        with cls._lock:
            cls._schema_ensured = False
            conn = cls._get_sqlite_conn()
            try:
                conn.execute("DELETE FROM goals")
                conn.execute("DELETE FROM milestones")
                conn.execute("DELETE FROM goal_events")
                conn.execute("DELETE FROM goal_progress")
                conn.execute("DELETE FROM goal_dependencies")
                conn.execute("DELETE FROM goal_values")
                conn.execute("DELETE FROM goal_conflicts")
                conn.execute("DELETE FROM goal_metrics")
                conn.commit()
            finally:
                conn.close()
