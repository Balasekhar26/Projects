import time
import unittest
from unittest.mock import patch

from backend.core.episodic_memory import EpisodicMemory


import sqlite3

class NoCloseConnection:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TestEpisodicMemory(unittest.TestCase):

    def setUp(self):
        # Reset memory state
        try:
            EpisodicMemory._get_chroma_collection()
            EpisodicMemory._chroma_client.delete_collection("episodic_vectors")
            EpisodicMemory._collection = None
        except Exception:
            pass

        # Create a single in-memory database connection for the test class to bypass slow file system handles
        if not hasattr(self.__class__, "_shared_conn"):
            self.__class__._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.__class__._shared_conn.row_factory = sqlite3.Row
            EpisodicMemory._ensure_schema(self.__class__._shared_conn)
            
            from backend.core.memory_governance import MemoryGovernance
            MemoryGovernance._ensure_schema(self.__class__._shared_conn)

        # Clear tables
        self.__class__._shared_conn.execute("DELETE FROM hm_episodes")
        self.__class__._shared_conn.execute("DELETE FROM hm_provenance")
        self.__class__._shared_conn.commit()

        # Patch connection
        from backend.core.memory_governance import MemoryGovernance
        self.conn_patchers = [
            patch.object(EpisodicMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(MemoryGovernance, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
        ]
        for p in self.conn_patchers:
            p.start()

    def tearDown(self):
        EpisodicMemory.stop_worker()
        for p in self.conn_patchers:
            p.stop()

    def test_episodic_crud(self):
        # 1. Create Episode
        eid = EpisodicMemory.create_episode(
            content="Bala optimized database execution profiles.",
            importance=0.8,
            category="success",
            session_id="test-session",
            tags=["optimization", "database"],
            pinned=1
        )
        self.assertIsNotNone(eid)

        # Flush queue to execute vector index write
        EpisodicMemory.flush_embeddings()

        # 2. Get Episode & Lazy Decay (pinned = 1 prevents decay)
        episode = EpisodicMemory.get_episode(eid)
        self.assertIsNotNone(episode)
        self.assertEqual(episode["content"], "Bala optimized database execution profiles.")
        self.assertEqual(episode["importance"], 0.8)
        self.assertEqual(episode["decay_score"], 0.8)  # Pinned locked to >= importance
        self.assertEqual(episode["pinned"], 1)

        # 3. Update Episode
        updated = EpisodicMemory.update_episode(
            eid,
            content="Bala refactored and optimized SQLite queries.",
            pinned=0
        )
        self.assertTrue(updated)
        EpisodicMemory.flush_embeddings()

        episode = EpisodicMemory.get_episode(eid)
        self.assertEqual(episode["content"], "Bala refactored and optimized SQLite queries.")
        self.assertEqual(episode["pinned"], 0)

        # 4. Delete Episode
        deleted = EpisodicMemory.delete_episode(eid)
        self.assertTrue(deleted)
        
        # Verify gone
        self.assertIsNone(EpisodicMemory.get_episode(eid))

    def test_lazy_decay_calculation(self):
        eid = EpisodicMemory.create_episode(
            content="Bala encountered a minor build pipeline syntax warning.",
            importance=0.6,
            category="warning",
            pinned=0
        )
        EpisodicMemory.flush_embeddings()

        # Mock time jump: set last_recalled_at to 2 days ago (172800 seconds)
        two_days_ago = time.time() - 172800.0
        conn = EpisodicMemory._get_sqlite_conn()
        try:
            conn.execute("UPDATE hm_episodes SET last_recalled_at = ? WHERE id = ?", (two_days_ago, eid))
            conn.commit()
        finally:
            conn.close()

        # Fetch and verify decay occurred
        episode = EpisodicMemory.get_episode(eid)
        self.assertLess(episode["decay_score"], 0.6)
        self.assertGreater(episode["decay_score"], 0.4)

    def test_hybrid_recall_and_rrf(self):
        eid1 = EpisodicMemory.create_episode(
            content="Database lockup resolved by memory broker serialization.",
            importance=0.9,
            category="success"
        )
        eid2 = EpisodicMemory.create_episode(
            content="Tauri application bundle compiled into production assets.",
            importance=0.5,
            category="moment"
        )
        EpisodicMemory.flush_embeddings()

        # Recall by lexical search (FTS5 match)
        results_lexical = EpisodicMemory.recall("Tauri", limit=2)
        self.assertEqual(len(results_lexical), 1)
        self.assertEqual(results_lexical[0]["id"], eid2)

        # Recall by semantic query (Vector match)
        results_semantic = EpisodicMemory.recall("database write locks", limit=2)
        self.assertEqual(len(results_semantic), 1)
        self.assertEqual(results_semantic[0]["id"], eid1)
        self.assertEqual(results_semantic[0]["recall_count"], 1)

    def test_vector_gc_ghost_recall(self):
        # 1. Create episode and flush
        eid = EpisodicMemory.create_episode(
            content="This is a test candidate for consistency sweeps.",
            importance=0.4,
            category="moment"
        )
        EpisodicMemory.flush_embeddings()

        # 2. Delete raw row from SQLite ONLY, creating a ghost vector
        conn = EpisodicMemory._get_sqlite_conn()
        try:
            conn.execute("DELETE FROM hm_episodes WHERE id = ?", (eid,))
            conn.commit()
        finally:
            conn.close()

        # 3. Running recall should skip it authoritative-check, but the vector still exists
        results = EpisodicMemory.recall("consistency sweeps", limit=2)
        self.assertEqual(len(results), 0)

        # 4. Execute GC sweep
        purged = EpisodicMemory.run_vector_gc()
        self.assertEqual(purged, 1)

        # 5. Verify vector has been removed from Chroma
        coll = EpisodicMemory._get_chroma_collection()
        self.assertEqual(coll.count(), 0)
