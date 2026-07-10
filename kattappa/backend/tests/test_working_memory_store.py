"""
test_working_memory_store.py

Unit tests for Phase 1B of the Kattappa Persistent Memory Engine.

Covers:
  - WorkingMemoryStore initialization and schema creation.
  - IMemoryStore compliance: save(), retrieve(), forget(), health_check().
  - save() type enforcement (rejects non-WORKING records).
  - save() ON CONFLICT upsert behavior.
  - TTL-based expiry: records become invisible after TTL.
  - expire() manual expiry.
  - forget() expired-record pruning and retention-threshold pruning.
  - Priority-based retrieval ordering.
  - Session isolation: records from different sessions don't bleed.
  - get_active_context() and get_goal_context() filters.
  - clear_session() removes only the target session.
  - consolidate() returns promotion-ready records above thresholds.
  - put() convenience wrapper.
  - get() single-record fetch with access counter bump.
  - delete() hard-delete.
  - MemoryManager integration: register + save + retrieve round-trip.
  - Concurrent writes from multiple threads (no data races).
  - health_check() reports correct counts.
  - close() is idempotent.
"""

from __future__ import annotations

import threading
import time
import unittest
from typing import List

from backend.core.memory.schemas import MemoryRecord, MemoryType, DEFAULT_TTL
from backend.core.memory.working_memory_store import WorkingMemoryStore, _DEFAULT_SESSION
from backend.core.memory.memory_manager import MemoryManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store() -> WorkingMemoryStore:
    """Return a fresh in-memory WorkingMemoryStore for each test."""
    return WorkingMemoryStore(db_path=":memory:")


def _record(
    *,
    session_id: str = "s-default",
    goal_id: str = "",
    key: str = "ctx",
    priority: int = 5,
    source_agent: str = "agent_x",
    importance_score: float = 0.7,
    confidence: float = 0.9,
    tags: List[str] = None,
    memory_id: str = None,
    extra: dict = None,
) -> MemoryRecord:
    payload = {"data": "test", "session_id": session_id, "goal_id": goal_id,
               "key": key, "priority": priority}
    if extra:
        payload.update(extra)
    return MemoryRecord(
        memory_type=MemoryType.WORKING,
        source_agent=source_agent,
        payload=payload,
        importance_score=importance_score,
        confidence=confidence,
        tags=tags or [],
        **({"memory_id": memory_id} if memory_id else {}),
    )


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------
class TestWorkingMemoryStoreInit(unittest.TestCase):

    def test_creates_without_error(self):
        store = _store()
        self.assertIsNotNone(store)
        store.close()

    def test_memory_type_is_working(self):
        self.assertIs(WorkingMemoryStore.memory_type, MemoryType.WORKING)

    def test_instance_memory_type_attribute(self):
        store = _store()
        self.assertIs(store.memory_type, MemoryType.WORKING)
        store.close()

    def test_health_check_on_empty_store(self):
        store = _store()
        health = store.health_check()
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["total_records"], 0)
        self.assertEqual(health["expired_records"], 0)
        store.close()

    def test_close_is_idempotent(self):
        store = _store()
        store.close()
        store.close()  # second call must not raise

    def test_repr_contains_db_path(self):
        store = _store()
        self.assertIn(":memory:", repr(store))
        store.close()


# ---------------------------------------------------------------------------
# save() tests
# ---------------------------------------------------------------------------
class TestWorkingMemoryStoreSave(unittest.TestCase):

    def setUp(self):
        self.store = _store()

    def tearDown(self):
        self.store.close()

    def test_save_valid_record(self):
        r = _record()
        self.store.save(r)
        health = self.store.health_check()
        self.assertEqual(health["total_records"], 1)

    def test_save_non_record_raises(self):
        with self.assertRaises(TypeError):
            self.store.save("not a record")  # type: ignore[arg-type]

    def test_save_wrong_memory_type_raises(self):
        r = MemoryRecord(
            memory_type=MemoryType.EPISODIC,
            source_agent="a",
            payload={},
        )
        with self.assertRaises(TypeError):
            self.store.save(r)

    def test_save_upsert_updates_value(self):
        r = _record(memory_id="fixed-001", key="original")
        self.store.save(r)

        r2 = _record(memory_id="fixed-001", key="updated")
        self.store.save(r2)

        fetched = self.store.get("fixed-001")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.payload["key"], "updated")

    def test_save_multiple_records(self):
        for i in range(5):
            self.store.save(_record(key=f"key-{i}"))
        self.assertEqual(self.store.health_check()["total_records"], 5)


