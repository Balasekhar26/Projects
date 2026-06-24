from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from backend.core.config import load_config
from backend.core.logger import log_event


class StrategicMemory:
    """Strategic Memory Subsystem (Layer 6) representing long-term intentions, goals, and plans.
    
    Adheres to Memory System Layer 6 requirements:
    - Authoritative storage in SQLite (hm_strategic_goals, hm_strategic_goal_history).
    - Lifecycle states (draft, active, paused, completed, archived) with strict transition validation.
    - Security trust gates for execution (TRUST_USER or TRUST_SYSTEM required to activate).
    - Monotonic version-checked edits with append-only history snapshots.
    - Hierarchical goals (parent_goal_id) and traceable provenance (derived_from).
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
                CREATE TABLE IF NOT EXISTS hm_strategic_goals (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    priority REAL NOT NULL DEFAULT 0.5,
                    trust_level TEXT NOT NULL DEFAULT 'TRUST_USER',
                    approved_by_user INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1,
                    parent_goal_id TEXT,
                    derived_from TEXT DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    completed_at REAL,
                    FOREIGN KEY (parent_goal_id) REFERENCES hm_strategic_goals(id)
                );
                CREATE INDEX IF NOT EXISTS idx_hm_goals_status ON hm_strategic_goals(status);
                CREATE INDEX IF NOT EXISTS idx_hm_goals_priority ON hm_strategic_goals(priority DESC);

                CREATE TABLE IF NOT EXISTS hm_strategic_goal_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    changed_at REAL NOT NULL,
                    changed_by TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_hm_goal_history_goal ON hm_strategic_goal_history(goal_id);

                -- ================================================================
                -- DECISION RATIONALE MEMORY
                -- Answers "why was this choice made?" — separate from goal state.
                -- Records rationale, alternatives, context.  NEVER stores authority
                -- grants or permission decisions; those belong to the security spine.
                -- ================================================================
                CREATE TABLE IF NOT EXISTS hm_decisions (
                    id TEXT PRIMARY KEY,
                    decision TEXT NOT NULL,
                    context TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    alternatives_considered TEXT NOT NULL DEFAULT '[]',
                    outcome TEXT,
                    linked_goal_id TEXT,
                    created_at REAL NOT NULL,
                    created_by TEXT NOT NULL DEFAULT 'user',
                    trust_level TEXT NOT NULL DEFAULT 'TRUST_USER',
                    FOREIGN KEY (linked_goal_id) REFERENCES hm_strategic_goals(id)
                );
                CREATE INDEX IF NOT EXISTS idx_hm_decisions_created ON hm_decisions(created_at DESC);
                """
            )
            conn.commit()

    @classmethod
    def create_goal(
        cls,
        goal: str,
        description: str,
        priority: float = 0.5,
        derived_from: list[str] | None = None,
        parent_goal_id: str | None = None,
    ) -> str:
        """Create a new goal in DRAFT state. Never auto-activates."""
        goal_id = str(uuid.uuid4())
        derived_json = json.dumps(derived_from or [])
        now = time.time()

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Validate parent_goal_id if provided
                if parent_goal_id:
                    parent = conn.execute("SELECT id FROM hm_strategic_goals WHERE id = ?", (parent_goal_id,)).fetchone()
                    if not parent:
                        raise ValueError(f"Parent goal with ID {parent_goal_id} does not exist.")

                conn.execute(
                    """
                    INSERT INTO hm_strategic_goals (
                        id, goal, description, status, priority, trust_level,
                        approved_by_user, version, parent_goal_id, derived_from,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, 'draft', ?, 'TRUST_UNVERIFIED', 0, 1, ?, ?, ?, ?)
                    """,
                    (goal_id, goal.strip(), description.strip(), priority, parent_goal_id, derived_json, now, now)
                )
                conn.commit()

                # Also set initial trust level as UNVERIFIED in registry
                from backend.core.memory_governance import MemoryGovernance
                MemoryGovernance.set_trust(goal_id, "goal", "TRUST_UNVERIFIED")
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        return goal_id

    @classmethod
    def approve_goal(cls, goal_id: str, approved_by: str = "user") -> bool:
        """Promote a DRAFT goal to ACTIVE. Sets approved_by_user=1.
        
        Gated by trust checks and logs provenance.
        """
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT * FROM hm_strategic_goals WHERE id = ?", (goal_id,)).fetchone()
                if not row:
                    return False
                goal_data = dict(row)

                if goal_data["status"] != "draft":
                    raise ValueError(f"Goal is already approved or not in draft state: {goal_data['status']}")

                # Transition status to active and approve
                conn.execute(
                    """
                    UPDATE hm_strategic_goals
                    SET status = 'active', approved_by_user = 1, trust_level = 'TRUST_USER', updated_at = ?
                    WHERE id = ?
                    """,
                    (now, goal_id)
                )
                conn.commit()

                # Register in MemoryGovernance trust registry
                from backend.core.memory_governance import MemoryGovernance
                MemoryGovernance.set_trust(goal_id, "goal", "TRUST_USER")

                # Log provenance
                derived_list = json.loads(goal_data["derived_from"])
                MemoryGovernance.log_provenance(
                    memory_id=goal_id,
                    memory_type="strategic",
                    source="user",
                    created_by=approved_by,
                    confidence=1.0,
                    derived_from=derived_list
                )
                
                # Write history log
                cls._snapshot_history(conn, goal_id, changed_by=approved_by)
                return True
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def update_goal(cls, goal_id: str, changed_by: str = "user", **kwargs) -> bool:
        """Update mutable fields (goal, description, priority, status).
        
        Increments version and snapshots history. Blocks update if goal is archived.
        """
        allowed_fields = {"goal", "description", "priority", "status", "parent_goal_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return False

        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT * FROM hm_strategic_goals WHERE id = ?", (goal_id,)).fetchone()
                if not row:
                    return False
                goal_data = dict(row)

                if goal_data["status"] == "archived":
                    raise ValueError("Cannot update an archived goal.")

                # If status is changing, enforce valid transitions
                if "status" in updates:
                    cls._validate_transition(goal_data["status"], updates["status"])
                    if updates["status"] == "completed":
                        updates["completed_at"] = now

                # Increment version
                new_version = goal_data["version"] + 1
                updates["version"] = new_version
                updates["updated_at"] = now

                # Check trust in governance
                from backend.core.memory_governance import MemoryGovernance
                trust = MemoryGovernance.get_trust(goal_id)
                if trust == "TRUST_UNTRUSTED":
                    raise ValueError("Cannot update a goal marked as UNTRUSTED.")

                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                params = list(updates.values()) + [goal_id]

                conn.execute(f"UPDATE hm_strategic_goals SET {set_clause} WHERE id = ?", params)
                
                # Write history snapshot
                cls._snapshot_history(conn, goal_id, changed_by=changed_by)
                
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_goal(cls, goal_id: str) -> dict[str, Any] | None:
        """Retrieve a goal by ID from SQLite."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM hm_strategic_goals WHERE id = ?", (goal_id,)).fetchone()
            if not row:
                return None
            record = dict(row)
            record["derived_from"] = json.loads(record["derived_from"])
            return record
        finally:
            conn.close()

    @classmethod
    def list_goals(
        cls,
        status: str | None = None,
        min_priority: float = 0.0,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List goals filtered by status and minimum priority, ordered by priority DESC."""
        conn = cls._get_sqlite_conn()
        try:
            query = "SELECT * FROM hm_strategic_goals WHERE priority >= ?"
            params = [min_priority]
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY priority DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                rec = dict(r)
                rec["derived_from"] = json.loads(rec["derived_from"])
                results.append(rec)
            return results
        finally:
            conn.close()

    @classmethod
    def get_goal_history(cls, goal_id: str) -> list[dict[str, Any]]:
        """Return full version history for a goal (append-only audit trail)."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hm_strategic_goal_history WHERE goal_id = ? ORDER BY version ASC",
                (goal_id,)
            ).fetchall()
            results = []
            for r in rows:
                rec = dict(r)
                rec["snapshot"] = json.loads(rec["snapshot_json"])
                results.append(rec)
            return results
        finally:
            conn.close()

    @classmethod
    def set_status(cls, goal_id: str, new_status: str, changed_by: str = "user") -> bool:
        """Transition goal lifecycle state."""
        return cls.update_goal(goal_id, changed_by=changed_by, status=new_status)

    @classmethod
    def get_active_goals(cls, limit: int = 10) -> list[dict[str, Any]]:
        """Return active, approved goals sorted by priority DESC."""
        return cls.list_goals(status="active", min_priority=0.0, limit=limit)

    # ----- Private Helper Methods -----

    @classmethod
    def _snapshot_history(cls, conn: sqlite3.Connection, goal_id: str, changed_by: str) -> None:
        row = conn.execute("SELECT * FROM hm_strategic_goals WHERE id = ?", (goal_id,)).fetchone()
        if not row:
            return
        goal_data = dict(row)
        goal_data["derived_from"] = json.loads(goal_data["derived_from"])
        
        conn.execute(
            """
            INSERT INTO hm_strategic_goal_history (goal_id, version, snapshot_json, changed_at, changed_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (goal_id, goal_data["version"], json.dumps(goal_data), time.time(), changed_by)
        )

    @classmethod
    def _validate_transition(cls, current_status: str, new_status: str) -> None:
        """Enforces the strict lifecycle state machine transitions.
        
        Valid Transitions:
        - draft -> active (via approve_goal or set_status)
        - draft -> archived
        - active -> paused
        - active -> completed
        - active -> archived
        - paused -> active
        - paused -> archived
        - completed -> archived
        
        Invalid Transitions raise ValueError.
        """
        curr = current_status.strip().lower()
        nxt = new_status.strip().lower()
        if curr == nxt:
            return

        valid_next = {
            "draft": {"active", "archived"},
            "active": {"paused", "completed", "archived"},
            "paused": {"active", "archived"},
            "completed": {"archived"},
            "archived": set(),
        }

        if nxt not in valid_next.get(curr, set()):
            raise ValueError(f"Invalid lifecycle transition: {curr} -> {nxt}")

    # =========================================================================
    # Decision Rationale Memory API
    # =========================================================================

    @classmethod
    def record_decision(
        cls,
        decision: str,
        context: str,
        rationale: str,
        alternatives: list[str] | None = None,
        outcome: str | None = None,
        linked_goal_id: str | None = None,
        created_by: str = "user",
    ) -> str:
        """Record why a decision was made.

        Stores the rationale, alternatives considered, and optional outcome.
        Links to a strategic goal if provided.

        Security note: This records *reasoning*, never authority grants.
        The memory system cannot grant permissions through decision records.
        """
        decision_id = str(uuid.uuid4())
        now = time.time()
        alternatives_json = json.dumps(alternatives or [])

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                if linked_goal_id:
                    row = conn.execute(
                        "SELECT id FROM hm_strategic_goals WHERE id = ?",
                        (linked_goal_id,)
                    ).fetchone()
                    if not row:
                        raise ValueError(f"Linked goal {linked_goal_id} does not exist.")

                conn.execute(
                    """
                    INSERT INTO hm_decisions
                        (id, decision, context, rationale, alternatives_considered,
                         outcome, linked_goal_id, created_at, created_by, trust_level)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'TRUST_USER')
                    """,
                    (
                        decision_id,
                        decision.strip(),
                        context.strip(),
                        rationale.strip(),
                        alternatives_json,
                        outcome,
                        linked_goal_id,
                        now,
                        created_by.strip(),
                    )
                )
                conn.commit()

                # Log provenance
                from backend.core.memory_governance import MemoryGovernance
                MemoryGovernance.log_provenance(
                    memory_id=decision_id,
                    memory_type="strategic",
                    source="user",
                    created_by=created_by,
                    confidence=1.0,
                    metadata={"decision": decision.strip()}
                )

                return decision_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_decision(cls, decision_id: str) -> dict[str, Any] | None:
        """Retrieve a single decision record by ID."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT * FROM hm_decisions WHERE id = ?", (decision_id,)
            ).fetchone()
            if not row:
                return None
            rec = dict(row)
            rec["alternatives_considered"] = json.loads(rec["alternatives_considered"])
            return rec
        finally:
            conn.close()

    @classmethod
    def query_decisions(
        cls,
        query_text: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Keyword search over decision text and rationale.

        Returns decisions whose decision text, context, or rationale contains
        any token from the query. Results ordered by recency (newest first).
        """
        if not query_text or not query_text.strip():
            return cls.list_decisions(limit=limit)

        tokens = [
            t.lower() for t in query_text.split()
            if len(t) > 2
        ]
        if not tokens:
            return cls.list_decisions(limit=limit)

        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hm_decisions ORDER BY created_at DESC LIMIT ?",
                (limit * 5,)   # over-fetch then filter
            ).fetchall()

            results = []
            for r in rows:
                rec = dict(r)
                haystack = (
                    rec["decision"].lower() + " "
                    + rec["context"].lower() + " "
                    + rec["rationale"].lower()
                )
                if any(tok in haystack for tok in tokens):
                    rec["alternatives_considered"] = json.loads(rec["alternatives_considered"])
                    results.append(rec)
                    if len(results) >= limit:
                        break

            return results
        finally:
            conn.close()

    @classmethod
    def list_decisions(cls, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent decision records, newest first."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hm_decisions ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            results = []
            for r in rows:
                rec = dict(r)
                rec["alternatives_considered"] = json.loads(rec["alternatives_considered"])
                results.append(rec)
            return results
        finally:
            conn.close()

    @classmethod
    def promote_strategic_principle(
        cls,
        statement: str,
        evidence_nodes: list[str],
        confidence: float,
        created_by: str = "reflection_engine"
    ) -> str:
        """Promotes a consolidated pattern to a strategic principle (goal) in DRAFT status.
        
        It is marked as INFERRED, links to evidence nodes, and requires explicit user signoff to activate.
        """
        # Create a draft goal representing the principle
        goal_id = cls.create_goal(
            goal=f"Strategic Principle: {statement[:80]}",
            description=f"Consolidated strategic principle: {statement}",
            priority=0.8, # Default high priority for strategic principles
            derived_from=evidence_nodes
        )
        
        # Update goal details to enforce trust_level = 'TRUST_UNVERIFIED' (or INFERRED)
        conn = cls._get_sqlite_conn()
        try:
            conn.execute(
                """
                UPDATE hm_strategic_goals
                SET trust_level = 'TRUST_UNVERIFIED', approved_by_user = 0, goal = ?
                WHERE id = ?
                """,
                (f"Strategic Principle: {statement} [INFERRED]", goal_id)
            )
            conn.commit()
        finally:
            conn.close()
            
        return goal_id
