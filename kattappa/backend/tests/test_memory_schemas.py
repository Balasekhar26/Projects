"""
test_memory_schemas.py

Unit tests for Phase 1A of the Kattappa Persistent Memory Engine.

Covers:
  - MemoryType enum values and ordering invariants.
  - MemoryRecord construction with auto-populated identity fields.
  - MemoryRecord validation bounds on confidence and importance_score.
  - Serialization/deserialization round-trip (to_dict/from_dict, to_json/from_json).
  - Derived property correctness (default_ttl, is_permanent, retention_score).
  - IMemoryStore ABC enforcement.
  - MemoryManager registration, routing, unregistration, and health reporting.
  - MemoryManager.save routing to the correct store.
  - MemoryManager.retrieve and MemoryManager.forget delegation.
  - MemoryManager error handling for unregistered types.
"""

from __future__ import annotations

import json
import time
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

from backend.core.memory.schemas import MemoryRecord, MemoryType, DEFAULT_TTL
from backend.core.memory.memory_manager import IMemoryStore, MemoryManager


# ---------------------------------------------------------------------------
# Minimal concrete store for testing
# ---------------------------------------------------------------------------
class _InMemoryStore(IMemoryStore):
    memory_type = MemoryType.EPISODIC

    def __init__(self):
        self._records: List[MemoryRecord] = []
        self._forget_calls: List[float] = []

    def save(self, record: MemoryRecord) -> None:
        self._records.append(record)

    def retrieve(self, query: Dict[str, Any], limit: int = 20) -> List[MemoryRecord]:
        return self._records[-limit:]

    def forget(self, retention_threshold: float = 0.0) -> int:
        self._forget_calls.append(retention_threshold)
        before = len(self._records)
        self._records = [
            r for r in self._records
            if r.retention_score() > retention_threshold
        ]
        return before - len(self._records)


class _PermanentStore(IMemoryStore):
    memory_type = MemoryType.PROCEDURAL

    def save(self, record: MemoryRecord) -> None:
        pass

    def retrieve(self, query: Dict[str, Any], limit: int = 20) -> List[MemoryRecord]:
        return []

    def forget(self, retention_threshold: float = 0.0) -> int:
        return 0  # permanent — nothing forgotten


# ---------------------------------------------------------------------------
# MemoryType tests
# ---------------------------------------------------------------------------
class TestMemoryType(unittest.TestCase):

    def test_all_types_defined(self):
        expected = {"working", "episodic", "reflection", "semantic", "procedural", "policy"}
        actual = {mt.value for mt in MemoryType}
        self.assertEqual(actual, expected)

    def test_str_enum_values(self):
        """MemoryType inherits str so it can be stored directly as a string."""
        self.assertEqual(MemoryType.EPISODIC, "episodic")
        self.assertEqual(MemoryType.PROCEDURAL, "procedural")

    def test_default_ttl_coverage(self):
        """Every MemoryType must have a DEFAULT_TTL entry."""
        for mt in MemoryType:
            self.assertIn(mt, DEFAULT_TTL, f"DEFAULT_TTL missing entry for {mt}")

    def test_permanent_types_have_none_ttl(self):
        self.assertIsNone(DEFAULT_TTL[MemoryType.PROCEDURAL])
        self.assertIsNone(DEFAULT_TTL[MemoryType.POLICY])

    def test_transient_types_have_positive_ttl(self):
        for mt in [MemoryType.WORKING, MemoryType.EPISODIC, MemoryType.REFLECTION, MemoryType.SEMANTIC]:
            ttl = DEFAULT_TTL[mt]
            self.assertIsNotNone(ttl)
            self.assertGreater(ttl, 0)


