"""
test_semantic_memory_store.py

Unit tests for Phase 2A: SemanticMemoryStore Adapter of the Kattappa Persistent Memory Engine.
"""

from __future__ import annotations

import time
import unittest
from typing import List, Optional

from backend.core.memory.schemas import MemoryRecord, MemoryType
from backend.core.memory.semantic_memory_store import SemanticMemoryStore
from backend.core.semantic_memory import SemanticMemory


def _sem_record(
    *,
    memory_id: Optional[str] = None,
    node_type: str = "FACT",
    status: str = "ACTIVE",
    title: str = "Test Fact Header",
    content: str = "Verification rules define fact corroborations.",
    source_episode_id: str = "s-123",
    confidence: float = 0.95,
    tags: List[str] = None,
) -> MemoryRecord:
    payload = {
        "node_type": node_type,
        "status": status,
        "title": title,
        "content": content,
        "source_episode_id": source_episode_id,
        "source_reference_hash": "SHA256:custom_reference_hash",
        "source_type": "REFLECTION_CORROBORATED"
    }
    return MemoryRecord(
        memory_id=memory_id,
        memory_type=MemoryType.SEMANTIC,
        source_agent="agent_z",
        payload=payload,
        importance_score=0.8,
        confidence=confidence,
        tags=tags or [],
    )


class TestSemanticMemoryStoreAdapter(unittest.TestCase):

    def setUp(self):
        # We start the background embedding workers on SemanticMemory to prevent warnings
        SemanticMemory.start_worker()
        self.store = SemanticMemoryStore()

    def tearDown(self):
        self.store.close()
        SemanticMemory.stop_worker()

    def test_creates_correctly(self):
        self.assertEqual(self.store.memory_type, MemoryType.SEMANTIC)

    def test_save_and_retrieve_structured(self):
        # Clean potential leftovers from previous runs
        conn = SemanticMemory._get_sqlite_conn()
        try:
            conn.execute("DELETE FROM semantic_sources")
            conn.execute("DELETE FROM semantic_evidence")
            conn.execute("DELETE FROM semantic_nodes")
            conn.commit()
        finally:
            conn.close()

        r = _sem_record(title="Adapter Concept", content="Adapter wraps the legacy engine.", node_type="CONCEPT")
        self.store.save(r)

        # Retrieve structured
        results = self.store.retrieve({"node_type": "CONCEPT"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].payload["title"], "Adapter Concept")
        self.assertEqual(results[0].payload["content"], "Adapter wraps the legacy engine.")

        # Test delete (which maps to deprecation status)
        node_id = results[0].memory_id
        self.store.delete(node_id)

        # Active lookup should hide it
        self.assertIsNone(self.store.get(node_id))

    def test_retrieve_filters(self):
        # Clear database
        conn = SemanticMemory._get_sqlite_conn()
        try:
            conn.execute("DELETE FROM semantic_sources")
            conn.execute("DELETE FROM semantic_evidence")
            conn.execute("DELETE FROM semantic_nodes")
            conn.commit()
        finally:
            conn.close()

        # 1. First save as FACT with source s-1. Stored as HYPOTHESIS (single evidence).
        r1 = _sem_record(title="First Fact", node_type="FACT", source_episode_id="s-1")
        self.store.save(r1)

        # 2. Save CONCEPT (stored as CONCEPT immediately).
        r2 = _sem_record(title="First Concept", node_type="CONCEPT", source_episode_id="s-1")
        self.store.save(r2)

        # Initially, querying node_type CONCEPT returns 1 row
        self.assertEqual(len(self.store.retrieve({"node_type": "CONCEPT"})), 1)

        # Querying node_type FACT returns 0 rows (since First Fact is still HYPOTHESIS)
        self.assertEqual(len(self.store.retrieve({"node_type": "FACT"})), 0)

        # 3. Save First Fact again from a second source s-2 to corroborate it and promote to FACT.
        r3 = _sem_record(title="First Fact", node_type="FACT", source_episode_id="s-2")
        self.store.save(r3)

        # Querying node_type FACT should now successfully retrieve 1 row!
        facts = self.store.retrieve({"node_type": "FACT"})
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].payload["title"], "First Fact")


if __name__ == "__main__":
    unittest.main()
