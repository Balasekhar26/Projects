"""
backend/core/memory/semantic_memory_store.py

Phase 2A: SemanticMemoryStore — Adapter implementation for MemoryType.SEMANTIC.

Acts as a facade/adapter wrapping backend/core/semantic_memory.py:
  - Preserves alias resolution, polarity checks, and trust boundaries.
  - save() delegates to SemanticMemory.upsert_node().
  - retrieve() delegates to SemanticMemory.recall() for text search, and
    performs direct SELECT queries on semantic_nodes for structured filtering.
  - health_check() counts active nodes in semantic_nodes.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .schemas import MemoryRecord, MemoryType
from .memory_manager import IMemoryStore
from backend.core.semantic_memory import SemanticMemory


class SemanticMemoryStore(IMemoryStore):
    """IMemoryStore adapter wrapping the existing SemanticMemory property graph engine."""

    memory_type: MemoryType = MemoryType.SEMANTIC

    def __init__(self) -> None:
        """Initializes the SemanticMemoryStore adapter."""
        # Ensure the schema is created on the legacy engine
        try:
            # Invoking schema initialization via its db helper
            conn = SemanticMemory._get_sqlite_conn()
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
    def _node_to_record(node: Dict[str, Any]) -> MemoryRecord:
        """Converts legacy/spec dictionary from SemanticMemory to MemoryRecord."""
        payload = {
            "node_id":                    node["node_id"],
            "title":                      node["title"],
            "content":                    node["content_raw"],
            "node_type":                  node["node_type"],
            "status":                     node["status"],
            "node_status":                node["node_status"],
            "valid_from":                 node["valid_from"],
            "valid_to":                   node["valid_to"],
            "last_verified_at":           node["last_verified_at"],
            "verification_interval_days": node["verification_interval_days"],
            "is_stale":                   node["is_stale"],
            "aliases":                    node.get("aliases", []),
            "sources":                    node.get("sources", []),
            "evidence":                   node.get("evidence", []),
            "skill":                      node.get("skill"),
            "contradicts_id":             node.get("contradicts_id"),
        }

        return MemoryRecord(
            memory_id=node["node_id"],
            memory_type=MemoryType.SEMANTIC,
            timestamp=node["created_at"],
            source_agent="semantic_layer",
            confidence=node["confidence_score"],
            importance_score=node["confidence_score"],
            tags=[],
            payload=payload,
        )

    # ------------------------------------------------------------------
    # IMemoryStore: save
    # ------------------------------------------------------------------
    def save(self, record: MemoryRecord) -> None:
        if not isinstance(record, MemoryRecord):
            raise TypeError(f"Expected MemoryRecord; got {type(record)!r}")
        if record.memory_type is not MemoryType.SEMANTIC:
            raise TypeError(
                f"SemanticMemoryStore only accepts MemoryType.SEMANTIC; "
                f"got {record.memory_type.value!r}"
            )

        payload = record.payload
        concept = str(payload.get("concept") or payload.get("title") or "").strip()
        description = str(payload.get("description") or payload.get("content") or payload.get("content_raw") or payload.get("text") or "").strip()
        
        if not concept and description:
            concept = description[:50]
        if not description and concept:
            description = concept

        source_episode_id = str(payload.get("source_episode_id") or payload.get("session_id") or "default_episode")
        provenance = payload.get("provenance")
        confidence = float(record.confidence)
        similarity_threshold = float(payload.get("similarity_threshold", 0.6))
        node_type = str(payload.get("node_type", "FACT")).upper()
        
        valid_from = payload.get("valid_from")
        valid_from = float(valid_from) if valid_from is not None else None
        valid_to = payload.get("valid_to")
        valid_to = float(valid_to) if valid_to is not None else None
        
        source_type = str(payload.get("source_type", "REFLECTION_CORROBORATED"))
        source_reference_hash = str(payload.get("source_reference_hash", "SHA256:default_reference_hash"))

        # Delegate to SemanticMemory.upsert_node
        SemanticMemory.upsert_node(
            concept=concept,
            description=description,
            source_episode_id=source_episode_id,
            provenance=provenance,
            confidence=confidence,
            similarity_threshold=similarity_threshold,
            node_type=node_type,
            valid_from=valid_from,
            valid_to=valid_to,
            source_type=source_type,
            source_reference_hash=source_reference_hash,
        )

    # ------------------------------------------------------------------
    # IMemoryStore: retrieve
    # ------------------------------------------------------------------
    def retrieve(self, query: Dict[str, Any], limit: int = 20) -> List[MemoryRecord]:
        text_query = query.get("text") or query.get("query")
        if text_query:
            # Delegate to SemanticMemory.recall
            relevance_floor = float(query.get("relevance_floor", 0.001))
            similarity_threshold = float(query.get("similarity_threshold", 1.2))
            
            hits = SemanticMemory.recall(
                query=text_query,
                limit=limit,
                relevance_floor=relevance_floor,
                similarity_threshold=similarity_threshold
            )
            records = []
            for h in hits:
                node = SemanticMemory.get_node(h["node_id"])
                if node:
                    records.append(self._node_to_record(node))
            return records

        # Structured query on semantic_nodes
        conditions: List[str] = ["status != 'DEPRECATED'"]
        params: List[Any] = []

        if "node_type" in query:
            conditions.append("node_type = ?")
            params.append(query["node_type"])

        if "status" in query:
            # Override default active filter if requesting archived/deprecated explicitly
            conditions = ["status = ?"]
            params = [query["status"]]

        if "min_confidence" in query:
            conditions.append("confidence_score >= ?")
            params.append(float(query["min_confidence"]))

        if "since" in query:
            conditions.append("created_at >= ?")
            params.append(float(query["since"]))

        if "until" in query:
            conditions.append("created_at <= ?")
            params.append(float(query["until"]))

        where = " AND ".join(conditions)
        sql = f"SELECT node_id FROM semantic_nodes WHERE {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        records = []
        conn = SemanticMemory._get_sqlite_conn()
        try:
            rows = conn.execute(sql, params).fetchall()
            for r in rows:
                node = SemanticMemory.get_node(r["node_id"])
                if node:
                    records.append(self._node_to_record(node))
        finally:
            conn.close()

        return records

    # ------------------------------------------------------------------
    # IMemoryStore: forget
    # ------------------------------------------------------------------
    def forget(self, retention_threshold: float = 0.0) -> int:
        deleted = 0
        conn = SemanticMemory._get_sqlite_conn()
        try:
            # Query candidate IDs
            rows = conn.execute(
                "SELECT node_id FROM semantic_nodes WHERE status != 'PINNED' AND confidence_score <= ?",
                (retention_threshold,)
            ).fetchall()
            
            for r in rows:
                node_id = r["node_id"]
                # Soft delete by marking deprecated
                conn.execute(
                    "UPDATE semantic_nodes SET status = 'DEPRECATED', updated_at = ? WHERE node_id = ?",
                    (time.time(), node_id)
                )
                deleted += 1
            conn.commit()
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
        active = 0
        conn = SemanticMemory._get_sqlite_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM semantic_nodes").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM semantic_nodes WHERE status = 'ACTIVE'").fetchone()[0]
        except Exception:
            pass
        finally:
            conn.close()

        return {
            "status": "ok",
            "memory_type": MemoryType.SEMANTIC.value,
            "total_records": total,
            "active_records": active,
        }

    # ------------------------------------------------------------------
    # Semantic-Specific APIs
    # ------------------------------------------------------------------
    def delete(self, memory_id: str) -> bool:
        """Soft deletes by marking deprecated, in alignment with SemanticMemory CRUD."""
        conn = SemanticMemory._get_sqlite_conn()
        try:
            cur = conn.execute(
                "UPDATE semantic_nodes SET status = 'DEPRECATED', updated_at = ? WHERE node_id = ?",
                (time.time(), memory_id)
            )
            conn.commit()
            deleted = cur.rowcount > 0
        except Exception:
            deleted = False
        finally:
            conn.close()
        return deleted

    def get(self, memory_id: str) -> Optional[MemoryRecord]:
        node = SemanticMemory.get_node(memory_id)
        if node:
            return self._node_to_record(node)
        return None

    def __repr__(self) -> str:
        return "SemanticMemoryStore(Adapter)"
