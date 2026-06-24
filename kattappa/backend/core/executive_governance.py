"""Executive Governance Subsystem (Step 14).

Arbitrates competing goals, gates tool executions, bounds cognitive planning loops,
records resource budgets, and audits human reviewer agreement rates.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, Optional

from backend.core.config import load_config




def _get_sqlite_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = config.sqlite_path.parent / "executive_governance.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='executive_tasks'")
    if cursor.fetchone():
        return
        
    conn.execute("PRAGMA foreign_keys = ON;")
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS executive_tasks (
            id TEXT PRIMARY KEY,
            task_name TEXT NOT NULL,
            priority REAL NOT NULL CHECK (priority BETWEEN 0.0 AND 1.0),
            urgency REAL NOT NULL CHECK (urgency BETWEEN 0.0 AND 1.0),
            token_budget INTEGER NOT NULL CHECK (token_budget > 0),
            max_execution_seconds INTEGER NOT NULL CHECK (max_execution_seconds > 0),
            replan_count INTEGER DEFAULT 0 CHECK (replan_count >= 0),
            state TEXT DEFAULT 'QUEUED' CHECK (state IN ('QUEUED', 'RUNNING', 'BLOCKED', 'COMPLETED', 'ABANDONED')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS arbitration_ledger (
            id TEXT PRIMARY KEY,
            task_id TEXT REFERENCES executive_tasks(id) ON DELETE CASCADE,
            conflict_type TEXT NOT NULL CHECK (conflict_type IN ('RESOURCE_EXCEEDED', 'SAFETY_VETO', 'GOAL_THRASHING', 'USER_INTERRUPTION', 'REFLECTION_OVERRIDE')),
            details_json TEXT NOT NULL,
            resolution_action TEXT NOT NULL CHECK (resolution_action IN ('PAUSE', 'ABORT', 'RE-ROUTE', 'HUMAN_APPROVAL_REQUIRED', 'PROCEED')),
            reviewer_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS resource_ledger (
            id TEXT PRIMARY KEY,
            task_id TEXT REFERENCES executive_tasks(id) ON DELETE SET NULL,
            resource_type TEXT NOT NULL CHECK (resource_type IN ('tokens', 'api_calls', 'compute_cost_usd', 'execution_time_ms')),
            amount_consumed REAL NOT NULL CHECK (amount_consumed >= 0.0),
            daily_limit REAL NOT NULL CHECK (daily_limit >= 0.0),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviewer_metrics (
            reviewer_id TEXT NOT NULL,
            task_id TEXT REFERENCES executive_tasks(id),
            executive_recommendation TEXT NOT NULL,
            reviewer_decision TEXT NOT NULL,
            congruent INTEGER CHECK (congruent IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
            PRIMARY KEY (reviewer_id, task_id)
        )
    """)
    
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exec_task_state ON executive_tasks(state);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_arbitration_task ON arbitration_ledger(task_id);")
    
    conn.commit()


