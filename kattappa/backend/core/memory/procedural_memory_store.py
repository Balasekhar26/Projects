"""
backend/core/memory/procedural_memory_store.py

Phase 2C: ProceduralMemoryStore — Adapter implementation for MemoryType.PROCEDURAL.

Acts as a facade/adapter wrapping backend/core/procedural_memory.py:
  - Direct mapping of save/retrieve/delete/forget calls to underlying routines.
  - Enforces cryptographic HMAC-SHA256 signature verification and trust level gates.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from .schemas import MemoryRecord, MemoryType
from .memory_manager import IMemoryStore
from backend.core.procedural_memory import ProceduralMemory


class ProceduralMemoryStore(IMemoryStore):
    """IMemoryStore adapter wrapping the existing ProceduralMemory property graph engine."""

    memory_type: MemoryType = MemoryType.PROCEDURAL

    def __init__(self) -> None:
        """Initializes the ProceduralMemoryStore adapter."""
        # Ensure the schema is created on the legacy engine
        try:
            conn = ProceduralMemory._get_sqlite_conn()
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
            "skill_name":        row["skill_name"],
            "trigger_phrase":    row["trigger_phrase"],
            "steps_json":        row["steps_json"],
            "trust_level":       row["trust_level"],
            "procedure_version": row["procedure_version"],
            "signature":         row["signature"],
            "revoked":           bool(row["revoked"]),
            "failure_reason":    row.get("failure_reason"),
        }

        # Safe parsing steps json to payload for convenience
        try:
            payload["steps"] = json.loads(row["steps_json"])
        except Exception:
            payload["steps"] = []

        return MemoryRecord(
            memory_id=row["id"],
            memory_type=MemoryType.PROCEDURAL,
            timestamp=row["created_at"] or time.time(),
            source_agent="procedural_layer",
            confidence=1.0,
            importance_score=1.0,
            tags=[],
            payload=payload,
        )

    # ------------------------------------------------------------------
    # IMemoryStore: save
    # ------------------------------------------------------------------
    def save(self, record: MemoryRecord) -> None:
        if not isinstance(record, MemoryRecord):
            raise TypeError(f"Expected MemoryRecord; got {type(record)!r}")
        if record.memory_type is not MemoryType.PROCEDURAL:
            raise TypeError(
                f"ProceduralMemoryStore only accepts MemoryType.PROCEDURAL; "
                f"got {record.memory_type.value!r}"
            )

        payload = record.payload
        skill_name = str(payload.get("skill_name") or "unknown_skill").strip()
        trigger_phrase = payload.get("trigger_phrase")
        trigger_phrase = str(trigger_phrase).strip() if trigger_phrase else None
        
        steps = payload.get("steps")
        if steps is not None:
            if isinstance(steps, (list, dict)):
                steps_json = json.dumps(steps)
            else:
                steps_json = str(steps)
        else:
            steps_json = str(payload.get("steps_json") or "[]").strip()

        trust_level = str(payload.get("trust_level", "DRAFT")).upper()
        procedure_version = int(payload.get("procedure_version", 1))
        derived_from_nodes = payload.get("derived_from_nodes")
        failure_reason = payload.get("failure_reason")

        # Register via underlying ProceduralMemory class method
        ProceduralMemory.register_procedure(
            skill_name=skill_name,
            trigger_phrase=trigger_phrase,
            steps_json=steps_json,
            trust_level=trust_level,
            procedure_version=procedure_version,
            procedure_id=record.memory_id,
            derived_from_nodes=derived_from_nodes,
            failure_reason=failure_reason,
        )

    # ------------------------------------------------------------------
    # IMemoryStore: retrieve
    # ------------------------------------------------------------------
    def retrieve(self, query: Dict[str, Any], limit: int = 20) -> List[MemoryRecord]:
        conditions: List[str] = []
        params: List[Any] = []

        if "skill_name" in query:
            conditions.append("skill_name = ?")
            params.append(query["skill_name"])

        if "trust_level" in query:
            conditions.append("trust_level = ?")
            params.append(query["trust_level"])

        if "revoked" in query:
            conditions.append("revoked = ?")
            params.append(1 if query["revoked"] else 0)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"SELECT * FROM hm_procedures {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        records = []
        conn = ProceduralMemory._get_sqlite_conn()
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
        # Monotonic procedural rules are protected from memory decay/forgetting
        return 0

    # ------------------------------------------------------------------
    # IMemoryStore: health_check
    # ------------------------------------------------------------------
    def health_check(self) -> Dict[str, Any]:
        total = 0
        revoked = 0
        conn = ProceduralMemory._get_sqlite_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM hm_procedures").fetchone()[0]
            revoked = conn.execute("SELECT COUNT(*) FROM hm_procedures WHERE revoked = 1").fetchone()[0]
        except Exception:
            pass
        finally:
            conn.close()

        return {
            "status": "ok",
            "memory_type": MemoryType.PROCEDURAL.value,
            "total_procedures": total,
            "revoked_procedures": revoked,
        }

    # ------------------------------------------------------------------
    # Procedural-Specific APIs
    # ------------------------------------------------------------------
    def delete(self, memory_id: str) -> bool:
        return ProceduralMemory.delete_procedure(memory_id)

    def get(self, memory_id: str) -> Optional[MemoryRecord]:
        proc = ProceduralMemory.get_procedure(memory_id)
        if proc:
            return self._row_to_record(proc)
        return None

    def revoke(self, memory_id: str) -> bool:
        return ProceduralMemory.revoke_procedure(memory_id)

    def validate_execution(self, memory_id: str, trigger_source: str) -> Tuple[bool, str]:
        return ProceduralMemory.validate_and_gate(memory_id, trigger_source)

    def __repr__(self) -> str:
        return "ProceduralMemoryStore(Adapter)"
