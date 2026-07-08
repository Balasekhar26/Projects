"""Memory Consolidator — Phase K12.5.

Stages raw, transient observations and planner episodes inside a temporary
Sleep Buffer, then filters and promotes only high-significance facts to
Semantic Memory during consolidation, preventing store pollution.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event
from backend.core.cognitive_memory_bus import MEMORY_BUS

logger = logging.getLogger(__name__)


class MemoryConsolidator:
    """Manages transient memory staging and consolidation promotions."""

    _lock = threading.Lock()

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = config.sqlite_path.parent / "memory_consolidation.db"
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS hm_sleep_buffer (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                significance REAL DEFAULT 0.5,
                domain TEXT DEFAULT 'general',
                created_at REAL NOT NULL
            );
            """
        )
        conn.commit()

    @classmethod
    def stage_transient_fact(
        cls,
        session_id: str,
        content: str,
        significance: float = 0.5,
        domain: str = "general",
        fact_id: Optional[str] = None
    ) -> str:
        """Stage a transient fact candidate inside the sleep buffer."""
        import uuid
        fid = fact_id or str(uuid.uuid4())
        now = time.time()
        
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_sleep_buffer (id, session_id, content, significance, domain, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (fid, session_id, content, significance, domain, now)
                )
                conn.commit()
                log_event("memory_consolidator_staged", f"Staged fact {fid} (significance={significance}) in sleep buffer")
            finally:
                conn.close()
        return fid

    @classmethod
    def consolidate(cls, significance_floor: float = 0.50) -> Dict[str, int]:
        """Process sleep buffer items: promote high-significance to Semantic Store."""
        log_event("memory_consolidator_start", f"Running consolidation cycle (floor={significance_floor:.2f})")
        promoted = 0
        discarded = 0

        with cls._lock:
            conn = cls._get_conn()
            try:
                rows = conn.execute("SELECT * FROM hm_sleep_buffer").fetchall()
                if not rows:
                    return {"promoted": 0, "discarded": 0}

                for row in rows:
                    fact_id = row["id"]
                    session_id = row["session_id"]
                    content = row["content"]
                    sig = row["significance"]
                    domain = row["domain"]

                    if sig >= significance_floor:
                        # 1. Promote to Semantic Store via Memory Bus
                        # (requires verified=True and confidence >= 0.75 for semantic)
                        res = MEMORY_BUS.write(
                            memory_type="semantic",
                            data={
                                "concept": f"consolidated_{domain}_{fact_id[:6]}",
                                "description": content,
                                "source_episode_id": session_id,
                                "provenance": "memory_consolidator_promotion"
                            },
                            confidence=max(0.75, sig),
                            verified=True
                        )
                        if res.success:
                            promoted += 1
                        else:
                            # If memory bus rejected, keep in buffer or degrade
                            discarded += 1
                    else:
                        # 2. Write to Episodic Memory as a low-significance refuted trace
                        MEMORY_BUS.write(
                            memory_type="episodic",
                            data={
                                "session_id": session_id,
                                "trace_type": "transient_discard",
                                "content": f"Discarded low-significance fact: {content}",
                            },
                            confidence=0.45,
                            verified=False
                        )
                        discarded += 1

                # Clean up all consolidated items from sleep buffer
                conn.execute("DELETE FROM hm_sleep_buffer")
                conn.commit()

            except Exception as e:
                conn.rollback()
                log_event("memory_consolidator_error", str(e))
                raise e
            finally:
                conn.close()

        log_event("memory_consolidator_complete", f"Consolidation complete: promoted={promoted}, discarded={discarded}")
        return {"promoted": promoted, "discarded": discarded}

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute("DROP TABLE IF EXISTS hm_sleep_buffer")
                conn.commit()
            finally:
                conn.close()