class ExecutiveCortex:
    @classmethod
    def get_db_conn(cls) -> sqlite3.Connection:
        conn = _get_sqlite_conn()
        _ensure_schema(conn)
        return conn

    @classmethod
    def arbitrate_task(
        cls,
        task_id: str,
        task_name: str,
        priority: float,
        urgency: float,
        token_budget: int,
        max_execution_seconds: int,
    ) -> dict[str, Any]:
        """Arbitrate a task queue state and allocate attention."""
        conn = cls.get_db_conn()
        cursor = conn.cursor()
        
        # Calculate dynamic decision weight W
        w = (priority * 0.6) + (urgency * 0.4)
        
        # Check if task already exists
        cursor.execute("SELECT * FROM executive_tasks WHERE id = ?", (task_id,))
        task_row = cursor.fetchone()
        
        if task_row:
            replan_count = task_row["replan_count"]
            state = task_row["state"]
        else:
            replan_count = 0
            state = "QUEUED"
            cursor.execute("""
                INSERT INTO executive_tasks (id, task_name, priority, urgency, token_budget, max_execution_seconds, replan_count, state)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (task_id, task_name, priority, urgency, token_budget, max_execution_seconds, replan_count, state))
            conn.commit()

        action = "PROCEED"
        details = {}
        
        if w < 0.3:
            action = "PAUSE"
            state = "BLOCKED"
            details = {"reason": f"Weighted priority {w:.2f} is below dynamic attention floor of 0.30"}
            cursor.execute("UPDATE executive_tasks SET state = ? WHERE id = ?", (state, task_id))
            cursor.execute("""
                INSERT INTO arbitration_ledger (id, task_id, conflict_type, details_json, resolution_action)
                VALUES (?, ?, 'USER_INTERRUPTION', ?, ?)
            """, (f"ARB-{task_id}-{int(time.time())}", task_id, json.dumps(details), action))
            conn.commit()
            
        return {
            "task_id": task_id,
            "weight": round(w, 2),
            "state": state,
            "action": action,
            "details": details
        }

    @classmethod
    def replan_increment(cls, task_id: str) -> dict[str, Any]:
        """Increments task replan count and triggers safety controls if thrashing is detected."""
        conn = cls.get_db_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT replan_count, task_name FROM executive_tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            raise KeyError(f"Task not found: {task_id}")
            
        new_count = row["replan_count"] + 1
        cursor.execute("UPDATE executive_tasks SET replan_count = ? WHERE id = ?", (new_count, task_id))
        conn.commit()
        
        action = "PROCEED"
        state = "RUNNING"
        details = {}
        
        if new_count > 3:
            action = "ABORT"
            state = "BLOCKED"
            details = {"reason": f"Task replan count {new_count} exceeded limit of 3. Potential cognitive planning loop."}
            cursor.execute("UPDATE executive_tasks SET state = ? WHERE id = ?", (state, task_id))
            cursor.execute("""
                INSERT INTO arbitration_ledger (id, task_id, conflict_type, details_json, resolution_action)
                VALUES (?, ?, 'GOAL_THRASHING', ?, ?)
            """, (f"ARB-THRASH-{task_id}-{int(time.time())}", task_id, json.dumps(details), action))
            conn.commit()
            
        return {
            "task_id": task_id,
            "replan_count": new_count,
            "state": state,
            "action": action,
            "details": details
        }

    @classmethod
    def record_resource_consumption(
        cls,
        task_id: str,
        resource_type: str,
        amount: float,
        daily_limit: float
    ) -> dict[str, Any]:
        """Record resources consumed and verify against daily budget ceilings."""
        conn = cls.get_db_conn()
        cursor = conn.cursor()
        
        today_start = datetime.utcnow().date().isoformat() + " 00:00:00"
        cursor.execute("""
            SELECT SUM(amount_consumed) FROM resource_ledger
            WHERE resource_type = ? AND created_at >= ?
        """, (resource_type, today_start))
        row = cursor.fetchone()
        prev_sum = row[0] if row and row[0] is not None else 0.0
        
        total_today = prev_sum + amount
        
        import uuid
        rid = f"RES-{task_id}-{resource_type}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
        cursor.execute("""
            INSERT INTO resource_ledger (id, task_id, resource_type, amount_consumed, daily_limit)
            VALUES (?, ?, ?, ?, ?)
        """, (rid, task_id, resource_type, amount, daily_limit))
        conn.commit()
        
        action = "PROCEED"
        details = {}
        
        if total_today > daily_limit:
            action = "HUMAN_APPROVAL_REQUIRED"
            details = {
                "reason": f"Daily limit exceeded for resource '{resource_type}'. Limit: {daily_limit}, Attempted Total: {total_today}"
            }
            cursor.execute("""
                INSERT INTO arbitration_ledger (id, task_id, conflict_type, details_json, resolution_action)
                VALUES (?, ?, 'RESOURCE_EXCEEDED', ?, ?)
            """, (f"ARB-RES-{task_id}-{int(time.time())}", task_id, json.dumps(details), action))
            
            cursor.execute("UPDATE executive_tasks SET state = 'BLOCKED' WHERE id = ?", (task_id,))
            conn.commit()
            
        return {
            "task_id": task_id,
            "total_today": total_today,
            "limit": daily_limit,
            "action": action,
            "details": details
        }

    @classmethod
    def record_reviewer_decision(
        cls,
        reviewer_id: str,
        task_id: str,
        recommendation: str,
        decision: str
    ) -> dict[str, Any]:
        """Record human review decision and track alignment/congruence rates."""
        conn = cls.get_db_conn()
        cursor = conn.cursor()
        
        congruent = 1 if recommendation.upper() == decision.upper() else 0
        
        cursor.execute("""
            INSERT OR REPLACE INTO reviewer_metrics (reviewer_id, task_id, executive_recommendation, reviewer_decision, congruent)
            VALUES (?, ?, ?, ?, ?)
        """, (reviewer_id, task_id, recommendation, decision, congruent))
        conn.commit()
        
        cursor.execute("SELECT SUM(congruent), COUNT(*) FROM reviewer_metrics WHERE reviewer_id = ?", (reviewer_id,))
        stats = cursor.fetchone()
        agreement_rate = (stats[0] / stats[1]) if stats and stats[1] > 0 else 1.0
        
        return {
            "reviewer_id": reviewer_id,
            "task_id": task_id,
            "congruent": bool(congruent),
            "agreement_rate": round(agreement_rate, 4),
            "total_reviews": stats[1] if stats else 0
        }