# ---------------------------------------------------------------------------
# MemoryRecord construction tests
# ---------------------------------------------------------------------------
class TestMemoryRecordConstruction(unittest.TestCase):

    def _make_record(self, **kwargs) -> MemoryRecord:
        defaults = dict(
            memory_type=MemoryType.EPISODIC,
            source_agent="test_agent",
            payload={"goal": "test"},
        )
        defaults.update(kwargs)
        return MemoryRecord(**defaults)

    def test_auto_memory_id(self):
        r = self._make_record()
        self.assertIsNotNone(r.memory_id)
        self.assertIsInstance(r.memory_id, str)
        self.assertTrue(len(r.memory_id) > 0)

    def test_two_records_have_different_ids(self):
        r1 = self._make_record()
        r2 = self._make_record()
        self.assertNotEqual(r1.memory_id, r2.memory_id)

    def test_auto_timestamp(self):
        before = time.time()
        r = self._make_record()
        after = time.time()
        self.assertGreaterEqual(r.timestamp, before)
        self.assertLessEqual(r.timestamp, after)

    def test_explicit_memory_id(self):
        r = self._make_record(memory_id="fixed-id-123")
        self.assertEqual(r.memory_id, "fixed-id-123")

    def test_default_confidence_and_importance(self):
        r = self._make_record()
        self.assertEqual(r.confidence, 1.0)
        self.assertEqual(r.importance_score, 0.5)

    def test_tags_normalized_to_strings(self):
        r = self._make_record(tags=["alpha", 42, True])
        self.assertEqual(r.tags, ["alpha", "42", "True"])

    def test_default_tags_empty_list(self):
        r = self._make_record()
        self.assertEqual(r.tags, [])

    def test_embedding_id_defaults_none(self):
        r = self._make_record()
        self.assertIsNone(r.embedding_id)


# ---------------------------------------------------------------------------
# MemoryRecord validation tests
# ---------------------------------------------------------------------------
class TestMemoryRecordValidation(unittest.TestCase):

    def _make_record(self, **kwargs) -> MemoryRecord:
        defaults = dict(
            memory_type=MemoryType.WORKING,
            source_agent="agent_x",
            payload={},
        )
        defaults.update(kwargs)
        return MemoryRecord(**defaults)

    def test_confidence_zero_is_valid(self):
        r = self._make_record(confidence=0.0)
        self.assertEqual(r.confidence, 0.0)

    def test_confidence_one_is_valid(self):
        r = self._make_record(confidence=1.0)
        self.assertEqual(r.confidence, 1.0)

    def test_confidence_below_zero_raises(self):
        with self.assertRaises(ValueError):
            self._make_record(confidence=-0.01)

    def test_confidence_above_one_raises(self):
        with self.assertRaises(ValueError):
            self._make_record(confidence=1.01)

    def test_importance_below_zero_raises(self):
        with self.assertRaises(ValueError):
            self._make_record(importance_score=-0.1)

    def test_importance_above_one_raises(self):
        with self.assertRaises(ValueError):
            self._make_record(importance_score=1.5)

    def test_invalid_memory_type_raises(self):
        with self.assertRaises(TypeError):
            self._make_record(memory_type="not_a_type")  # type: ignore[arg-type]

    def test_empty_source_agent_raises(self):
        with self.assertRaises(ValueError):
            self._make_record(source_agent="")

    def test_whitespace_source_agent_raises(self):
        with self.assertRaises(ValueError):
            self._make_record(source_agent="   ")

    def test_non_dict_payload_raises(self):
        with self.assertRaises(TypeError):
            self._make_record(payload="not a dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Serialization round-trip tests
# ---------------------------------------------------------------------------
class TestMemoryRecordSerialization(unittest.TestCase):

    def _sample(self) -> MemoryRecord:
        return MemoryRecord(
            memory_id="abc-123",
            memory_type=MemoryType.SEMANTIC,
            timestamp=1_700_000_000.0,
            source_agent="semantic_extractor",
            confidence=0.97,
            importance_score=0.8,
            tags=["fastapi", "uvicorn"],
            embedding_id="emb-xyz",
            payload={"fact": "FastAPI runs on uvicorn"},
        )

    def test_to_dict_contains_all_fields(self):
        r = self._sample()
        d = r.to_dict()
        self.assertEqual(d["memory_id"], "abc-123")
        self.assertEqual(d["memory_type"], "semantic")
        self.assertEqual(d["timestamp"], 1_700_000_000.0)
        self.assertEqual(d["source_agent"], "semantic_extractor")
        self.assertAlmostEqual(d["confidence"], 0.97)
        self.assertAlmostEqual(d["importance_score"], 0.8)
        self.assertEqual(d["tags"], ["fastapi", "uvicorn"])
        self.assertEqual(d["embedding_id"], "emb-xyz")
        self.assertEqual(d["payload"], {"fact": "FastAPI runs on uvicorn"})

    def test_to_dict_memory_type_is_string(self):
        r = self._sample()
        d = r.to_dict()
        self.assertIsInstance(d["memory_type"], str)

    def test_from_dict_round_trip(self):
        r = self._sample()
        r2 = MemoryRecord.from_dict(r.to_dict())
        self.assertEqual(r2.memory_id, r.memory_id)
        self.assertEqual(r2.memory_type, r.memory_type)
        self.assertAlmostEqual(r2.timestamp, r.timestamp)
        self.assertEqual(r2.source_agent, r.source_agent)
        self.assertAlmostEqual(r2.confidence, r.confidence)
        self.assertAlmostEqual(r2.importance_score, r.importance_score)
        self.assertEqual(r2.tags, r.tags)
        self.assertEqual(r2.embedding_id, r.embedding_id)
        self.assertEqual(r2.payload, r.payload)

    def test_to_json_is_valid_json(self):
        r = self._sample()
        j = r.to_json()
        parsed = json.loads(j)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed["memory_id"], "abc-123")

    def test_from_json_round_trip(self):
        r = self._sample()
        r2 = MemoryRecord.from_json(r.to_json())
        self.assertEqual(r2.memory_id, r.memory_id)
        self.assertEqual(r2.payload, r.payload)

    def test_from_dict_uses_defaults_for_optional_fields(self):
        minimal = {
            "memory_id": "m-001",
            "memory_type": "working",
            "timestamp": 1_000_000.0,
            "source_agent": "test",
            "payload": {},
        }
        r = MemoryRecord.from_dict(minimal)
        self.assertEqual(r.confidence, 1.0)
        self.assertEqual(r.importance_score, 0.5)
        self.assertEqual(r.tags, [])
        self.assertIsNone(r.embedding_id)