# ---------------------------------------------------------------------------
# retrieve() tests
# ---------------------------------------------------------------------------
class TestWorkingMemoryStoreRetrieve(unittest.TestCase):

    def setUp(self):
        self.store = _store()

    def tearDown(self):
        self.store.close()

    def test_retrieve_all(self):
        for i in range(3):
            self.store.save(_record(session_id="s1", key=f"k{i}"))
        results = self.store.retrieve({})
        self.assertEqual(len(results), 3)

    def test_retrieve_returns_memory_records(self):
        self.store.save(_record())
        results = self.store.retrieve({})
        self.assertIsInstance(results[0], MemoryRecord)

    def test_retrieve_filter_session_id(self):
        self.store.save(_record(session_id="alice"))
        self.store.save(_record(session_id="bob"))
        results = self.store.retrieve({"session_id": "alice"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].payload["session_id"], "alice")

    def test_retrieve_filter_goal_id(self):
        self.store.save(_record(goal_id="g-001"))
        self.store.save(_record(goal_id="g-002"))
        results = self.store.retrieve({"goal_id": "g-001"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].payload["goal_id"], "g-001")

    def test_retrieve_filter_key(self):
        self.store.save(_record(key="plan"))
        self.store.save(_record(key="observation"))
        results = self.store.retrieve({"key": "plan"})
        self.assertEqual(len(results), 1)

    def test_retrieve_filter_min_importance(self):
        self.store.save(_record(importance_score=0.3))
        self.store.save(_record(importance_score=0.8))
        results = self.store.retrieve({"min_importance": 0.6})
        self.assertEqual(len(results), 1)
        self.assertGreaterEqual(results[0].importance_score, 0.6)

    def test_retrieve_filter_min_confidence(self):
        self.store.save(_record(confidence=0.2))
        self.store.save(_record(confidence=0.95))
        results = self.store.retrieve({"min_confidence": 0.7})
        self.assertEqual(len(results), 1)

    def test_retrieve_priority_order(self):
        self.store.save(_record(priority=7, key="low"))
        self.store.save(_record(priority=1, key="high"))
        self.store.save(_record(priority=4, key="mid"))
        results = self.store.retrieve({})
        priorities = [r.payload["priority"] for r in results]
        self.assertEqual(priorities, sorted(priorities))

    def test_retrieve_limit(self):
        for i in range(10):
            self.store.save(_record(key=f"k{i}"))
        results = self.store.retrieve({}, limit=3)
        self.assertEqual(len(results), 3)

    def test_retrieve_respects_expiry(self):
        r = _record()
        self.store.save(r)
        self.store.expire(r.memory_id)
        results = self.store.retrieve({})
        self.assertEqual(len(results), 0)

    def test_retrieve_include_expired_flag(self):
        r = _record()
        self.store.save(r)
        self.store.expire(r.memory_id)
        results = self.store.retrieve({"include_expired": True})
        self.assertEqual(len(results), 1)


# ---------------------------------------------------------------------------
# TTL expiry tests
# ---------------------------------------------------------------------------
class TestWorkingMemoryStoreTTL(unittest.TestCase):

    def setUp(self):
        self.store = _store()

    def tearDown(self):
        self.store.close()

    def test_default_ttl_is_three_hours(self):
        self.assertEqual(DEFAULT_TTL[MemoryType.WORKING], 3 * 3600)

    def test_fresh_record_is_visible(self):
        r = _record()
        self.store.save(r)
        fetched = self.store.get(r.memory_id)
        self.assertIsNotNone(fetched)

    def test_manually_expired_record_invisible_to_get(self):
        r = _record()
        self.store.save(r)
        self.store.expire(r.memory_id)
        fetched = self.store.get(r.memory_id)
        self.assertIsNone(fetched)

    def test_expire_returns_true_for_existing(self):
        r = _record()
        self.store.save(r)
        result = self.store.expire(r.memory_id)
        self.assertTrue(result)

    def test_expire_returns_false_for_missing(self):
        result = self.store.expire("nonexistent-id")
        self.assertFalse(result)

    def test_forget_removes_expired_records(self):
        r = _record()
        self.store.save(r)
        self.store.expire(r.memory_id)
        deleted = self.store.forget(0.0)
        self.assertGreaterEqual(deleted, 1)
        self.assertEqual(self.store.health_check()["total_records"], 0)

    def test_forget_returns_count(self):
        for _ in range(3):
            r = _record()
            self.store.save(r)
            self.store.expire(r.memory_id)
        count = self.store.forget(0.0)
        self.assertEqual(count, 3)

    def test_forget_threshold_prunes_low_quality(self):
        # low importance × confidence = 0.1 × 0.1 = 0.01 <= 0.05 threshold → pruned
        self.store.save(_record(importance_score=0.1, confidence=0.1, key="low"))
        # high importance × confidence = 0.9 × 0.9 = 0.81 > 0.05 → kept
        self.store.save(_record(importance_score=0.9, confidence=0.9, key="high"))
        deleted = self.store.forget(retention_threshold=0.05)
        self.assertEqual(deleted, 1)
        remaining = self.store.retrieve({})
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].payload["key"], "high")

    def test_forget_preserves_high_quality_records(self):
        r = _record(importance_score=0.9, confidence=0.9)
        self.store.save(r)
        self.store.forget(retention_threshold=0.0)
        # Not expired, not below threshold
        self.assertEqual(self.store.health_check()["total_records"], 1)


