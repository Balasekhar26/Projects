"""Tests for MemoryGovernance (Governance Layer).

Verifies:
- Centralized trust registry CRUD and normalization.
- Promotion evaluator correctly gates facts from untrusted episodes.
- Global GC sweep orchestrates episodic + semantic orphan purges.
- Cross-layer validation detects and repairs missing Chroma vectors.
- Governance audit event log is written on key operations.
- Scheduler lifecycle (start / stop).
"""

import json
import sqlite3
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from backend.core.memory_governance import MemoryGovernance


class NoCloseConn:
    """Proxy that prevents close() from terminating the shared in-memory DB."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def close(self) -> None:  # no-op
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestMemoryGovernance(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Create a single shared in-memory DB for the whole test class."""
        cls._db = sqlite3.connect(":memory:", check_same_thread=False)
        cls._db.row_factory = sqlite3.Row
        # Build governance schema once
        MemoryGovernance._schema_ensured = False
        MemoryGovernance._ensure_schema(cls._db)
        MemoryGovernance._schema_ensured = True  # prevent re-run on conn open

    def setUp(self):
        """Clear all governance tables and patch _get_sqlite_conn per test."""
        self._db.execute("DELETE FROM hm_trust_registry")
        self._db.execute("DELETE FROM hm_provenance")
        self._db.execute("DELETE FROM hm_governance_events")
        self._db.commit()

        self.conn_patcher = patch.object(
            MemoryGovernance,
            "_get_sqlite_conn",
            return_value=NoCloseConn(self._db),
        )
        self.conn_patcher.start()

    def tearDown(self):
        MemoryGovernance.stop_scheduler()
        self.conn_patcher.stop()

    @classmethod
    def tearDownClass(cls):
        cls._db.close()

    # ---------- Trust Registry ----------

    def test_set_and_get_trust(self):
        """Setting trust for an entity should be readable back."""
        MemoryGovernance.set_trust("ep-001", "memory", "TRUST_USER")
        trust = MemoryGovernance.get_trust("ep-001")
        self.assertEqual(trust, "TRUST_USER")

    def test_default_trust_is_unverified(self):
        """Unknown entities should return TRUST_UNVERIFIED by default."""
        trust = MemoryGovernance.get_trust("nonexistent-id")
        self.assertEqual(trust, "TRUST_UNVERIFIED")

    def test_trust_update_on_conflict(self):
        """Re-setting trust should update the existing record."""
        MemoryGovernance.set_trust("ep-002", "memory", "TRUST_UNVERIFIED")
        MemoryGovernance.set_trust("ep-002", "memory", "TRUST_CORROBORATED")
        trust = MemoryGovernance.get_trust("ep-002")
        self.assertEqual(trust, "TRUST_CORROBORATED")

    def test_invalid_trust_level_raises(self):
        """Setting an invalid trust level should raise ValueError."""
        with self.assertRaises(ValueError):
            MemoryGovernance.set_trust("ep-bad", "memory", "SUPER_TRUST")

    def test_trust_levels_all_valid(self):
        """All five canonical trust levels must be accepted."""
        for level in [
            "TRUST_SYSTEM",
            "TRUST_USER",
            "TRUST_CORROBORATED",
            "TRUST_UNVERIFIED",
            "TRUST_UNTRUSTED",
        ]:
            MemoryGovernance.set_trust(f"eid-{level}", "memory", level)
            self.assertEqual(MemoryGovernance.get_trust(f"eid-{level}"), level)

    # ---------- Provenance Registry ----------

    def test_log_and_get_provenance(self):
        """Logged provenance should be retrievable by memory_id."""
        MemoryGovernance.log_provenance(
            memory_id="sem-001",
            memory_type="semantic",
            source="user",
            created_by="broker",
            confidence=0.8,
            derived_from=["ep-101", "ep-102"],
            metadata={"session": "s1"},
        )
        prov = MemoryGovernance.get_provenance("sem-001")
        self.assertIsNotNone(prov)
        self.assertEqual(prov["memory_type"], "semantic")
        self.assertEqual(prov["source"], "user")
        self.assertIn("ep-101", prov["derived_from"])
        self.assertIn("ep-102", prov["derived_from"])
        self.assertAlmostEqual(prov["confidence"], 0.8)

    def test_get_provenance_unknown_returns_none(self):
        """Querying an unlogged memory_id should return None."""
        self.assertIsNone(MemoryGovernance.get_provenance("nonexistent"))

    def test_log_provenance_upserts_on_conflict(self):
        """Re-logging provenance for the same memory_id should update it."""
        MemoryGovernance.log_provenance(
            "sem-002", "semantic", "user", "broker", 0.5
        )
        MemoryGovernance.log_provenance(
            "sem-002", "semantic", "system", "compiler", 0.9
        )
        prov = MemoryGovernance.get_provenance("sem-002")
        self.assertAlmostEqual(prov["confidence"], 0.9)

    # ---------- Promotion Policy Engine ----------

    def test_can_promote_fact_requires_two_episodes(self):
        """Promotion must be blocked if fewer than 2 episodes are provided."""
        allowed, reason = MemoryGovernance.can_promote_fact(["ep-only-one"])
        self.assertFalse(allowed)
        self.assertEqual(reason, "insufficient_episode_count")

    def test_can_promote_fact_blocks_untrusted_episodes(self):
        """Promotion must be blocked if any episode is TRUST_UNTRUSTED."""
        MemoryGovernance.set_trust("ep-bad-1", "memory", "TRUST_UNTRUSTED")
        MemoryGovernance.set_trust("ep-good-1", "memory", "TRUST_USER")
        allowed, reason = MemoryGovernance.can_promote_fact(
            ["ep-bad-1", "ep-good-1"]
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "untrusted_source_episodes")

    def test_can_promote_fact_allows_two_trusted_episodes(self):
        """Promotion must be allowed for two trusted episodes."""
        MemoryGovernance.set_trust("ep-ok-1", "memory", "TRUST_USER")
        MemoryGovernance.set_trust("ep-ok-2", "memory", "TRUST_CORROBORATED")
        allowed, reason = MemoryGovernance.can_promote_fact(
            ["ep-ok-1", "ep-ok-2"]
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "allowed")

    def test_can_promote_fact_allows_unverified_episodes_not_in_registry(self):
        """Episodes absent from the registry default to TRUST_UNVERIFIED (not untrusted)."""
        allowed, reason = MemoryGovernance.can_promote_fact(
            ["ep-anon-1", "ep-anon-2"]
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "allowed")

    # ---------- Governance Audit Events ----------

    def test_log_governance_event(self):
        """Logged governance events should appear in the audit trail."""
        MemoryGovernance.log_governance_event(
            "GC_SWEEP",
            target_id=None,
            details={"episodic_orphans_purged": 3, "semantic_orphans_purged": 1},
        )
        events = MemoryGovernance.get_governance_events(limit=10)
        self.assertGreaterEqual(len(events), 1)
        latest = events[0]
        self.assertEqual(latest["event_type"], "GC_SWEEP")
        details = json.loads(latest["details_json"])
        self.assertEqual(details["episodic_orphans_purged"], 3)

    def test_multiple_event_types_stored(self):
        """Multiple distinct event types should all be persisted."""
        for etype in ["GC_SWEEP", "REPAIR", "PROMOTION", "TRUST_VIOLATION"]:
            MemoryGovernance.log_governance_event(etype, details={"test": True})
        events = MemoryGovernance.get_governance_events(limit=10)
        types_found = {e["event_type"] for e in events}
        for etype in ["GC_SWEEP", "REPAIR", "PROMOTION", "TRUST_VIOLATION"]:
            self.assertIn(etype, types_found)

    # ---------- Global GC (mocked layers) ----------

    def test_run_global_gc_delegates_to_layers(self):
        """run_global_gc should call each layer GC method and return counts."""
        with (
            patch(
                "backend.core.episodic_memory.EpisodicMemory.run_vector_gc",
                return_value=5,
            ) as mock_epi_gc,
            patch(
                "backend.core.semantic_memory.SemanticMemory.run_vector_gc",
                return_value=3,
            ) as mock_sem_gc,
            patch(
                "backend.core.episodic_memory.EpisodicMemory.archive_decayed_episodes",
                return_value=2,
            ) as mock_archive,
        ):
            counts = MemoryGovernance.run_global_gc()

        mock_epi_gc.assert_called_once()
        mock_sem_gc.assert_called_once()
        mock_archive.assert_called_once()
        self.assertEqual(counts["episodic_orphans_purged"], 5)
        self.assertEqual(counts["semantic_orphans_purged"], 3)
        self.assertEqual(counts["decayed_episodes_archived"], 2)

    def test_run_global_gc_logs_event(self):
        """run_global_gc should emit a GC_SWEEP governance event."""
        with (
            patch(
                "backend.core.episodic_memory.EpisodicMemory.run_vector_gc",
                return_value=0,
            ),
            patch(
                "backend.core.semantic_memory.SemanticMemory.run_vector_gc",
                return_value=0,
            ),
            patch(
                "backend.core.episodic_memory.EpisodicMemory.archive_decayed_episodes",
                return_value=0,
            ),
        ):
            MemoryGovernance.run_global_gc()

        events = MemoryGovernance.get_governance_events(limit=5)
        self.assertTrue(any(e["event_type"] == "GC_SWEEP" for e in events))

    # ---------- Scheduler ----------

    def test_scheduler_starts_and_stops(self):
        """start_scheduler should create a live daemon thread; stop should join it."""
        MemoryGovernance.start_scheduler()
        self.assertIsNotNone(MemoryGovernance._scheduler_thread)
        self.assertTrue(MemoryGovernance._scheduler_thread.is_alive())
        MemoryGovernance.stop_scheduler()
        self.assertIsNone(MemoryGovernance._scheduler_thread)

    # ---------- Cross-Layer Validation (mocked layers) ----------

    def test_cross_layer_validation_ok_when_in_sync(self):
        """Validation should report OK when SQLite and Chroma are empty and in sync."""
        # Ensure the hm_episodes and hm_semantic_nodes tables exist in our in-memory DB
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS hm_episodes (
                id TEXT PRIMARY KEY, content TEXT NOT NULL,
                session_id TEXT, importance REAL, category TEXT,
                created_at REAL, last_recalled_at REAL,
                recall_count INTEGER, pinned INTEGER, tags TEXT
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS hm_semantic_nodes (
                id TEXT PRIMARY KEY, concept TEXT NOT NULL,
                description TEXT NOT NULL, confidence REAL,
                evidence_count INTEGER, source_episode_ids TEXT,
                provenance TEXT, created_at REAL, updated_at REAL
            )
            """
        )
        self._db.commit()

        mock_col = MagicMock()
        mock_col.count.return_value = 0
        mock_col.get.return_value = {"ids": []}

        with (
            patch(
                "backend.core.episodic_memory.EpisodicMemory._get_chroma_collection",
                return_value=mock_col,
            ),
            patch(
                "backend.core.semantic_memory.SemanticMemory._get_chroma_collection",
                return_value=mock_col,
            ),
        ):
            diagnostics = MemoryGovernance.run_cross_layer_validation()

        layers = {d["layer"]: d for d in diagnostics}
        self.assertIn("episodic", layers)
        self.assertIn("semantic", layers)
        self.assertEqual(layers["episodic"]["status"], "OK")
        self.assertEqual(layers["semantic"]["status"], "OK")


if __name__ == "__main__":
    unittest.main()