# ---------------------------------------------------------------------------
# Derived property tests
# ---------------------------------------------------------------------------
class TestMemoryRecordProperties(unittest.TestCase):

    def test_permanent_type_is_permanent(self):
        r = MemoryRecord(
            memory_type=MemoryType.PROCEDURAL,
            source_agent="skill_builder",
            payload={},
        )
        self.assertTrue(r.is_permanent)
        self.assertIsNone(r.default_ttl)

    def test_transient_type_is_not_permanent(self):
        r = MemoryRecord(
            memory_type=MemoryType.WORKING,
            source_agent="goal_manager",
            payload={},
        )
        self.assertFalse(r.is_permanent)
        self.assertIsNotNone(r.default_ttl)

    def test_retention_score_of_fresh_record(self):
        r = MemoryRecord(
            memory_type=MemoryType.EPISODIC,
            source_agent="exec",
            payload={},
            confidence=1.0,
            importance_score=1.0,
        )
        score = r.retention_score(now=r.timestamp + 1)  # 1 second old
        self.assertGreater(score, 0.99)

    def test_retention_score_of_expired_record(self):
        r = MemoryRecord(
            memory_type=MemoryType.WORKING,
            source_agent="exec",
            payload={},
            confidence=1.0,
            importance_score=1.0,
        )
        # Simulate record aged well past its TTL
        past_expiry = r.timestamp + DEFAULT_TTL[MemoryType.WORKING] + 3600
        score = r.retention_score(now=past_expiry)
        self.assertEqual(score, 0.0)

    def test_permanent_record_retention_score_always_one(self):
        r = MemoryRecord(
            memory_type=MemoryType.POLICY,
            source_agent="safety_monitor",
            payload={"rule": "no harm"},
        )
        for delta in [0, 1_000_000, 1_000_000_000]:
            score = r.retention_score(now=r.timestamp + delta)
            self.assertEqual(score, 1.0)

    def test_retention_score_scales_with_importance(self):
        base = dict(memory_type=MemoryType.EPISODIC, source_agent="a", payload={})
        low = MemoryRecord(**base, importance_score=0.2, confidence=1.0)
        high = MemoryRecord(**base, importance_score=0.9, confidence=1.0)
        # Both fresh
        now = low.timestamp + 1
        self.assertLess(low.retention_score(now), high.retention_score(now))


