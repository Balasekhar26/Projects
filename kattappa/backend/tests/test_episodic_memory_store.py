"""
test_episodic_memory_store.py

Unit tests for Phase 1C of the Kattappa Persistent Memory Engine.

Covers:
  - EpisodicMemoryStore initialization and schemas/triggers.
  - Conformance to IMemoryStore: save(), retrieve(), forget(), health_check().
  - SQLite triggers auto-synchronization with FTS5 virtual table.
  - Asynchronous background embedding indexing via EventBus.
  - Reciprocal Rank Fusion (RRF) hybrid search combining FTS5 lexical hits and vector hits.
  - Graceful degradation when ChromaDB is mock-disabled or raises errors.
  - Filtering parameters: session_id, goal_id, episode_type, outcome, min_importance, min_confidence.
  - TTL expiration (default 90 days).
  - Explicit delete() and clean syncing to ChromaDB.
  - Concurrent writes from multiple threads (RLock verification).
  - Close and teardown cleanup.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from typing import List, Optional
from unittest.mock import MagicMock, patch

from backend.core.memory.schemas import MemoryRecord, MemoryType, DEFAULT_TTL
from backend.core.memory.episodic_memory_store import EpisodicMemoryStore
from backend.core.memory.memory_manager import MemoryManager
from backend.core.event_bus import EventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record(
    *,
    session_id: str = "s-default",
    goal_id: str = "",
    episode_type: str = "general",
    outcome: str = "unknown",
    consolidation_state: Optional[str] = None,
    title: str = "Test Episode",
    content: str = "This is a detailed record of the test execution.",
    source_agent: str = "agent_y",
    importance_score: float = 0.8,
    confidence: float = 0.9,
    tags: List[str] = None,
    memory_id: Optional[str] = None,
) -> MemoryRecord:
    payload = {
        "session_id": session_id,
        "goal_id": goal_id,
        "episode_type": episode_type,
        "outcome": outcome,
        "title": title,
        "content": content,
    }
    if consolidation_state is not None:
        payload["consolidation_state"] = consolidation_state
    return MemoryRecord(
        memory_type=MemoryType.EPISODIC,
        source_agent=source_agent,
        payload=payload,
        importance_score=importance_score,
        confidence=confidence,
        tags=tags or [],
        **({"memory_id": memory_id} if memory_id else {}),
    )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------
class TestEpisodicMemoryStoreInit(unittest.TestCase):

    def setUp(self):
        self.store = EpisodicMemoryStore(db_path=":memory:")

    def tearDown(self):
        self.store.close()

    def test_creates_correctly(self):
        self.assertIsNotNone(self.store)
        self.assertEqual(self.store.memory_type, MemoryType.EPISODIC)

    def test_health_check_on_empty(self):
        health = self.store.health_check()
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["total_records"], 0)
        self.assertEqual(health["expired_records"], 0)

    def test_repr_shows_path(self):
        self.assertIn(":memory:", repr(self.store))


class TestEpisodicMemoryStoreSaveAndFTS(unittest.TestCase):

    def setUp(self):
        self.store = EpisodicMemoryStore(db_path=":memory:")

    def tearDown(self):
        self.store.close()

    def test_save_inserts_and_fts_syncs(self):
        r = _record(title="First Deploy", content="Successfully deployed production stack.")
        self.store.save(r)

        # Check standard retrieve
        records = self.store.retrieve({})
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].payload["title"], "First Deploy")

        # Verify FTS virtual table has it
        with self.store._lock:
            conn = self.store._get_conn()
            fts_rows = conn.execute("SELECT * FROM episodic_memories_fts").fetchall()
            self.assertEqual(len(fts_rows), 1)
            self.assertEqual(fts_rows[0]["title"], "First Deploy")
            self.assertEqual(fts_rows[0]["content"], "Successfully deployed production stack.")

    def test_save_wrong_memory_type_raises(self):
        r = MemoryRecord(
            memory_type=MemoryType.WORKING,
            source_agent="a",
            payload={}
        )
        with self.assertRaises(TypeError):
            self.store.save(r)

    def test_delete_removes_from_both(self):
        r = _record()
        self.store.save(r)
        self.store.delete(r.memory_id)

        self.assertEqual(len(self.store.retrieve({})), 0)
        with self.store._lock:
            conn = self.store._get_conn()
            fts_rows = conn.execute("SELECT * FROM episodic_memories_fts").fetchall()
            self.assertEqual(len(fts_rows), 0)

    def test_update_syncs_fts(self):
        r = _record(memory_id="ep-1", title="Original Title", content="Original content")
        self.store.save(r)

        # Update record
        r_up = _record(memory_id="ep-1", title="Updated Title", content="Updated content")
        self.store.save(r_up)

        fetched = self.store.get("ep-1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.payload["title"], "Updated Title")

        with self.store._lock:
            conn = self.store._get_conn()
            fts_rows = conn.execute("SELECT * FROM episodic_memories_fts").fetchall()
            self.assertEqual(len(fts_rows), 1)
            self.assertEqual(fts_rows[0]["title"], "Updated Title")


class TestEpisodicMemoryStoreRetrieve(unittest.TestCase):

    def setUp(self):
        self.store = EpisodicMemoryStore(db_path=":memory:")

    def tearDown(self):
        self.store.close()

    def test_retrieve_filters(self):
        self.store.save(_record(session_id="s1", episode_type="PLANNING", outcome="success"))
        self.store.save(_record(session_id="s2", episode_type="TESTING", outcome="failure"))

        # Test session filter
        self.assertEqual(len(self.store.retrieve({"session_id": "s1"})), 1)
        # Test episode_type filter
        self.assertEqual(len(self.store.retrieve({"episode_type": "TESTING"})), 1)
        # Test outcome filter
        self.assertEqual(len(self.store.retrieve({"outcome": "failure"})), 1)

        # Verify consolidation_state defaults to ACTIVE
        records = self.store.retrieve({})
        self.assertEqual(records[0].payload["consolidation_state"], "ACTIVE")

        # Save with explicit state
        self.store.save(_record(session_id="s3", consolidation_state="CONSOLIDATED"))
        self.assertEqual(len(self.store.retrieve({"consolidation_state": "CONSOLIDATED"})), 1)

    def test_retrieve_min_signals(self):
        self.store.save(_record(importance_score=0.4, confidence=0.9))
        self.store.save(_record(importance_score=0.8, confidence=0.5))

        self.assertEqual(len(self.store.retrieve({"min_importance": 0.6})), 1)
        self.assertEqual(len(self.store.retrieve({"min_confidence": 0.7})), 1)

    def test_get_convenience_apis(self):
        self.store.save(_record(memory_id="m-1", session_id="s1", goal_id="g1", episode_type="BENCHMARK"))

        self.assertEqual(len(self.store.get_by_session("s1")), 1)
        self.assertEqual(len(self.store.get_by_goal("g1")), 1)
        self.assertEqual(len(self.store.get_by_type("BENCHMARK")), 1)


class TestEpisodicMemoryStoreAsyncEmbedding(unittest.TestCase):

    def setUp(self):
        self.temp_chroma = tempfile.mkdtemp()
        self.store = EpisodicMemoryStore(db_path=":memory:", chroma_path=self.temp_chroma)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_chroma, ignore_errors=True)

    @patch("chromadb.PersistentClient")
    def test_async_indexing_pipeline_triggered(self, mock_client_cls):
        # Setup mock Chroma collection
        mock_col = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_col
        mock_client_cls.return_value = mock_client

        # Save record
        r = _record(content="Unique deploy event content")
        self.store.save(r)

        # Allow EventBus async background pool worker time to process the job
        timeout = time.time() + 10.0
        while time.time() < timeout:
            fetched = self.store.get(r.memory_id)
            if fetched and fetched.embedding_id is not None:
                break
            time.sleep(0.1)

        # Check updates occurred
        fetched = self.store.get(r.memory_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.embedding_id, r.memory_id)
        mock_col.add.assert_called_with(ids=[r.memory_id], documents=["Unique deploy event content"])


class TestEpisodicMemoryStoreHybridRetrieval(unittest.TestCase):

    def setUp(self):
        self.temp_chroma = tempfile.mkdtemp()
        self.store = EpisodicMemoryStore(db_path=":memory:", chroma_path=self.temp_chroma)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_chroma, ignore_errors=True)

    def test_hybrid_search_rrf_merging(self):
        # Insert records
        r1 = _record(memory_id="ep-1", title="Kubernetes Cluster", content="Scaling nodes down to save costs.")
        r2 = _record(memory_id="ep-2", title="Database Backup", content="Automatic daily snapshot failed due to timeout.")
        self.store.save(r1)
        self.store.save(r2)

        # Mock ChromaDB query output
        mock_col = MagicMock()
        mock_col.query.return_value = {"ids": [["ep-2", "ep-1"]]}
        self.store._collection = mock_col
        self.store._chroma_available = True

        # Perform hybrid search for "snapshot failed"
        results = self.store.retrieve({"text": "snapshot failed"})

        # RRF should boost ep-2 to rank 1 because it matches lexical and vector best
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0].memory_id, "ep-2")

    def test_graceful_degradation_when_chromadb_fails(self):
        # Save a record
        r = _record(title="Lexical Only Search", content="This database handles local indexing.")
        self.store.save(r)

        # Simulate ChromaDB query throwing exception
        mock_col = MagicMock()
        mock_col.query.side_effect = Exception("Chroma is offline!")
        self.store._collection = mock_col
        self.store._chroma_available = True

        # Search should still succeed via FTS5
        results = self.store.retrieve({"text": "database local"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].payload["title"], "Lexical Only Search")


class TestEpisodicMemoryStoreTTLAndForgetting(unittest.TestCase):

    def setUp(self):
        self.store = EpisodicMemoryStore(db_path=":memory:")

    def tearDown(self):
        self.store.close()

    def test_default_ttl_is_90_days(self):
        self.assertEqual(DEFAULT_TTL[MemoryType.EPISODIC], 90 * 86400)

    def test_forget_removes_expired_records(self):
        # Save an already expired record (backdated timestamp)
        r = _record()
        r.timestamp = time.time() - (91 * 86400)  # older than 90-day TTL
        self.store.save(r)

        # Trigger forget
        deleted = self.store.forget()
        self.assertEqual(deleted, 1)
        self.assertEqual(self.store.health_check()["total_records"], 0)

    def test_forget_retains_valid_records(self):
        r = _record()
        self.store.save(r)
        deleted = self.store.forget()
        self.assertEqual(deleted, 0)
        self.assertEqual(self.store.health_check()["total_records"], 1)


class TestEpisodicMemoryStoreConcurrency(unittest.TestCase):

    def setUp(self):
        self.store = EpisodicMemoryStore(db_path=":memory:")

    def tearDown(self):
        self.store.close()

    def test_concurrent_writes_and_reads(self):
        errors: List[Exception] = []

        def writer(tid: int):
            try:
                for i in range(10):
                    r = _record(memory_id=f"thread-{tid}-{i}", title=f"Thread {tid} Item {i}")
                    self.store.save(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(self.store.health_check()["total_records"], 50)


if __name__ == "__main__":
    unittest.main()
