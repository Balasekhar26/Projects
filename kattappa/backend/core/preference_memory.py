from __future__ import annotations
import json
import sqlite3
import time
import threading
from typing import Any, Dict, List, Optional
from backend.core.config import load_config


class PreferenceMemory:
    """Subsystem for managing user preferences with confidence score reinforcement and aging policies."""

    _lock = threading.Lock()
    _initialized = False

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.sqlite_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def _ensure_schema(cls) -> None:
        if cls._initialized:
            return
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_preferences (
                        pref_key TEXT PRIMARY KEY,
                        pref_value TEXT NOT NULL,
                        confidence REAL NOT NULL DEFAULT 1.0,
                        evidence_count INTEGER NOT NULL DEFAULT 1,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.commit()
                cls._initialized = True
            finally:
                conn.close()

    @classmethod
    def set_preference(cls, key: str, value: Any, confidence: float = 1.0) -> Dict[str, Any]:
        """Inserts or updates a user preference, and logs the change to the execution ledger."""
        cls._ensure_schema()
        now = time.time()
        val_json = json.dumps(value)

        with cls._lock:
            conn = cls._get_conn()
            try:
                row = conn.execute("SELECT evidence_count FROM user_preferences WHERE pref_key = ?", (key,)).fetchone()
                if row:
                    new_count = row["evidence_count"] + 1
                    conn.execute(
                        """
                        UPDATE user_preferences
                        SET pref_value = ?, confidence = ?, evidence_count = ?, updated_at = ?
                        WHERE pref_key = ?
                        """,
                        (val_json, float(confidence), new_count, now, key)
                    )
                else:
                    new_count = 1
                    conn.execute(
                        """
                        INSERT INTO user_preferences (pref_key, pref_value, confidence, evidence_count, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (key, val_json, float(confidence), 1, now, now)
                    )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        # Log change to ledger
        cls._log_ledger_event("set_preference", {"key": key, "value": value, "confidence": confidence, "count": new_count})
        return cls.get_preference(key)

    @classmethod
    def get_preference(cls, key: str) -> Optional[Dict[str, Any]]:
        """Retrieves a preference by key."""
        cls._ensure_schema()
        conn = cls._get_conn()
        try:
            row = conn.execute("SELECT * FROM user_preferences WHERE pref_key = ?", (key,)).fetchone()
            if not row:
                return None
            return {
                "pref_key": row["pref_key"],
                "pref_value": json.loads(row["pref_value"]),
                "confidence": row["confidence"],
                "evidence_count": row["evidence_count"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }
        finally:
            conn.close()

    @classmethod
    def delete_preference(cls, key: str) -> None:
        """Deletes a preference."""
        cls._ensure_schema()
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute("DELETE FROM user_preferences WHERE pref_key = ?", (key,))
                conn.commit()
            finally:
                conn.close()
        cls._log_ledger_event("delete_preference", {"key": key})

    @classmethod
    def list_preferences(cls) -> List[Dict[str, Any]]:
        """Lists all user preferences."""
        cls._ensure_schema()
        conn = cls._get_conn()
        try:
            rows = conn.execute("SELECT * FROM user_preferences ORDER BY pref_key ASC").fetchall()
            return [
                {
                    "pref_key": r["pref_key"],
                    "pref_value": json.loads(r["pref_value"]),
                    "confidence": r["confidence"],
                    "evidence_count": r["evidence_count"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"]
                }
                for r in rows
            ]
        finally:
            conn.close()

    @classmethod
    def reinforce_preference(cls, key: str, positive: bool) -> Optional[Dict[str, Any]]:
        """Reinforces confidence in a preference. If negative, decays confidence; evicts if below 0.2."""
        cls._ensure_schema()
        pref = cls.get_preference(key)
        if not pref:
            return None

        now = time.time()
        curr_conf = pref["confidence"]
        curr_count = pref["evidence_count"]

        if positive:
            # Increase confidence and evidence count
            new_conf = min(1.0, curr_conf + 0.1)
            new_count = curr_count + 1
            action = "reinforced"
        else:
            # Decays confidence by 20%
            new_conf = curr_conf * 0.8
            new_count = curr_count
            action = "decayed"

        if new_conf < 0.2:
            # Eviction policy
            cls.delete_preference(key)
            cls._log_ledger_event("evict_preference", {"key": key, "confidence": new_conf, "reason": "Confidence decayed below threshold (0.2)"})
            return None
        else:
            with cls._lock:
                conn = cls._get_conn()
                try:
                    conn.execute(
                        """
                        UPDATE user_preferences
                        SET confidence = ?, evidence_count = ?, updated_at = ?
                        WHERE pref_key = ?
                        """,
                        (new_conf, new_count, now, key)
                    )
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    raise e
                finally:
                    conn.close()

            cls._log_ledger_event("reinforce_preference", {"key": key, "action": action, "confidence": new_conf})
            return cls.get_preference(key)

    @classmethod
    def _log_ledger_event(cls, action_type: str, payload: Dict[str, Any]) -> None:
        """Helper to append log to the central KERNEL execution ledger."""
        try:
            from backend.core.cos.kernel import KERNEL
            from backend.core.ledger.models.event import LedgerEvent
            from backend.core.ledger.models.enums import EventType
            import uuid

            event = LedgerEvent(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                parent_event_ids=[],
                goal_id="user_preference_subsystem",
                session_id="user_preferences",
                correlation_id=payload.get("key", "global"),
                timestamp_utc=time.time(),
                actor="system",
                subsystem="preference_memory",
                event_type=EventType.MEMORY_STORED,
                payload={"action": action_type, "details": payload},
            )
            KERNEL.ledger.append(event)
        except Exception:
            pass

    @classmethod
    def reset(cls) -> None:
        """Resets preference memory table. For testing purposes only."""
        cls._ensure_schema()
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute("DROP TABLE IF EXISTS user_preferences")
                conn.commit()
                cls._initialized = False
            finally:
                conn.close()