# ---------------------------------------------------------------------------
# IMemoryStore ABC enforcement tests
# ---------------------------------------------------------------------------
class TestIMemoryStoreABC(unittest.TestCase):

    def test_cannot_instantiate_abstract_base(self):
        with self.assertRaises(TypeError):
            IMemoryStore()  # type: ignore[abstract]

    def test_concrete_store_works(self):
        store = _InMemoryStore()
        self.assertIsNotNone(store)

    def test_health_check_default_implementation(self):
        store = _InMemoryStore()
        health = store.health_check()
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["memory_type"], "episodic")


# ---------------------------------------------------------------------------
# MemoryManager tests
# ---------------------------------------------------------------------------
class TestMemoryManagerRegistration(unittest.TestCase):

    def test_register_and_has_store(self):
        mgr = MemoryManager()
        store = _InMemoryStore()
        mgr.register(store)
        self.assertTrue(mgr.has_store(MemoryType.EPISODIC))

    def test_unregister_removes_store(self):
        mgr = MemoryManager()
        mgr.register(_InMemoryStore())
        mgr.unregister(MemoryType.EPISODIC)
        self.assertFalse(mgr.has_store(MemoryType.EPISODIC))

    def test_unregister_nonexistent_is_silent(self):
        mgr = MemoryManager()
        mgr.unregister(MemoryType.WORKING)  # no error expected

    def test_register_non_store_raises(self):
        mgr = MemoryManager()
        with self.assertRaises(TypeError):
            mgr.register("not a store")  # type: ignore[arg-type]

    def test_register_store_without_memory_type_raises(self):
        class BadStore(IMemoryStore):
            def save(self, record): pass
            def retrieve(self, query, limit=20): return []
            def forget(self, threshold=0.0): return 0

        mgr = MemoryManager()
        with self.assertRaises(TypeError):
            mgr.register(BadStore())

    def test_double_register_replaces_store(self):
        mgr = MemoryManager()
        store_a = _InMemoryStore()
        store_b = _InMemoryStore()
        mgr.register(store_a)
        mgr.register(store_b)
        self.assertIs(mgr.get_store(MemoryType.EPISODIC), store_b)


class TestMemoryManagerRouting(unittest.TestCase):

    def setUp(self):
        self.mgr = MemoryManager()
        self.epi_store = _InMemoryStore()
        self.proc_store = _PermanentStore()
        self.mgr.register(self.epi_store)
        self.mgr.register(self.proc_store)

    def _episodic_record(self) -> MemoryRecord:
        return MemoryRecord(
            memory_type=MemoryType.EPISODIC,
            source_agent="test",
            payload={"episode": "deploy success"},
        )

    def test_save_routes_to_correct_store(self):
        r = self._episodic_record()
        self.mgr.save(r)
        self.assertIn(r, self.epi_store._records)

    def test_save_non_record_raises(self):
        with self.assertRaises(TypeError):
            self.mgr.save("not a record")  # type: ignore[arg-type]

    def test_save_unregistered_type_raises(self):
        r = MemoryRecord(
            memory_type=MemoryType.SEMANTIC,
            source_agent="sem",
            payload={"fact": "x"},
        )
        with self.assertRaises(KeyError):
            self.mgr.save(r)

    def test_retrieve_delegates_to_store(self):
        r = self._episodic_record()
        self.mgr.save(r)
        results = self.mgr.retrieve(MemoryType.EPISODIC, {})
        self.assertIn(r, results)

    def test_retrieve_unregistered_type_raises(self):
        with self.assertRaises(KeyError):
            self.mgr.retrieve(MemoryType.WORKING, {})

    def test_forget_specific_type(self):
        r = MemoryRecord(
            memory_type=MemoryType.EPISODIC,
            source_agent="test",
            payload={},
            importance_score=0.0,
            confidence=0.0,
        )
        self.mgr.save(r)
        result = self.mgr.forget(MemoryType.EPISODIC, retention_threshold=0.0)
        self.assertIn(MemoryType.EPISODIC, result)

    def test_forget_all_types(self):
        result = self.mgr.forget(retention_threshold=0.0)
        self.assertIn(MemoryType.EPISODIC, result)
        self.assertIn(MemoryType.PROCEDURAL, result)

    def test_health_reports_all_stores(self):
        health = self.mgr.health()
        self.assertIn("episodic", health)
        self.assertIn("procedural", health)

    def test_repr_shows_registered_types(self):
        r = repr(self.mgr)
        self.assertIn("episodic", r)
        self.assertIn("procedural", r)


if __name__ == "__main__":
    unittest.main()
