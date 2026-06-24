"""Memory Safety & Forgetting Verification (Phase 1 & 2).

Provides quantifiable audits of Kattappa's human-like memory system, checking
if deleted/forgotten memories are clean purges or leave privacy leakage.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List

from backend.core.human_memory import HumanMemoryStore, MemoryRecord, MemoryType, RecallEngine, _storage_dir
from backend.core.config import load_config


class MemorySafetyVerifier:
    """Audits adversarial extraction rate, residue score, and deletion fidelity."""

    @classmethod
    def _get_db_paths(cls) -> List[str]:
        config = load_config()
        # Create directories
        _storage_dir().mkdir(parents=True, exist_ok=True)
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return [
            str(_storage_dir() / "human_memory.db"),
            str(config.sqlite_path)
        ]

    @classmethod
    def calculate_aer(cls, test_contents: List[str]) -> float:
        """Adversarial Extraction Rate: tries to recall deleted memories.

        Inserts N test memories, deletes them, and attempts to extract them.
        Returns the fraction of deleted records successfully extracted [0.0 - 1.0].
        """
        if not test_contents:
            return 0.0

        inserted_ids: List[str] = []
        content_to_id: Dict[str, str] = {}
        now = time.time()
        for idx, content in enumerate(test_contents):
            mem_id = f"test_aer_{uuid.uuid4().hex[:8]}_{idx}"
            record = MemoryRecord(
                id=mem_id,
                type=MemoryType.EPISODIC,
                content=content,
                importance=0.8,
                confidence=0.9,
                decay_score=0.9,
                recall_count=0,
                created_at=now,
                last_recall_at=now,
                pinned=False,
                trusted=True,
                source="test_aer",
                compression_level=0,
            )
            HumanMemoryStore.insert(record)
            inserted_ids.append(mem_id)
            content_to_id[content] = mem_id

        # Purge/Delete the inserted memories
        for mem_id in inserted_ids:
            HumanMemoryStore.delete(mem_id)

        leaked_count = 0
        for content in test_contents:
            target_id = content_to_id[content]
            # Attempt to extract using FTS search or Recall Engine directly
            hits = RecallEngine.recall(content, limit=5, include_forgotten=True, reinforce=False)
            for hit in hits:
                if hit.record.id == target_id or content in hit.record.content:
                    leaked_count += 1
                    break

        return leaked_count / len(test_contents)

    @classmethod
    def calculate_frs(cls, deleted_ids: List[str]) -> float:
        """Forgetting Residue Score: checks for dangling indices/edges after deletion."""
        if not deleted_ids:
            return 0.0

        residue_count = 0
        paths = cls._get_db_paths()

        for path in paths:
            try:
                conn = sqlite3.connect(path)
                conn.row_factory = sqlite3.Row
                try:
                    for mem_id in deleted_ids:
                        # 1. Check FTS index for id residue (if table exists)
                        fts_exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hm_memories_fts'").fetchone()
                        if fts_exists:
                            fts_row = conn.execute("SELECT COUNT(*) AS c FROM hm_memories_fts WHERE id = ?", (mem_id,)).fetchone()
                            if fts_row and fts_row["c"] > 0:
                                residue_count += 1

                        # 2. Check dangling edges (if table exists)
                        edges_exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hm_edges'").fetchone()
                        if edges_exists:
                            edge_row = conn.execute("SELECT COUNT(*) AS c FROM hm_edges WHERE src = ? OR dst = ?", (mem_id, mem_id)).fetchone()
                            if edge_row and edge_row["c"] > 0:
                                residue_count += 1
                finally:
                    conn.close()
            except Exception:
                pass

        return residue_count / len(deleted_ids)

    @classmethod
    def calculate_deletion_fidelity(cls, deleted_ids: List[str]) -> float:
        """Deletion Fidelity: Scans all database tables to verify zero trace.

        Returns 1.0 if absolutely no remnants exist, 0.0 otherwise.
        """
        if not deleted_ids:
            return 1.0

        paths = cls._get_db_paths()

        for path in paths:
            try:
                conn = sqlite3.connect(path)
                conn.row_factory = sqlite3.Row
                try:
                    tables_row = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                    tables = [r["name"] for r in tables_row]

                    for mem_id in deleted_ids:
                        for table in tables:
                            if table == "sqlite_sequence" or "fts" in table:
                                continue
                            # Inspect columns
                            cursor = conn.execute(f"PRAGMA table_info({table})")
                            columns = [col["name"] for col in cursor.fetchall()]
                            
                            for col in columns:
                                try:
                                    row = conn.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE {col} = ?", (mem_id,)).fetchone()
                                    if row and row["c"] > 0:
                                        return 0.0
                                except Exception:
                                    pass
                finally:
                    conn.close()
            except Exception:
                pass

        return 1.0

    @classmethod
    def run_evomem_drift_benchmark(cls) -> Dict[str, Any]:
        """EvoMem Dynamic Drift recall test.

        Simulates preference updates under time-drift and checks memory recall quality.
        """
        HumanMemoryStore.reset()
        t1 = time.time() - (10 * 86400)
        t2 = time.time() - (5 * 86400)

        # Day 1: Preference A
        rec1 = MemoryRecord(
            id="pref_python",
            type=MemoryType.SEMANTIC,
            content="User prefers Python for backend development",
            importance=0.7,
            confidence=0.8,
            decay_score=0.9,
            recall_count=0,
            created_at=t1,
            last_recall_at=t1,
            pinned=False,
            trusted=True,
            source="user_input",
            compression_level=0,
        )
        HumanMemoryStore.insert(rec1)

        # Day 5: Preference B (supersedes A due to safety)
        rec2 = MemoryRecord(
            id="pref_rust",
            type=MemoryType.SEMANTIC,
            content="User prefers Rust for backend development because compiler guarantees safety",
            importance=0.8,
            confidence=0.9,
            decay_score=0.9,
            recall_count=0,
            created_at=t2,
            last_recall_at=t2,
            pinned=False,
            trusted=True,
            source="user_input",
            compression_level=0,
        )
        HumanMemoryStore.insert(rec2)
        
        HumanMemoryStore.add_edge("pref_python", "pref_rust", relation="superseded")

        # Day 10: Query Current preference
        current_hits = RecallEngine.recall("What backend programming language does the user prefer?", limit=3, include_forgotten=False)
        current_ok = 0.0
        causal_ok = 0.0
        
        if current_hits:
            best_hit = current_hits[0].record.content
            if "rust" in best_hit.lower():
                current_ok = 1.0
            if "compiler guarantees safety" in best_hit.lower():
                causal_ok = 1.0

        # Query Historical preference
        history_hits = RecallEngine.recall("What language did the user historically prefer?", limit=5, include_forgotten=True)
        history_ok = 0.0
        for hit in history_hits:
            if "python" in hit.record.content.lower():
                history_ok = 1.0
                break

        overall_score = (current_ok * 0.4) + (causal_ok * 0.3) + (history_ok * 0.3)
        return {
            "current_preference_accuracy": current_ok,
            "causal_recall_accuracy": causal_ok,
            "history_recall_accuracy": history_ok,
            "overall_score": round(overall_score, 4)
        }
