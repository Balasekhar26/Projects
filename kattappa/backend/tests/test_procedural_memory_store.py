"""
test_procedural_memory_store.py

Unit tests for Phase 2C: ProceduralMemoryStore of the Kattappa Persistent Memory Engine.
"""

from __future__ import annotations

import unittest
from typing import Dict, Any, List

from backend.core.memory.schemas import MemoryRecord, MemoryType
from backend.core.memory.procedural_memory_store import ProceduralMemoryStore
from backend.core.procedural_memory import ProceduralMemory


def _proc_record(
    *,
    memory_id: str = "proc-123",
    skill_name: str = "deploy_app",
    steps: List[Dict[str, Any]] = None,
    trust_level: str = "SYSTEM_TRUST",
    procedure_version: int = 1,
) -> MemoryRecord:
    payload = {
        "skill_name": skill_name,
        "steps": steps or [{"step": 1, "action": "build_docker"}],
        "trust_level": trust_level,
        "procedure_version": procedure_version,
    }
    return MemoryRecord(
        memory_id=memory_id,
        memory_type=MemoryType.PROCEDURAL,
        source_agent="agent_x",
        payload=payload,
        importance_score=1.0,
        confidence=1.0,
    )


class TestProceduralMemoryStoreAdapter(unittest.TestCase):

    def setUp(self):
        self.store = ProceduralMemoryStore()

    def tearDown(self):
        self.store.close()

    def test_creates_correctly(self):
        self.assertEqual(self.store.memory_type, MemoryType.PROCEDURAL)

    def test_save_and_retrieve_and_validate(self):
        # Clear database to prevent version conflict
        conn = ProceduralMemory._get_sqlite_conn()
        try:
            conn.execute("DELETE FROM hm_procedures")
            conn.execute("DELETE FROM hm_procedure_audit")
            conn.commit()
        finally:
            conn.close()

        r = _proc_record(
            memory_id="proc-deploy",
            skill_name="test_deploy",
            steps=[{"step": 1, "action": "test"}],
            trust_level="SYSTEM_TRUST",
            procedure_version=1
        )
        self.store.save(r)

        # Retrieve
        results = self.store.retrieve({"skill_name": "test_deploy"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].payload["skill_name"], "test_deploy")
        self.assertEqual(results[0].payload["trust_level"], "SYSTEM_TRUST")

        # Verify signature exists
        self.assertIsNotNone(results[0].payload["signature"])

        # Validate execution allowed from safe system source
        allowed, reason = self.store.validate_execution("proc-deploy", "system")
        self.assertTrue(allowed)

        # Revoke procedure
        self.store.revoke("proc-deploy")
        revoked_rec = self.store.get("proc-deploy")
        self.assertTrue(revoked_rec.payload["revoked"])

        # Execution validation should now be blocked
        allowed, reason = self.store.validate_execution("proc-deploy", "system")
        self.assertFalse(allowed)
        self.assertIn("revoked", reason.lower())

    def test_forget_does_nothing(self):
        # Verify forget is a no-op (procedures are permanent assets)
        pruned = self.store.forget(retention_threshold=1.0)
        self.assertEqual(pruned, 0)


if __name__ == "__main__":
    unittest.main()
