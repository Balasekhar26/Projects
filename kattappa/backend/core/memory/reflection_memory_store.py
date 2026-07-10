"""
backend/core/memory/reflection_memory_store.py

Phase 3A: ReflectionMemoryStore — Adapter implementation for MemoryType.REFLECTION.

Acts as a facade/adapter wrapping backend/core/reflection_memory.py:
  - Direct mapping of save/retrieve/delete/forget calls to underlying routines.
  - Controls closed-loop reflection cycles, candidate proposals, and behavioral experiments.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from .schemas import MemoryRecord, MemoryType
from .memory_manager import IMemoryStore
from backend.core.reflection_memory import ReflectionMemory


class ReflectionMemoryStore(IMemoryStore):
    """IMemoryStore adapter wrapping the existing ReflectionMemory closed-loop engine."""

    memory_type: MemoryType = MemoryType.REFLECTION

    def __init__(self) -> None:
        """Initializes the ReflectionMemoryStore adapter."""
        # Ensure the schema is created on the legacy engine
        try:
            conn = ReflectionMemory._get_sqlite_conn()
            conn.close()
        except Exception:
            pass

    def close(self) -> None:
        """No-op because the wrapped engine manages its own connection pools."""
        pass

    # ------------------------------------------------------------------
    # Conversion Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_record(row: Dict[str, Any]) -> MemoryRecord:
        """Converts database row dictionary to MemoryRecord."""
        payload = {
            "category":           row["category"],
            "problem":            row["problem"],
            "cause":              row["cause"],
            "improvement":        row["improvement"],
            "evidence_count":     row["evidence_count"],
            "source_count":       row["source_count"],
            "source_window_days": row["source_window_days"],
            "status":             row["status"],
        }

        try:
            payload["sources"] = json.loads(row["sources_json"])
        except Exception:
            payload["sources"] = []

        try:
            payload["active_guardrails"] = json.loads(row["active_guardrails"])
        except Exception:
            payload["active_guardrails"] = []

        return MemoryRecord(
            memory_id=row["id"],
            memory_type=MemoryType.REFLECTION,
            timestamp=row["created_at"],
            source_agent="reflection_layer",
            confidence=row["confidence"],
            importance_score=row["confidence"],
            tags=[],
            payload=payload,
        )

    # ------------------------------------------------------------------
    # IMemoryStore: save
    # ------------------------------------------------------------------
    def save(self, record: MemoryRecord) -> None:
        if not isinstance(record, MemoryRecord):
            raise TypeError(f"Expected MemoryRecord; got {type(record)!r}")
        if record.memory_type is not MemoryType.REFLECTION:
            raise TypeError(
                f"ReflectionMemoryStore only accepts MemoryType.REFLECTION; "
                f"got {record.memory_type.value!r}"
            )

        payload = record.payload
        category = str(payload.get("category") or "RETRIEVAL").strip().upper()
        problem = str(payload.get("problem") or "unknown_problem").strip()
        cause = str(payload.get("cause") or "unknown_cause").strip()
        improvement = str(payload.get("improvement") or "unknown_improvement").strip()
        confidence = float(record.confidence)
        source_window_days = int(payload.get("source_window_days", 7))
        source_type = str(payload.get("source_type") or "conversation").strip()

        # Propose the reflection to the engine
        new_id = ReflectionMemory.propose_reflection(
            category=category,
            problem=problem,
            cause=cause,
            improvement=improvement,
            confidence=confidence,
            source_window_days=source_window_days,
            source_type=source_type,
        )
        
        # Override the record memory_id if the engine returned a merged match ID
        if new_id and record.memory_id != new_id:
            object.__setattr__(record, "memory_id", new_id)

    # ------------------------------------------------------------------
    # IMemoryStore: retrieve
    # ------------------------------------------------------------------
    def retrieve(self, query: Dict[str, Any], limit: int = 20) -> List[MemoryRecord]:
        conditions: List[str] = []
        params: List[Any] = []

        if "category" in query:
            conditions.append("category = ?")
            params.append(query["category"].strip().upper())

        if "status" in query:
            conditions.append("status = ?")
            params.append(query["status"].strip().lower())

        if "min_confidence" in query:
            conditions.append("confidence >= ?")
            params.append(float(query["min_confidence"]))

        if "since" in query:
            conditions.append("created_at >= ?")
            params.append(float(query["since"]))

        if "until" in query:
            conditions.append("created_at <= ?")
            params.append(float(query["until"]))

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"SELECT * FROM hm_reflections {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        records = []
        conn = ReflectionMemory._get_sqlite_conn()
        try:
            rows = conn.execute(sql, params).fetchall()
            for r in rows:
                records.append(self._row_to_record(dict(r)))
        finally:
            conn.close()

        return records

    # ------------------------------------------------------------------
    # IMemoryStore: forget
    # ------------------------------------------------------------------
    def forget(self, retention_threshold: float = 0.0) -> int:
        deleted = 0
        conn = ReflectionMemory._get_sqlite_conn()
        try:
            cur = conn.execute(
                "DELETE FROM hm_reflections WHERE status = 'pending' AND confidence <= ?",
                (retention_threshold,)
            )
            conn.commit()
            deleted = cur.rowcount
        except Exception:
            pass
        finally:
            conn.close()
        return deleted

    # ------------------------------------------------------------------
    # IMemoryStore: health_check
    # ------------------------------------------------------------------
    def health_check(self) -> Dict[str, Any]:
        total = 0
        pending = 0
        testing = 0
        accepted = 0
        conn = ReflectionMemory._get_sqlite_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM hm_reflections").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM hm_reflections WHERE status = 'pending'").fetchone()[0]
            testing = conn.execute("SELECT COUNT(*) FROM hm_reflections WHERE status = 'testing'").fetchone()[0]
            accepted = conn.execute("SELECT COUNT(*) FROM hm_reflections WHERE status = 'accepted'").fetchone()[0]
        except Exception:
            pass
        finally:
            conn.close()

        return {
            "status": "ok",
            "memory_type": MemoryType.REFLECTION.value,
            "total_reflections": total,
            "pending_reflections": pending,
            "testing_reflections": testing,
            "accepted_reflections": accepted,
        }

    # ------------------------------------------------------------------
    # Reflection-Specific APIs
    # ------------------------------------------------------------------
    def delete(self, memory_id: str) -> bool:
        conn = ReflectionMemory._get_sqlite_conn()
        try:
            cur = conn.execute("DELETE FROM hm_reflections WHERE id = ?", (memory_id,))
            conn.commit()
            deleted = cur.rowcount > 0
        except Exception:
            deleted = False
        finally:
            conn.close()
        return deleted

    def get(self, memory_id: str) -> Optional[MemoryRecord]:
        ref = ReflectionMemory.get_reflection(memory_id)
        if ref:
            return self._row_to_record(ref)
        return None

    def start_experiment(self, reflection_id: str, experiment_name: str, change_applied: str, metric_before: float) -> str:
        return ReflectionMemory.start_experiment(reflection_id, experiment_name, change_applied, metric_before)

    def conclude_experiment(self, intervention_id: str, metric_after: float, result: str) -> bool:
        return ReflectionMemory.conclude_experiment(intervention_id, metric_after, result)

    def __repr__(self) -> str:
        return "ReflectionMemoryStore(Adapter)"
