"""
test_reflection_memory_store.py

Unit tests for Phase 3A: ReflectionMemoryStore of the Kattappa Persistent Memory Engine.
"""

from __future__ import annotations

import unittest
from typing import Dict, Any, List

from backend.core.memory.schemas import MemoryRecord, MemoryType
from backend.core.memory.reflection_memory_store import ReflectionMemoryStore
from backend.core.reflection_memory import ReflectionMemory


def _ref_record(
    *,
    memory_id: str = "ref-123",
    category: str = "RETRIEVAL",
    problem: str = "Slow index queries.",
    cause: str = "ChromaDB missing indices.",
    improvement: str = "Index embeddings asynchronously.",
    confidence: float = 0.85,
    source_type: str = "conversation",
) -> MemoryRecord:
    payload = {
        "category": category,
        "problem": problem,
        "cause": cause,
        "improvement": improvement,
        "source_type": source_type,
        "source_window_days": 7,
    }
    return MemoryRecord(
        memory_id=memory_id,
        memory_type=MemoryType.REFLECTION,
        source_agent="agent_r",
        payload=payload,
        importance_score=0.8,
        confidence=confidence,
    )


class TestReflectionMemoryStoreAdapter(unittest.TestCase):

    def setUp(self):
        self.store = ReflectionMemoryStore()

    def tearDown(self):
        self.store.close()

    def test_creates_correctly(self):
        self.assertEqual(self.store.memory_type, MemoryType.REFLECTION)

    def test_save_and_retrieve_and_experiment(self):
        # Clear database to prevent conflict
        conn = ReflectionMemory._get_sqlite_conn()
        try:
            conn.execute("DELETE FROM hm_interventions")
            conn.execute("DELETE FROM hm_guardrails")
            conn.execute("DELETE FROM hm_reflections")
            conn.commit()
        finally:
            conn.close()

        r = _ref_record(
            category="RETRIEVAL",
            problem="Slow index query latency.",
            cause="ChromaDB missing indexes.",
            improvement="Index asynchronously.",
            confidence=0.9
        )
        self.store.save(r)

        # Retrieve
        results = self.store.retrieve({"category": "RETRIEVAL"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].payload["category"], "RETRIEVAL")
        self.assertEqual(results[0].payload["problem"], "Slow index query latency.")

        # Test duplicate reflection increments evidence count
        r_dup = _ref_record(
            category="RETRIEVAL",
            problem="Slow index query latency.",
            source_type="log_monitor"
        )
        self.store.save(r_dup)

        updated_rec = self.store.get(results[0].memory_id)
        self.assertEqual(updated_rec.payload["evidence_count"], 2)
        self.assertEqual(updated_rec.payload["source_count"], 2)

        # Test starting experiment
        ref_id = results[0].memory_id
        int_id = self.store.start_experiment(ref_id, "test_exp", "apply index", 10.0)
        self.assertIsNotNone(int_id)

        # Conclude experiment
        success = self.store.conclude_experiment(int_id, 2.0, "success")
        self.assertTrue(success)

        # Retrieve status has updated to accepted
        final_rec = self.store.get(ref_id)
        self.assertEqual(final_rec.payload["status"], "accepted")

    def test_forget_removes_low_confidence(self):
        # Clear database
        conn = ReflectionMemory._get_sqlite_conn()
        try:
            conn.execute("DELETE FROM hm_reflections")
            conn.commit()
        finally:
            conn.close()

        r_low = _ref_record(problem="Low value problem", confidence=0.2)
        self.store.save(r_low)

        # Prune
        pruned = self.store.forget(retention_threshold=0.3)
        self.assertEqual(pruned, 1)


if __name__ == "__main__":
    unittest.main()
