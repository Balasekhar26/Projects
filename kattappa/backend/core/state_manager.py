"""Cognitive State Manager — Phase K11.5.

Maintains and persists the global cognitive state of Kattappa (e.g., FOCUSED,
EXPLORING, LEARNING, REFLECTING, IDLE, EMERGENCY). State transitions dynamically
adjust attention weights, memory thresholds, and planning strategies.
"""
from __future__ import annotations

import sqlite3
import threading
from enum import Enum
from typing import Any, Dict, Optional

from backend.core.config import load_config
from backend.core.logger import log_event
from backend.core.blackboard import BLACKBOARD


class CognitiveState(str, Enum):
    FOCUSED = "FOCUSED"
    EXPLORING = "EXPLORING"
    LEARNING = "LEARNING"
    REFLECTING = "REFLECTING"
    IDLE = "IDLE"
    EMERGENCY = "EMERGENCY"


class CognitiveStateManager:
    """Manages global cognitive states and exposes dynamic parameters."""

    _lock = threading.Lock()

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = config.sqlite_path.parent / "cognitive_state.db"
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.commit()

    @classmethod
    def set_state(cls, state: CognitiveState) -> None:
        """Update the system state and publish to Blackboard."""
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO system_state (key, value) VALUES ('cognitive_state', ?)",
                    (state.value,),
                )
                conn.commit()
                log_event("state_manager_transition", f"Cognitive State -> {state.value}")
            finally:
                conn.close()

        # Notify blackboard
        try:
            BLACKBOARD.publish(
                publisher="state_manager",
                topic="state_change",
                payload={"previous_state": None, "current_state": state.value},
            )
        except Exception as e:
            log_event("state_manager_blackboard_error", str(e))

    @classmethod
    def get_state(cls) -> CognitiveState:
        """Get the current persisted state, defaulting to IDLE."""
        with cls._lock:
            conn = cls._get_conn()
            try:
                row = conn.execute("SELECT value FROM system_state WHERE key = 'cognitive_state'").fetchone()
                if row:
                    return CognitiveState(row["value"])
                return CognitiveState.IDLE
            except Exception:
                return CognitiveState.IDLE
            finally:
                conn.close()

    @classmethod
    def get_attention_weights(cls) -> Dict[str, float]:
        """Return composite formula weights adjusted dynamically by state."""
        state = cls.get_state()
        
        # Default weights: I(0.25) + U(0.20) + N(0.15) + R(0.25) + O(0.15)
        weights = {
            CognitiveState.FOCUSED: {
                "importance": 0.40,
                "urgency": 0.30,
                "novelty": 0.10,
                "risk": 0.10,
                "opportunity": 0.10,
            },
            CognitiveState.EXPLORING: {
                "importance": 0.10,
                "urgency": 0.10,
                "novelty": 0.50,
                "risk": 0.10,
                "opportunity": 0.20,
            },
            CognitiveState.LEARNING: {
                "importance": 0.20,
                "urgency": 0.10,
                "novelty": 0.20,
                "risk": 0.10,
                "opportunity": 0.40,
            },
            CognitiveState.REFLECTING: {
                "importance": 0.20,
                "urgency": 0.10,
                "novelty": 0.30,
                "risk": 0.10,
                "opportunity": 0.30,
            },
            CognitiveState.EMERGENCY: {
                "importance": 0.30,
                "urgency": 0.40,
                "novelty": 0.00,
                "risk": 0.30,
                "opportunity": 0.00,
            },
            CognitiveState.IDLE: {
                "importance": 0.25,
                "urgency": 0.20,
                "novelty": 0.15,
                "risk": 0.25,
                "opportunity": 0.15,
            },
        }
        return weights.get(state, weights[CognitiveState.IDLE])

    @classmethod
    def get_memory_thresholds(cls) -> Dict[str, float]:
        """Dynamically adjust confidence thresholds depending on cognitive state."""
        state = cls.get_state()
        
        # Base thresholds: Working=0.20, Episodic=0.45, Semantic=0.75, Procedural=0.90, KG=0.95
        base = {
            "working": 0.20,
            "episodic": 0.45,
            "semantic": 0.75,
            "procedural": 0.90,
            "knowledge_graph": 0.95,
        }
        
        if state == CognitiveState.EXPLORING:
            # Relaxes thresholds to invite new/creative concept connections
            return {
                "working": 0.15,
                "episodic": 0.35,
                "semantic": 0.60,
                "procedural": 0.80,
                "knowledge_graph": 0.85,
            }
        elif state == CognitiveState.EMERGENCY:
            # Tighten rules to minimize risk
            return {
                "working": 0.35,
                "episodic": 0.60,
                "semantic": 0.85,
                "procedural": 0.95,
                "knowledge_graph": 0.98,
            }
        return base

    @classmethod
    def reset(cls) -> None:
        """Reset the system state database (useful for tests)."""
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute("DROP TABLE IF EXISTS system_state")
                conn.commit()
            finally:
                conn.close()
