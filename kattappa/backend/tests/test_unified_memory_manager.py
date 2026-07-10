"""
test_unified_memory_manager.py

Unit tests for Phase 4A: Unified Memory Manager context retrieval and conflict resolution.
"""

from __future__ import annotations

import time
import unittest
from typing import Dict, Any, List

from backend.core.memory.schemas import MemoryRecord, MemoryType
from backend.core.memory.memory_manager import MemoryManager
from backend.core.memory.working_memory_store import WorkingMemoryStore
from backend.core.memory.episodic_memory_store import EpisodicMemoryStore
from backend.core.memory.semantic_memory_store import SemanticMemoryStore
from backend.core.memory.policy_memory_store import PolicyMemoryStore


class TestUnifiedMemoryManager(unittest.TestCase):

    def setUp(self):
        self.manager = MemoryManager()
        self.working = WorkingMemoryStore(db_path=":memory:")
        self.episodic = EpisodicMemoryStore(db_path=":memory:")
        self.semantic = SemanticMemoryStore()  # Adapter wraps shared SemanticMemory DB
        self.policy = PolicyMemoryStore(db_path=":memory:")

        self.manager.register(self.working)
        self.manager.register(self.episodic)
        self.manager.register(self.semantic)
        self.manager.register(self.policy)

    def tearDown(self):
        self.working.close()
        self.episodic.close()
        self.semantic.close()
        self.policy.close()

    def test_retrieve_context_from_multiple_stores(self):
        # 1. Add working memory
        rec_work = MemoryRecord(
            memory_id="w-1",
            memory_type=MemoryType.WORKING,
            source_agent="agent_a",
            payload={"key": "active_task", "content": "Deploying the Kattappa unified system."},
            importance_score=0.9,
            confidence=0.9
        )
        self.working.save(rec_work)

        # 2. Add episodic memory
        rec_epi = MemoryRecord(
            memory_id="e-1",
            memory_type=MemoryType.EPISODIC,
            source_agent="agent_b",
            payload={"title": "deployment log", "content": "Kattappa system is active."},
            importance_score=0.8,
            confidence=0.8
        )
        self.episodic.save(rec_epi)

        # Retrieve context
        ctx = self.manager.retrieve_context("Kattappa system", limit=5)
        self.assertIn("combined", ctx)
        self.assertIn("working", ctx["results"])
        self.assertIn("episodic", ctx["results"])

        # Check the combined RRF-ranked results contains matching items
        combined_titles = [
            (r.payload.get("key") or r.payload.get("title"))
            for r in ctx["combined"]
        ]
        self.assertIn("deployment log", combined_titles)

    def test_resolve_conflicts_heuristics(self):
        now = time.time()
        
        # Scenario A: Status overrides deprecated
        r1 = MemoryRecord(
            memory_id="r1",
            memory_type=MemoryType.WORKING,
            source_agent="agent_a",
            timestamp=now - 100,
            payload={"title": "Config-Server", "status": "DEPRECATED"},
            confidence=0.9,
            importance_score=0.5
        )
        r2 = MemoryRecord(
            memory_id="r2",
            memory_type=MemoryType.WORKING,
            source_agent="agent_a",
            timestamp=now - 50,
            payload={"title": "Config-Server", "status": "ACTIVE"},
            confidence=0.7,
            importance_score=0.5
        )

        # ACTIVE should take precedence even if r1 has higher confidence
        resolved = self.manager.resolve_conflicts([r1, r2])
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].memory_id, "r2")

        # Scenario B: Confidence overrides
        r3 = MemoryRecord(
            memory_id="r3",
            memory_type=MemoryType.WORKING,
            source_agent="agent_a",
            timestamp=now - 100,
            payload={"title": "Memory-Limits", "status": "ACTIVE"},
            confidence=0.95,
            importance_score=0.5
        )
        r4 = MemoryRecord(
            memory_id="r4",
            memory_type=MemoryType.WORKING,
            source_agent="agent_a",
            timestamp=now - 50,
            payload={"title": "Memory-Limits", "status": "ACTIVE"},
            confidence=0.6,
            importance_score=0.5
        )

        resolved_conf = self.manager.resolve_conflicts([r3, r4])
        self.assertEqual(len(resolved_conf), 1)
        self.assertEqual(resolved_conf[0].memory_id, "r3")

        # Scenario C: Recency overrides when confidence matches
        r5 = MemoryRecord(
            memory_id="r5",
            memory_type=MemoryType.WORKING,
            source_agent="agent_a",
            timestamp=now - 100,
            payload={"title": "API-Key", "status": "ACTIVE"},
            confidence=0.8,
            importance_score=0.5
        )
        r6 = MemoryRecord(
            memory_id="r6",
            memory_type=MemoryType.WORKING,
            source_agent="agent_a",
            timestamp=now - 10,
            payload={"title": "API-Key", "status": "ACTIVE"},
            confidence=0.8,
            importance_score=0.5
        )

        resolved_recency = self.manager.resolve_conflicts([r5, r6])
        self.assertEqual(len(resolved_recency), 1)
        self.assertEqual(resolved_recency[0].memory_id, "r6")


if __name__ == "__main__":
    unittest.main()
