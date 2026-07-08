"""Tool Reliability Tracker — Phase K19.5.

Persists and calculates reliability indicators (success rates, latencies,
error types, and last failure times) for active system tools.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import Any, Dict, Optional

from backend.core.config import load_config
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


class ToolReliabilityTracker:
    """Manages tool invocation outcomes and latency records in SQLite."""

    _lock = threading.Lock()

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = config.sqlite_path.parent / "tool_reliability.db"
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS hm_tool_reliability (
                tool_name TEXT PRIMARY KEY,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                total_latency REAL DEFAULT 0.0,
                last_error TEXT,
                last_failure_at REAL,
                updated_at REAL NOT NULL
            );
            """
        )
        conn.commit()

    @classmethod
    def record_invocation(
        cls,
        tool_name: str,
        success: bool,
        latency: float,
        error: Optional[str] = None
    ) -> None:
        """Update tool statistics after a run."""
        clean_name = tool_name.strip().lower()
        now = time.time()
        
        with cls._lock:
            conn = cls._get_conn()
            try:
                row = conn.execute(
                    "SELECT tool_name FROM hm_tool_reliability WHERE tool_name = ?",
                    (clean_name,)
                ).fetchone()

                succ_inc = 1 if success else 0
                fail_inc = 0 if success else 1
                fail_ts = now if not success else None

                if row:
                    conn.execute(
                        """
                        UPDATE hm_tool_reliability
                        SET success_count = success_count + ?,
                            failure_count = failure_count + ?,
                            total_latency = total_latency + ?,
                            last_error = ?,
                            last_failure_at = COALESCE(?, last_failure_at),
                            updated_at = ?
                        WHERE tool_name = ?
                        """,
                        (succ_inc, fail_inc, latency, error, fail_ts, now, clean_name)
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO hm_tool_reliability
                            (tool_name, success_count, failure_count, total_latency, last_error, last_failure_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (clean_name, succ_inc, fail_inc, latency, error, fail_ts, now)
                    )
                conn.commit()
                log_event("tool_reliability_recorded", f"Recorded invocation for {clean_name}: success={success}")
            except Exception as e:
                conn.rollback()
                logger.error("ToolReliabilityTracker: failed to record metrics: %s", e)
            finally:
                conn.close()

    @classmethod
    def get_reliability(cls, tool_name: str) -> Dict[str, Any]:
        """Fetch reliability metrics for a tool."""
        clean_name = tool_name.strip().lower()
        
        with cls._lock:
            conn = cls._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM hm_tool_reliability WHERE tool_name = ?",
                    (clean_name,)
                ).fetchone()
                
                if not row:
                    return {
                        "tool_name": clean_name,
                        "success_rate": 1.0,
                        "average_latency": 0.0,
                        "confidence": 0.95,
                        "last_error": None
                    }

                total = row["success_count"] + row["failure_count"]
                succ_rate = row["success_count"] / total if total > 0 else 1.0
                avg_lat = row["total_latency"] / total if total > 0 else 0.0
                
                # Confidence falls based on failures
                confidence = max(0.0, succ_rate - (row["failure_count"] * 0.05))

                return {
                    "tool_name": clean_name,
                    "success_rate": round(succ_rate, 3),
                    "average_latency": round(avg_lat, 3),
                    "confidence": round(confidence, 3),
                    "last_error": row["last_error"]
                }
            finally:
                conn.close()

    @classmethod
    def get_all_reliability(cls) -> Dict[str, Dict[str, Any]]:
        """Retrieve reliability metrics for all recorded tools."""
        res = {}
        with cls._lock:
            conn = cls._get_conn()
            try:
                rows = conn.execute("SELECT tool_name FROM hm_tool_reliability").fetchall()
                for row in rows:
                    name = row["tool_name"]
                    res[name] = cls.get_reliability(name)
            finally:
                conn.close()
        return res

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute("DROP TABLE IF EXISTS hm_tool_reliability")
                conn.commit()
            finally:
                conn.close()