# ---------------------------------------------------------------------------
# put() / get() / delete() tests
# ---------------------------------------------------------------------------
class TestWorkingMemoryStoreBasicOps(unittest.TestCase):

    def setUp(self):
        self.store = _store()

    def tearDown(self):
        self.store.close()

    def test_put_returns_memory_id(self):
        mid = self.store.put({"task": "analyze"}, session_id="s1", source_agent="planner")
        self.assertIsInstance(mid, str)
        self.assertTrue(len(mid) > 0)

    def test_put_then_get(self):
        mid = self.store.put({"fact": "sky is blue"}, source_agent="observer")
        record = self.store.get(mid)
        self.assertIsNotNone(record)
        self.assertEqual(record.payload["fact"], "sky is blue")

    def test_get_bumps_access_count(self):
        mid = self.store.put({"x": 1}, source_agent="a")
        # Access twice
        self.store.get(mid)
        self.store.get(mid)
        # Retrieve raw via include_expired to read access_count
        with self.store._lock:
            conn = self.store._get_conn()
            row = conn.execute(
                "SELECT access_count FROM working_memories WHERE memory_id=?", (mid,)
            ).fetchone()
        # 2 explicit gets + 1 from retrieve inside get = at least 2
        self.assertGreaterEqual(row["access_count"], 2)

    def test_get_missing_returns_none(self):
        result = self.store.get("does-not-exist")
        self.assertIsNone(result)

    def test_delete_removes_record(self):
        mid = self.store.put({"x": 1}, source_agent="a")
        deleted = self.store.delete(mid)
        self.assertTrue(deleted)
        self.assertIsNone(self.store.get(mid))

    def test_delete_missing_returns_false(self):
        result = self.store.delete("does-not-exist")
        self.assertFalse(result)

    def test_put_explicit_memory_id(self):
        mid = self.store.put({"x": 1}, source_agent="a", memory_id="my-id-123")
        self.assertEqual(mid, "my-id-123")
        self.assertIsNotNone(self.store.get("my-id-123"))


# ---------------------------------------------------------------------------
# Session and context tests
# ---------------------------------------------------------------------------
class TestWorkingMemoryStoreSession(unittest.TestCase):

    def setUp(self):
        self.store = _store()

    def tearDown(self):
        self.store.close()

    def test_get_active_context_only_own_session(self):
        self.store.put({"x": 1}, session_id="alice", source_agent="a")
        self.store.put({"x": 2}, session_id="bob", source_agent="a")
        ctx = self.store.get_active_context("alice")
        self.assertEqual(len(ctx), 1)
        self.assertEqual(ctx[0].payload["session_id"], "alice")

    def test_get_active_context_filters_expired(self):
        mid = self.store.put({"x": 1}, session_id="s1", source_agent="a")
        self.store.expire(mid)
        ctx = self.store.get_active_context("s1")
        self.assertEqual(len(ctx), 0)

    def test_get_goal_context(self):
        self.store.put({"x": 1}, goal_id="g-42", source_agent="a")
        self.store.put({"x": 2}, goal_id="g-99", source_agent="a")
        result = self.store.get_goal_context("g-42")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].payload["goal_id"], "g-42")

    def test_clear_session_removes_only_target(self):
        self.store.put({"x": 1}, session_id="s-alpha", source_agent="a")
        self.store.put({"x": 2}, session_id="s-beta", source_agent="a")
        count = self.store.clear_session("s-alpha")
        self.assertEqual(count, 1)
        self.assertEqual(len(self.store.get_active_context("s-alpha")), 0)
        self.assertEqual(len(self.store.get_active_context("s-beta")), 1)

    def test_clear_session_returns_zero_for_unknown(self):
        count = self.store.clear_session("nonexistent-session")
        self.assertEqual(count, 0)


