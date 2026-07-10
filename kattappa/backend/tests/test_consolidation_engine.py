"""
test_consolidation_engine.py

Unit tests for Phase 1D: ConsolidationEngine of the Kattappa Persistent Memory Engine.
"""

from __future__ import annotations

import time
import unittest
from typing import Dict, Any, List

from backend.core.memory.schemas import MemoryRecord, MemoryType
from backend.core.memory.working_memory_store import WorkingMemoryStore
from backend.core.memory.episodic_memory_store import EpisodicMemoryStore
from backend.core.memory.consolidation_engine import ConsolidationEngine, ConsolidationReport


def _work_record(
    *,
    memory_id: str,
    key: str,
    content: str,
    importance_score: float = 0.5,
    confidence: float = 0.8,
    access_count: int = 1,
    pinned: bool = False,
    session_id: str = "s-1",
    goal_id: str = "g-1",
    tags: List[str] = None,
) -> MemoryRecord:
    payload = {
        "key": key,
        "content": content,
        "access_count": access_count,
        "pinned": pinned,
        "session_id": session_id,
        "goal_id": goal_id,
    }
    return MemoryRecord(
        memory_id=memory_id,
        memory_type=MemoryType.WORKING,
        source_agent="agent_x",
        payload=payload,
        importance_score=importance_score,
        confidence=confidence,
        tags=tags or [],
    )


class TestConsolidationEngine(unittest.TestCase):

    def setUp(self):
        self.working = WorkingMemoryStore(db_path=":memory:")
        self.episodic = EpisodicMemoryStore(db_path=":memory:")
        self.engine = ConsolidationEngine(
            working_store=self.working,
            episodic_store=self.episodic,
        )

    def tearDown(self):
        self.working.close()
        self.episodic.close()

    def test_promotion_gates_and_score(self):
        # 1. Promote via score threshold
        # Score = (0.9*0.4) + (0*0.25) + (1.0*0.15) + (0.9*0.20) = 0.36 + 0.15 + 0.18 = 0.69 >= 0.5 (promote)
        r1 = _work_record(
            memory_id="w-1", key="deploy", content="Deploy stack successfully.",
            importance_score=0.9, confidence=0.9, access_count=0
        )
        self.working.save(r1)

        # 2. Discard via low score
        # Score = (0.2*0.4) + (0*0.25) + (1.0*0.15) + (0.5*0.20) = 0.08 + 0.15 + 0.10 = 0.33 < 0.5 (discard)
        r2 = _work_record(
            memory_id="w-2", key="temp", content="Temporary log event.",
            importance_score=0.2, confidence=0.5, access_count=0
        )
        self.working.save(r2)

        # Run consolidation
        report = self.engine.consolidate(promotion_threshold=0.5)

        self.assertEqual(report.scanned_count, 2)
        self.assertEqual(report.promoted_count, 1)
        self.assertEqual(report.discarded_count, 1)

        # w-1 should be promoted to EpisodicStore
        ep_rec = self.episodic.get("w-1")
        self.assertIsNotNone(ep_rec)
        self.assertEqual(ep_rec.payload["title"], "deploy")
        self.assertEqual(ep_rec.payload["consolidation_state"], "ACTIVE")

        # both should be deleted from WorkingStore
        self.assertIsNone(self.working.get("w-1"))
        self.assertIsNone(self.working.get("w-2"))

    def test_absolute_promotion_gates(self):
        # Absolute Gate 1: Pinned
        r1 = _work_record(
            memory_id="w-1", key="rules", content="Critical rules.",
            importance_score=0.1, confidence=0.1, pinned=True
        )
        self.working.save(r1)

        # Absolute Gate 2: High Interaction Frequency (access >= 5)
        r2 = _work_record(
            memory_id="w-2", key="loop", content="Frequent iteration check.",
            importance_score=0.1, confidence=0.1, access_count=6
        )
        self.working.save(r2)

        report = self.engine.consolidate(promotion_threshold=0.9)  # High threshold
        self.assertEqual(report.promoted_count, 2)
        self.assertIsNotNone(self.episodic.get("w-1"))
        self.assertIsNotNone(self.episodic.get("w-2"))

    def test_jaccard_deduplication_and_merging(self):
        # Insert three duplicate working records
        r1 = _work_record(
            memory_id="w-1", key="deploy_bug", content="Failing stack deployments due to timeout error.",
            importance_score=0.3, confidence=0.8, tags=["infra"]
        )
        r2 = _work_record(
            memory_id="w-2", key="deploy_bug", content="Stack deployment failed from timeout issue.",
            importance_score=0.7, confidence=0.9, tags=["bug"]
        )
        self.working.save(r1)
        self.working.save(r2)

        # Run consolidation (RRF or score will trigger promotion because r2 has high importance)
        report = self.engine.consolidate(jaccard_threshold=0.7, promotion_threshold=0.4)

        # Report stats
        self.assertEqual(report.scanned_count, 2)
        self.assertEqual(report.merged_count, 1)
        self.assertEqual(report.promoted_count, 1)

        # Verify w-2 (lead with highest priority) was promoted
        ep = self.episodic.get("w-2")
        self.assertIsNotNone(ep)
        self.assertEqual(ep.importance_score, 0.7)
        self.assertEqual(ep.confidence, 0.9)
        self.assertEqual(set(ep.tags), {"infra", "bug"})
        # Combined content
        self.assertIn("Failing stack deployments due to timeout error.", ep.payload["content"])
        self.assertIn("Stack deployment failed from timeout issue.", ep.payload["content"])

        # Both working records deleted
        self.assertIsNone(self.working.get("w-1"))
        self.assertIsNone(self.working.get("w-2"))

    def test_session_isolation(self):
        # Session s-1
        self.working.save(_work_record(memory_id="w-1", key="k1", content="c1", session_id="s-1", pinned=True))
        # Session s-2
        self.working.save(_work_record(memory_id="w-2", key="k2", content="c2", session_id="s-2", pinned=True))

        # Consolidate only s-1
        report = self.engine.consolidate(session_id="s-1")
        self.assertEqual(report.scanned_count, 1)
        self.assertEqual(report.promoted_count, 1)

        self.assertIsNotNone(self.episodic.get("w-1"))
        self.assertIsNone(self.episodic.get("w-2"))  # s-2 untouched
        self.assertIsNone(self.working.get("w-1"))
        self.assertIsNotNone(self.working.get("w-2"))  # s-2 working record retained


if __name__ == "__main__":
    unittest.main()
