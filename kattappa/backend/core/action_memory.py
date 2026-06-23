"""
action_memory.py
================
Action Memory V1 - Experience ledger for Kattappa AI OS.

Position in the cognitive stack
---------------------------------
  Action Broker
       v  (post-execution write, after DVE verification)
  Action Memory   <- this module
       ^  (read queries)
  Reflection Agent
  Strategy Agent
  Planner (pre-execution context)

Responsibilities
----------------
* Record every completed, DVE-verified action as a structured experience
* Expose a clean retrieval API: recent, by success, by failure, by similarity, by agent
* Provide per-agent statistics for Strategy and Simulation engines
* Persist to SQLite (WAL mode) - safe for concurrent readers, single writer

Storage
-------
  action_memory.db
    action_history  - one row per completed action
    action_tags     - many-to-one tags for faceted retrieval

Authority Rules
---------------
[OK]  Write verified action records (called by Action Broker only)
[OK]  Read / query action history (open to all advisory consumers)
[OK]  Compute per-agent statistics

[NO]  Execute any action
[NO]  Modify capability registry or policy engine
[NO]  Approve or reject actions
[NO]  Bypass Action Broker
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


# -- DB path -------------------------------------------------------------------

def _db_path() -> Path:
    p = runtime_data_root() / "backend" / "data" / "action_memory.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# -- Thread-safe write lock (mirrors human_memory.py pattern) ------------------
_WRITE_LOCK = threading.Lock()


# -- Domain model --------------------------------------------------------------

@dataclass
class ActionRecord:
    """
    A single completed-action experience entry.
    All fields are serialisable to/from SQLite.
    """
    action_id: str
    agent: str
    action: str
    reason: str
    expected_outcome: str
    actual_outcome: str
    success: bool
    failure: bool
    duration_ms: int
    confidence_score: float
    rollback_executed: bool
    timestamp: str                      # ISO-8601 UTC
    timestamp_unix: float
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["success"] = self.success
        d["failure"] = self.failure
        d["rollback_executed"] = self.rollback_executed
        d["outcome"] = self.actual_outcome
        return d

    @classmethod
    def from_row(cls, row: sqlite3.Row, tags: list[str] | None = None) -> "ActionRecord":
        success = bool(row["success"])
        failure = bool(row["failure"]) if "failure" in row.keys() else not success
        return cls(
            action_id=row["action_id"],
            agent=row["agent"],
            action=row["action"],
            reason=row["reason"],
            expected_outcome=row["expected_outcome"],
            actual_outcome=row["actual_outcome"],
            success=success,
            failure=failure,
            duration_ms=row["duration_ms"],
            confidence_score=row["confidence_score"],
            rollback_executed=bool(row["rollback_executed"]),
            timestamp=row["timestamp"],
            timestamp_unix=row["timestamp_unix"],
            tags=tags or [],
        )


@dataclass
class AgentStatistics:
    """Per-agent aggregated performance statistics."""
    agent: str
    total_actions: int
    success_count: int
    failure_count: int
    rollback_count: int
    success_rate: float
    avg_duration_ms: float
    avg_confidence: float
    rollback_rate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ==============================================================================
# Schema Management
# ==============================================================================

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS action_history (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id         TEXT NOT NULL UNIQUE,
    agent             TEXT NOT NULL,
    action            TEXT NOT NULL,
    reason            TEXT NOT NULL DEFAULT '',
    expected_outcome  TEXT NOT NULL DEFAULT '',
    actual_outcome    TEXT NOT NULL DEFAULT '',
    success           INTEGER NOT NULL DEFAULT 1,   -- 1=success, 0=failure
    failure           INTEGER NOT NULL DEFAULT 0,   -- derived inverse, stored for fast filters
    duration_ms       INTEGER NOT NULL DEFAULT 0,
    confidence_score  REAL    NOT NULL DEFAULT 0.0,
    rollback_executed INTEGER NOT NULL DEFAULT 0,   -- 1=yes, 0=no
    timestamp         TEXT    NOT NULL,              -- ISO-8601
    timestamp_unix    REAL    NOT NULL               -- Unix epoch for range queries
);

CREATE INDEX IF NOT EXISTS idx_ah_agent   ON action_history(agent);
CREATE INDEX IF NOT EXISTS idx_ah_action  ON action_history(action);
CREATE INDEX IF NOT EXISTS idx_ah_success ON action_history(success);
CREATE INDEX IF NOT EXISTS idx_ah_failure ON action_history(failure);
CREATE INDEX IF NOT EXISTS idx_ah_ts_unix ON action_history(timestamp_unix);

CREATE TABLE IF NOT EXISTS action_tags (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id TEXT NOT NULL,
    tag       TEXT NOT NULL,
    FOREIGN KEY (action_id) REFERENCES action_history(action_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_at_tag       ON action_tags(tag);
CREATE INDEX IF NOT EXISTS idx_at_action_id ON action_tags(action_id);
"""


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply additive migrations for older local action_memory.db files."""
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(action_history)").fetchall()
    }
    if "failure" not in columns:
        conn.execute(
            "ALTER TABLE action_history ADD COLUMN failure INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute(
            "UPDATE action_history SET failure = CASE WHEN success=1 THEN 0 ELSE 1 END"
        )
        conn.commit()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    _migrate_schema(conn)
    return conn


def _ensure_schema() -> None:
    """Ensure tables exist. Safe to call multiple times."""
    conn = _connect()
    conn.close()


def _normalise_timestamp(timestamp: str | None = None) -> tuple[str, float]:
    if not timestamp:
        now = datetime.now(timezone.utc)
        return now.isoformat().replace("+00:00", "Z"), now.timestamp()

    raw = timestamp.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z"), parsed.timestamp()


def _clean_tags(tags: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags or []:
        clean = str(tag).strip().lower()
        if clean and clean not in seen:
            seen.add(clean)
            cleaned.append(clean)
    return cleaned


# ==============================================================================
# ActionMemory - Core Storage + Retrieval
# ==============================================================================

class ActionMemory:
    """
    Experience ledger. Single-writer, multi-reader, WAL-mode SQLite.

    Write path: Action Broker calls `record()` after DVE post-execution.
    Read path: Reflection / Strategy / Planner call query methods freely.
    """

    # --- Write ----------------------------------------------------------------

    @classmethod
    def record(
        cls,
        agent: str,
        action: str,
        reason: str = "",
        expected_outcome: str = "",
        actual_outcome: str = "",
        success: bool = True,
        duration_ms: int = 0,
        confidence_score: float = 0.0,
        rollback_executed: bool = False,
        tags: list[str] | None = None,
        action_id: str | None = None,
        timestamp: str | None = None,
    ) -> str:
        """
        Insert one action experience record.
        Returns the action_id of the inserted record.
        Duplicate action_ids are rejected so retries cannot corrupt the ledger.
        """
        _ensure_schema()
        if not str(agent).strip():
            raise ValueError("agent is required")
        if not str(action).strip():
            raise ValueError("action is required")
        if duration_ms < 0:
            raise ValueError("duration_ms must be greater than or equal to 0")
        if not 0.0 <= float(confidence_score) <= 1.0:
            raise ValueError("confidence_score must be between 0.0 and 1.0")

        aid = action_id or f"act_{uuid.uuid4().hex[:12]}"
        if not aid.strip():
            raise ValueError("action_id cannot be blank")
        recorded_at, recorded_unix = _normalise_timestamp(timestamp)
        _tags = _clean_tags(tags)
        failure = not bool(success)

        with _WRITE_LOCK:
            conn = _connect()
            try:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO action_history
                      (action_id, agent, action, reason, expected_outcome,
                       actual_outcome, success, failure, duration_ms, confidence_score,
                       rollback_executed, timestamp, timestamp_unix)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        aid, agent, action, reason, expected_outcome,
                        actual_outcome, int(success), int(failure), duration_ms,
                        confidence_score, int(rollback_executed),
                        recorded_at, recorded_unix,
                    ),
                )
                if cursor.rowcount == 0:
                    raise ValueError(f"action_id already exists: {aid}")
                for tag in _tags:
                    conn.execute(
                        "INSERT INTO action_tags (action_id, tag) VALUES (?,?)",
                        (aid, tag),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return aid

    @classmethod
    def update_outcome(
        cls,
        action_id: str,
        actual_outcome: str | None = None,
        success: bool | None = None,
        rollback_executed: bool | None = None,
        confidence_score: float | None = None,
        duration_ms: int | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        """Update the outcome of an already-recorded action (e.g. after rollback)."""
        _ensure_schema()
        if confidence_score is not None and not 0.0 <= float(confidence_score) <= 1.0:
            raise ValueError("confidence_score must be between 0.0 and 1.0")
        if duration_ms is not None and duration_ms < 0:
            raise ValueError("duration_ms must be greater than or equal to 0")

        updates: list[str] = []
        params: list[Any] = []
        if actual_outcome is not None:
            updates.append("actual_outcome=?")
            params.append(actual_outcome)
        if success is not None:
            updates.append("success=?")
            params.append(int(success))
            updates.append("failure=?")
            params.append(int(not success))
        if rollback_executed is not None:
            updates.append("rollback_executed=?")
            params.append(int(rollback_executed))
        if confidence_score is not None:
            updates.append("confidence_score=?")
            params.append(confidence_score)
        if duration_ms is not None:
            updates.append("duration_ms=?")
            params.append(duration_ms)

        with _WRITE_LOCK:
            conn = _connect()
            try:
                changed = 0
                if updates:
                    cursor = conn.execute(
                        f"UPDATE action_history SET {', '.join(updates)} WHERE action_id=?",
                        (*params, action_id),
                    )
                    changed = cursor.rowcount
                if tags is not None:
                    exists = conn.execute(
                        "SELECT 1 FROM action_history WHERE action_id=?",
                        (action_id,),
                    ).fetchone()
                    if not exists:
                        conn.rollback()
                        return False
                    conn.execute("DELETE FROM action_tags WHERE action_id=?", (action_id,))
                    for tag in _clean_tags(tags):
                        conn.execute(
                            "INSERT INTO action_tags (action_id, tag) VALUES (?,?)",
                            (action_id, tag),
                        )
                    changed = max(changed, 1)
                conn.commit()
                return changed > 0
            finally:
                conn.close()

    # --- Retrieval API --------------------------------------------------------

    @classmethod
    def get_action(cls, action_id: str) -> ActionRecord | None:
        """Return one action record by id."""
        _ensure_schema()
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM action_history WHERE action_id=?",
                (action_id,),
            ).fetchone()
            return cls._hydrate(conn, row) if row else None
        finally:
            conn.close()

    @classmethod
    def get_recent_actions(cls, limit: int = 100) -> list[ActionRecord]:
        """Returns the most recent N verified actions, newest first."""
        _ensure_schema()
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM action_history ORDER BY timestamp_unix DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [cls._hydrate(conn, row) for row in rows]
        finally:
            conn.close()

    @classmethod
    def get_successful_actions(
        cls,
        action_type: str | None = None,
        agent: str | None = None,
        limit: int = 100,
    ) -> list[ActionRecord]:
        """Returns successfully completed actions, optionally filtered by type and/or agent."""
        _ensure_schema()
        sql = "SELECT * FROM action_history WHERE success=1"
        params: list[Any] = []
        if action_type:
            sql += " AND action=?"
            params.append(action_type)
        if agent:
            sql += " AND agent=?"
            params.append(agent)
        sql += " ORDER BY timestamp_unix DESC LIMIT ?"
        params.append(limit)
        conn = _connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [cls._hydrate(conn, row) for row in rows]
        finally:
            conn.close()

    @classmethod
    def get_failed_actions(
        cls,
        action_type: str | None = None,
        agent: str | None = None,
        limit: int = 100,
    ) -> list[ActionRecord]:
        """Returns failed actions, optionally filtered by type and/or agent."""
        _ensure_schema()
        sql = "SELECT * FROM action_history WHERE success=0"
        params: list[Any] = []
        if action_type:
            sql += " AND action=?"
            params.append(action_type)
        if agent:
            sql += " AND agent=?"
            params.append(agent)
        sql += " ORDER BY timestamp_unix DESC LIMIT ?"
        params.append(limit)
        conn = _connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [cls._hydrate(conn, row) for row in rows]
        finally:
            conn.close()

    @classmethod
    def find_similar_actions(
        cls,
        action: str,
        agent: str | None = None,
        limit: int = 50,
    ) -> list[ActionRecord]:
        """
        Returns previous executions of the same action type.
        Optionally restricted to a specific agent.
        Useful for Simulation Engine pre-execution priors.
        """
        _ensure_schema()
        sql = "SELECT * FROM action_history WHERE action=?"
        params: list[Any] = [action]
        if agent:
            sql += " AND agent=?"
            params.append(agent)
        sql += " ORDER BY timestamp_unix DESC LIMIT ?"
        params.append(limit)
        conn = _connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [cls._hydrate(conn, row) for row in rows]
        finally:
            conn.close()

    @classmethod
    def get_by_tag(cls, tag: str, limit: int = 50) -> list[ActionRecord]:
        """Returns actions that carry a specific tag."""
        _ensure_schema()
        sql = """
            SELECT ah.* FROM action_history ah
            INNER JOIN action_tags at ON ah.action_id = at.action_id
            WHERE at.tag = ?
            ORDER BY ah.timestamp_unix DESC LIMIT ?
        """
        conn = _connect()
        try:
            rows = conn.execute(sql, (tag.strip().lower(), limit)).fetchall()
            return [cls._hydrate(conn, row) for row in rows]
        finally:
            conn.close()

    @classmethod
    def get_by_time_range(
        cls,
        since_unix: float,
        until_unix: float | None = None,
        limit: int = 500,
    ) -> list[ActionRecord]:
        """Returns actions within a Unix timestamp window."""
        _ensure_schema()
        sql = "SELECT * FROM action_history WHERE timestamp_unix >= ?"
        params: list[Any] = [since_unix]
        if until_unix is not None:
            sql += " AND timestamp_unix <= ?"
            params.append(until_unix)
        sql += " ORDER BY timestamp_unix ASC LIMIT ?"
        params.append(limit)
        conn = _connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [cls._hydrate(conn, row) for row in rows]
        finally:
            conn.close()

    # --- Agent Statistics -----------------------------------------------------

    @classmethod
    def get_agent_statistics(cls, agent: str) -> AgentStatistics:
        """
        Returns aggregated performance statistics for a single agent.
        Used by Strategy Agent for reliability scoring and by Simulation Engine
        for prior probability estimation.
        """
        _ensure_schema()
        conn = _connect()
        try:
            row = conn.execute(
                """
                SELECT
                    COUNT(*)                        AS total,
                    SUM(success)                    AS successes,
                    SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures,
                    SUM(rollback_executed)          AS rollbacks,
                    AVG(duration_ms)                AS avg_dur,
                    AVG(confidence_score)           AS avg_conf
                FROM action_history
                WHERE agent = ?
                """,
                (agent,)
            ).fetchone()

            total = row["total"] or 0
            successes = row["successes"] or 0
            failures = row["failures"] or 0
            rollbacks = row["rollbacks"] or 0
            avg_dur = float(row["avg_dur"] or 0.0)
            avg_conf = float(row["avg_conf"] or 0.0)

            return AgentStatistics(
                agent=agent,
                total_actions=total,
                success_count=successes,
                failure_count=failures,
                rollback_count=rollbacks,
                success_rate=round(successes / total, 4) if total > 0 else 0.0,
                avg_duration_ms=round(avg_dur, 1),
                avg_confidence=round(avg_conf, 4),
                rollback_rate=round(rollbacks / total, 4) if total > 0 else 0.0,
            )
        finally:
            conn.close()

    @classmethod
    def get_all_agent_statistics(cls) -> dict[str, AgentStatistics]:
        """Returns statistics for every agent that has records."""
        _ensure_schema()
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    agent,
                    COUNT(*)                        AS total,
                    SUM(success)                    AS successes,
                    SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures,
                    SUM(rollback_executed)          AS rollbacks,
                    AVG(duration_ms)                AS avg_dur,
                    AVG(confidence_score)           AS avg_conf
                FROM action_history
                GROUP BY agent
                """
            ).fetchall()
            result = {}
            for row in rows:
                agent = row["agent"]
                total = row["total"] or 0
                successes = row["successes"] or 0
                rollbacks = row["rollbacks"] or 0
                result[agent] = AgentStatistics(
                    agent=agent,
                    total_actions=total,
                    success_count=successes,
                    failure_count=row["failures"] or 0,
                    rollback_count=rollbacks,
                    success_rate=round(successes / total, 4) if total > 0 else 0.0,
                    avg_duration_ms=round(float(row["avg_dur"] or 0), 1),
                    avg_confidence=round(float(row["avg_conf"] or 0), 4),
                    rollback_rate=round(rollbacks / total, 4) if total > 0 else 0.0,
                )
            return result
        finally:
            conn.close()

    @classmethod
    def get_action_type_statistics(cls, action: str) -> dict[str, Any]:
        """
        Returns statistics for a specific action type across all agents.
        Useful for Simulation Engine success probability estimation.
        """
        _ensure_schema()
        conn = _connect()
        try:
            row = conn.execute(
                """
                SELECT
                    COUNT(*)              AS total,
                    SUM(success)          AS successes,
                    SUM(failure)          AS failures,
                    AVG(duration_ms)      AS avg_dur,
                    AVG(confidence_score) AS avg_conf,
                    SUM(rollback_executed) AS rollbacks
                FROM action_history
                WHERE action = ?
                """,
                (action,)
            ).fetchone()
            total = row["total"] or 0
            successes = row["successes"] or 0
            return {
                "action": action,
                "total_executions": total,
                "success_count": successes,
                "failure_count": row["failures"] or 0,
                "success_rate": round(successes / total, 4) if total > 0 else 0.0,
                "avg_duration_ms": round(float(row["avg_dur"] or 0), 1),
                "avg_confidence": round(float(row["avg_conf"] or 0), 4),
                "rollback_count": row["rollbacks"] or 0,
            }
        finally:
            conn.close()

    @classmethod
    def get_top_failing_actions(cls, limit: int = 10) -> list[dict[str, Any]]:
        """Returns action types ranked by failure count - useful for Reflection."""
        _ensure_schema()
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT action,
                       COUNT(*) AS total,
                       SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures,
                       ROUND(AVG(CASE WHEN success=0 THEN 1.0 ELSE 0.0 END), 4) AS failure_rate
                FROM action_history
                GROUP BY action
                HAVING failures > 0
                ORDER BY failure_rate DESC, failures DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()
            return [
                {
                    "action": r["action"],
                    "total": r["total"],
                    "failures": r["failures"],
                    "failure_rate": r["failure_rate"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    @classmethod
    def count_total(cls) -> int:
        """Returns total number of records in the ledger."""
        _ensure_schema()
        conn = _connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM action_history").fetchone()[0]
        finally:
            conn.close()

    @classmethod
    def purge_old_records(cls, keep_latest: int = 10000) -> int:
        """
        Retain only the most recent `keep_latest` records.
        Returns number of rows deleted. Safe to call on a schedule.
        """
        _ensure_schema()
        with _WRITE_LOCK:
            conn = _connect()
            try:
                total = conn.execute("SELECT COUNT(*) FROM action_history").fetchone()[0]
                if total <= keep_latest:
                    return 0
                cutoff = conn.execute(
                    "SELECT timestamp_unix FROM action_history ORDER BY timestamp_unix DESC LIMIT 1 OFFSET ?",
                    (keep_latest - 1,)
                ).fetchone()
                if cutoff is None:
                    return 0
                conn.execute(
                    "DELETE FROM action_history WHERE timestamp_unix < ?",
                    (cutoff["timestamp_unix"],)
                )
                deleted = total - conn.execute("SELECT COUNT(*) FROM action_history").fetchone()[0]
                conn.commit()
                return deleted
            finally:
                conn.close()

    # --- Internal helpers -----------------------------------------------------

    @staticmethod
    def _hydrate(conn: sqlite3.Connection, row: sqlite3.Row) -> ActionRecord:
        """Build an ActionRecord from a DB row, fetching its tags."""
        tags_rows = conn.execute(
            "SELECT tag FROM action_tags WHERE action_id=? ORDER BY id ASC",
            (row["action_id"],)
        ).fetchall()
        tags = [t["tag"] for t in tags_rows]
        return ActionRecord.from_row(row, tags)


# ==============================================================================
# Broker Integration Helper
# ==============================================================================

def record_from_broker(
    agent_name: str,
    action: str,
    params: dict[str, Any],
    execution_result: Any,
    dve_result: dict[str, Any],
    duration_ms: int,
    state: dict[str, Any],
) -> str | None:
    """
    Called by ActionBroker after DVE post-execution.
    Extracts relevant fields and writes to ActionMemory.
    Non-blocking - any exception is swallowed to protect broker flow.

    Returns action_id on success, None on failure.
    """
    try:
        success = _infer_success(execution_result, dve_result)
        actual_outcome = _summarise_result(execution_result)
        expected_outcome = params.get("expected_outcome", "") or params.get("reason", "")
        reason = params.get("reason", "") or state.get("user_input", "")[:120]
        confidence = float(dve_result.get("confidence_score", 0.0)) if isinstance(dve_result, dict) else 0.0
        rollback_executed = bool(
            isinstance(dve_result, dict) and
            (dve_result.get("recovery_actions") or dve_result.get("recovery_action"))
        )
        tags = _build_tags(agent_name, action, params, success)

        return ActionMemory.record(
            agent=agent_name,
            action=action,
            reason=reason[:500],
            expected_outcome=expected_outcome[:500],
            actual_outcome=actual_outcome[:500],
            success=success,
            duration_ms=max(0, duration_ms),
            confidence_score=max(0.0, min(1.0, confidence)),
            rollback_executed=rollback_executed,
            tags=tags,
        )
    except Exception:
        return None


def _infer_success(execution_result: Any, dve_result: dict[str, Any]) -> bool:
    """Determine success from execution result and DVE outcome."""
    if isinstance(dve_result, dict):
        outcome = dve_result.get("outcome", "")
        if outcome == "FAILURE":
            return False
        if outcome == "SUCCESS":
            return True
    if isinstance(execution_result, dict):
        return bool(execution_result.get("success", True))
    if isinstance(execution_result, str):
        return "error" not in execution_result.lower() and "fail" not in execution_result.lower()
    return True


def _summarise_result(execution_result: Any) -> str:
    """Extract a readable outcome string from the execution result."""
    if isinstance(execution_result, dict):
        if "message" in execution_result:
            return str(execution_result["message"])[:200]
        if "error" in execution_result:
            return f"ERROR: {execution_result['error']}"[:200]
        if "content" in execution_result:
            content = str(execution_result["content"])
            return content[:200] + ("..." if len(content) > 200 else "")
        return str(execution_result)[:200]
    return str(execution_result)[:200]


def _build_tags(agent: str, action: str, params: dict[str, Any], success: bool) -> list[str]:
    """Produce faceted tags for fast retrieval."""
    tags = [agent.lower(), action.lower().replace("_", "-")]
    if not success:
        tags.append("failed")
    if params.get("url"):
        tags.append("network")
    if action.startswith("BROWSER_"):
        tags.append("browser")
    if action.startswith("DESKTOP_"):
        tags.append("desktop")
    if action.startswith("VOICE_"):
        tags.append("voice")
    if action.startswith("FILE_") or action in ("CREATE_FILE", "WRITE_FILE", "READ_FILE", "DELETE_FILE"):
        tags.append("file-io")
    return tags
