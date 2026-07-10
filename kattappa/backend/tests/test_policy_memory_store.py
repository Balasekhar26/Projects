"""
test_policy_memory_store.py

Unit tests for Phase 3B: PolicyMemoryStore of the Kattappa Persistent Memory Engine.
"""

from __future__ import annotations

import unittest
from typing import Dict, Any, List

from backend.core.memory.schemas import MemoryRecord, MemoryType
from backend.core.memory.policy_memory_store import PolicyMemoryStore


def _pol_record(
    *,
    memory_id: str = "pol-123",
    rule_name: str = "No arbitrary code execution",
    description: str = "All shell code commands must be approved explicitly by the user.",
    active: bool = True,
    priority: float = 1.0,
) -> MemoryRecord:
    payload = {
        "rule_name": rule_name,
        "description": description,
        "active": active,
        "priority": priority,
    }
    return MemoryRecord(
        memory_id=memory_id,
        memory_type=MemoryType.POLICY,
        source_agent="security_officer",
        payload=payload,
        importance_score=1.0,
        confidence=1.0,
    )


class TestPolicyMemoryStore(unittest.TestCase):

    def setUp(self):
        self.store = PolicyMemoryStore(db_path=":memory:")

    def tearDown(self):
        self.store.close()

    def test_creates_correctly(self):
        self.assertEqual(self.store.memory_type, MemoryType.POLICY)

    def test_save_and_retrieve_fts(self):
        r = _pol_record(
            memory_id="p-1",
            rule_name="User Approval Rules",
            description="User approval is mandatory for write operations.",
            priority=2.0
        )
        self.store.save(r)

        # Retrieve structured
        results = self.store.retrieve({"active": True})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].payload["rule_name"], "User Approval Rules")

        # Retrieve text MATCH FTS
        hits = self.store.retrieve({"text": "mandatory write"})
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].payload["rule_name"], "User Approval Rules")

        # Deactivate policy
        self.store.deactivate("p-1")
        deact_rec = self.store.get("p-1")
        self.assertFalse(deact_rec.payload["active"])

        # Retrieval query should show zero active policies
        self.assertEqual(len(self.store.retrieve({"active": True})), 0)

    def test_forget_does_nothing(self):
        # Policy rules are permanent
        pruned = self.store.forget(retention_threshold=1.0)
        self.assertEqual(pruned, 0)


if __name__ == "__main__":
    unittest.main()
