"""Agent Reputation Tracker — Phase K19.5.

Persists and tracks reputation indicators (accuracy, latency, failures, and
hallucination rates) for all active agents to enable optimal CEO routing.
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


class AgentReputationTracker:
    """Manages agent performance and reliability metrics in SQLite."""

    _lock = threading.Lock()

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = config.sqlite_path.parent / "agent_reputation.db"
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS hm_agent_reputation (
                agent_name TEXT PRIMARY KEY,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                total_latency REAL DEFAULT 0.0,
                hallucination_count INTEGER DEFAULT 0,
                updated_at REAL NOT NULL
            );
            """
        )
        conn.commit()

    @classmethod
    def record_execution(
        cls,
        agent_name: str,
        success: bool,
        latency: float,
        hallucination: bool = False
    ) -> None:
        """Log agent execution results to update running statistics."""
        clean_name = agent_name.strip().lower()
        now = time.time()
        
        with cls._lock:
            conn = cls._get_conn()
            try:
                row = conn.execute(
                    "SELECT agent_name FROM hm_agent_reputation WHERE agent_name = ?",
                    (clean_name,)
                ).fetchone()
                
                succ_inc = 1 if success else 0
                fail_inc = 0 if success else 1
                hal_inc = 1 if hallucination else 0

                if row:
                    conn.execute(
                        """
                        UPDATE hm_agent_reputation
                        SET success_count = success_count + ?,
                            failure_count = failure_count + ?,
                            total_latency = total_latency + ?,
                            hallucination_count = hallucination_count + ?,
                            updated_at = ?
                        WHERE agent_name = ?
                        """,
                        (succ_inc, fail_inc, latency, hal_inc, now, clean_name)
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO hm_agent_reputation
                            (agent_name, success_count, failure_count, total_latency, hallucination_count, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (clean_name, succ_inc, fail_inc, latency, hal_inc, now)
                    )
                conn.commit()
                log_event("agent_reputation_recorded", f"Recorded metrics for {clean_name}: success={success}")
            except Exception as e:
                conn.rollback()
                logger.error("AgentReputationTracker: failed to record metrics: %s", e)
            finally:
                conn.close()

    @classmethod
    def get_reputation(cls, agent_name: str) -> Dict[str, Any]:
        """Fetch compiled reputation stats for a specific agent."""
        clean_name = agent_name.strip().lower()
        
        with cls._lock:
            conn = cls._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM hm_agent_reputation WHERE agent_name = ?",
                    (clean_name,)
                ).fetchone()
                
                if not row:
                    return {
                        "agent_name": clean_name,
                        "success_rate": 1.0,
                        "average_latency": 0.0,
                        "hallucination_count": 0,
                        "confidence": 0.95
                    }

                total = row["success_count"] + row["failure_count"]
                succ_rate = row["success_count"] / total if total > 0 else 1.0
                avg_lat = row["total_latency"] / total if total > 0 else 0.0
                
                # Confidence degrades with failures and hallucinations
                confidence = max(0.0, succ_rate - (row["hallucination_count"] * 0.1))

                return {
                    "agent_name": clean_name,
                    "success_rate": round(succ_rate, 3),
                    "average_latency": round(avg_lat, 3),
                    "hallucination_count": row["hallucination_count"],
                    "confidence": round(confidence, 3)
                }
            finally:
                conn.close()

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute("DROP TABLE IF EXISTS hm_agent_reputation")
                conn.commit()
            finally:
                conn.close()