# ---------------------------------------------------------------------------
# consolidate() tests
# ---------------------------------------------------------------------------
class TestWorkingMemoryStoreConsolidate(unittest.TestCase):

    def setUp(self):
        self.store = _store()

    def tearDown(self):
        self.store.close()

    def test_consolidate_returns_high_quality_records(self):
        self.store.put({"x": "important"}, session_id="s1", source_agent="a",
                       importance_score=0.9, confidence=0.95)
        self.store.put({"x": "noise"}, session_id="s1", source_agent="a",
                       importance_score=0.2, confidence=0.3)
        candidates = self.store.consolidate("s1")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].payload["x"], "important")

    def test_consolidate_excludes_expired(self):
        mid = self.store.put({"x": "hi"}, session_id="s1", source_agent="a",
                             importance_score=0.9, confidence=0.9)
        self.store.expire(mid)
        candidates = self.store.consolidate("s1")
        self.assertEqual(len(candidates), 0)

    def test_consolidate_session_isolation(self):
        self.store.put({"x": 1}, session_id="s1", source_agent="a",
                       importance_score=0.9, confidence=0.9)
        self.store.put({"x": 2}, session_id="s2", source_agent="a",
                       importance_score=0.9, confidence=0.9)
        candidates = self.store.consolidate("s1")
        self.assertEqual(len(candidates), 1)

    def test_consolidate_ordered_by_importance_desc(self):
        for imp in [0.7, 0.9, 0.8]:
            self.store.put({"imp": imp}, session_id="s1", source_agent="a",
                           importance_score=imp, confidence=0.9)
        candidates = self.store.consolidate("s1", min_importance=0.6)
        scores = [r.importance_score for r in candidates]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_consolidate_returns_memory_records(self):
        self.store.put({"x": 1}, session_id="s1", source_agent="a",
                       importance_score=0.9, confidence=0.9)
        candidates = self.store.consolidate("s1")
        self.assertIsInstance(candidates[0], MemoryRecord)


# ---------------------------------------------------------------------------
# health_check() tests
# ---------------------------------------------------------------------------
class TestWorkingMemoryStoreHealth(unittest.TestCase):

    def setUp(self):
        self.store = _store()

    def tearDown(self):
        self.store.close()

    def test_health_check_fields(self):
        health = self.store.health_check()
        self.assertIn("status", health)
        self.assertIn("memory_type", health)
        self.assertIn("total_records", health)
        self.assertIn("expired_records", health)
        self.assertIn("db_path", health)

    def test_health_check_counts_expired(self):
        mid = self.store.put({"x": 1}, source_agent="a")
        self.store.expire(mid)
        health = self.store.health_check()
        self.assertEqual(health["expired_records"], 1)
        self.assertEqual(health["total_records"], 1)

    def test_health_check_memory_type_value(self):
        health = self.store.health_check()
        self.assertEqual(health["memory_type"], "working")


# ---------------------------------------------------------------------------
# MemoryManager integration tests
# ---------------------------------------------------------------------------
class TestWorkingMemoryManagerIntegration(unittest.TestCase):

    def setUp(self):
        self.store = _store()
        self.manager = MemoryManager()
        self.manager.register(self.store)

    def tearDown(self):
        self.store.close()

    def test_manager_save_routes_to_store(self):
        r = _record()
        self.manager.save(r)
        self.assertEqual(self.store.health_check()["total_records"], 1)

    def test_manager_retrieve_delegates(self):
        r = _record(session_id="s-mgr")
        self.manager.save(r)
        results = self.manager.retrieve(MemoryType.WORKING, {"session_id": "s-mgr"})
        self.assertEqual(len(results), 1)

    def test_manager_forget_delegates(self):
        r = _record()
        self.manager.save(r)
        self.store.expire(r.memory_id)
        result = self.manager.forget(MemoryType.WORKING, retention_threshold=0.0)
        self.assertIn(MemoryType.WORKING, result)
        self.assertEqual(result[MemoryType.WORKING], 1)

    def test_manager_health_includes_working(self):
        health = self.manager.health()
        self.assertIn("working", health)

    def test_manager_has_store(self):
        self.assertTrue(self.manager.has_store(MemoryType.WORKING))


# ---------------------------------------------------------------------------
# Concurrent access tests
# ---------------------------------------------------------------------------
class TestWorkingMemoryStoreConcurrency(unittest.TestCase):

    def setUp(self):
        self.store = _store()

    def tearDown(self):
        self.store.close()

    def test_concurrent_writes_no_data_loss(self):
        errors: List[Exception] = []
        records_written = []

        def writer(n: int) -> None:
            try:
                for i in range(10):
                    mid = self.store.put(
                        {"thread": n, "i": i},
                        session_id=f"thread-{n}",
                        source_agent="writer",
                    )
                    records_written.append(mid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent write errors: {errors}")
        self.assertEqual(self.store.health_check()["total_records"], 50)

    def test_concurrent_reads_and_writes(self):
        errors: List[Exception] = []

        def writer() -> None:
            try:
                for _ in range(20):
                    self.store.put({"x": 1}, source_agent="w")
            except Exception as e:
                errors.append(e)

        def reader() -> None:
            try:
                for _ in range(20):
                    self.store.retrieve({}, limit=5)
            except Exception as e:
                errors.append(e)

        threads = (
            [threading.Thread(target=writer) for _ in range(3)] +
            [threading.Thread(target=reader) for _ in range(3)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent read/write errors: {errors}")


if __name__ == "__main__":
    unittest.main()
