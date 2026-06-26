"""
Tests for Step 22 (Learning Engine) + Step 23 (Skill Memory)
=============================================================

Covers:
  Step 22 — Learning Engine
    - LearningRecord schema roundtrip
    - RecordType classification (rule / pattern / knowledge / skill_gap / skill_win)
    - Priority escalation for skill gaps
    - Deduplication + frequency reinforcement in LearningStore
    - EMA success_rate update in LearningStore
    - Knowledge distillation (rule-based and custom hook)
    - Semantic memory promotion on every learn_from()
    - Skill Memory update called when attached

  Step 23 — Skill Memory
    - record_attempt increments counters + clamps confidence
    - success_rate computed property
    - learning_velocity EMA
    - add_weakness deduplication
    - weakest / strongest skill queries
    - summary_table non-empty string output
    - JSON persistence across instances
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from kattappa_runtime.reflection.schema import Reflection, OutcomeLabel
from kattappa_runtime.learning.schema import (
    LearningRecord, RecordType, LearningPriority
)
from kattappa_runtime.learning.store  import LearningStore
from kattappa_runtime.learning.engine import LearningEngine
from kattappa_runtime.skill_memory.store import SkillMemory, SkillProfile


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def make_reflection(
    domain="translation",
    succeeded=True,
    partial=False,
    lesson="default lesson text",
    outcome=None,
) -> Reflection:
    if outcome is None:
        if not succeeded:
            outcome = OutcomeLabel.FAILURE
        elif partial:
            outcome = OutcomeLabel.PARTIAL
        else:
            outcome = OutcomeLabel.SUCCESS

    return Reflection(
        domain=domain,
        input_text="test input",
        action_taken="test action",
        result="test result",
        outcome=outcome,
        lesson=lesson,
        confidence_delta=+0.05 if succeeded and not partial else (-0.02 if partial else -0.10),
        is_mistake=(outcome != OutcomeLabel.SUCCESS),
    )


@pytest.fixture
def mock_memory():
    mem = MagicMock()
    mem.writer = MagicMock()
    mem.writer.store_fact = MagicMock()
    mem.writer.store_episode = MagicMock()
    return mem


@pytest.fixture
def tmp_store(tmp_path):
    return LearningStore(path=str(tmp_path / "learning.jsonl"))


@pytest.fixture
def tmp_skill_mem(tmp_path):
    return SkillMemory(path=str(tmp_path / "skills.json"))


@pytest.fixture
def engine(mock_memory, tmp_store, tmp_skill_mem):
    return LearningEngine(
        memory=mock_memory,
        skill_memory=tmp_skill_mem,
        store=tmp_store,
    )


# ===========================================================================
# STEP 22: LearningRecord Schema
# ===========================================================================

class TestLearningRecordSchema:
    def test_default_fields(self):
        r = LearningRecord()
        assert r.record_id            # UUID populated
        assert r.record_type == RecordType.KNOWLEDGE
        assert r.priority == LearningPriority.MEDIUM
        assert r.frequency == 1
        assert r.success_rate == -1.0

    def test_to_dict_roundtrip(self):
        r = LearningRecord(
            domain="rf_systems",
            record_type=RecordType.SKILL_GAP,
            priority=LearningPriority.HIGH,
            knowledge="impedance matching must be validated first",
            confidence=0.4,
            importance=0.85,
        )
        d = r.to_dict()
        assert d["record_type"] == "skill_gap"
        assert d["priority"]    == "high"

        r2 = LearningRecord.from_dict(d)
        assert r2.domain       == "rf_systems"
        assert r2.record_type  == RecordType.SKILL_GAP
        assert r2.priority     == LearningPriority.HIGH
        assert r2.confidence   == pytest.approx(0.4)


# ===========================================================================
# STEP 22: RecordType Classification
# ===========================================================================

class TestRecordTypeClassification:
    def test_failure_with_gap_keywords_is_skill_gap(self, engine):
        r = make_reflection(
            succeeded=False,
            lesson="Insufficient understanding of impedance matching"
        )
        record = engine.learn_from(r)
        assert record.record_type == RecordType.SKILL_GAP

    def test_failure_without_gap_keywords_is_rule(self, engine):
        r = make_reflection(
            succeeded=False,
            lesson="Model returned wrong token sequence"
        )
        record = engine.learn_from(r)
        assert record.record_type == RecordType.RULE

    def test_success_with_rule_keyword_is_rule(self, engine):
        r = make_reflection(
            succeeded=True,
            lesson="Always validate input before calling translation API"
        )
        record = engine.learn_from(r)
        assert record.record_type == RecordType.RULE

    def test_success_without_rule_keyword_is_skill_win(self, engine):
        r = make_reflection(
            succeeded=True,
            lesson="Translation model succeeded on short input"
        )
        record = engine.learn_from(r)
        assert record.record_type == RecordType.SKILL_WIN

    def test_partial_with_rule_keyword_is_rule(self, engine):
        r = make_reflection(
            succeeded=True, partial=True,
            lesson="Should validate before calling, but only partial result"
        )
        record = engine.learn_from(r)
        assert record.record_type == RecordType.RULE

    def test_partial_without_rule_keyword_is_pattern(self, engine):
        r = make_reflection(
            succeeded=True, partial=True,
            lesson="Translation succeeded for short texts, failed for long"
        )
        record = engine.learn_from(r)
        assert record.record_type == RecordType.PATTERN


# ===========================================================================
# STEP 22: Priority Escalation
# ===========================================================================

class TestPriorityEscalation:
    def test_skill_gap_always_at_least_high(self, engine):
        # Failure with gap keywords → SKILL_GAP, and priority must be at least HIGH
        r = make_reflection(
            succeeded=False,
            lesson="Missing understanding of RF fundamentals"
        )
        record = engine.learn_from(r)
        assert record.record_type == RecordType.SKILL_GAP
        assert record.priority in (LearningPriority.HIGH, LearningPriority.CRITICAL)

    def test_failure_without_gap_is_high_priority(self, engine):
        r = make_reflection(succeeded=False, lesson="Model failed to tokenize correctly")
        record = engine.learn_from(r)
        assert record.priority == LearningPriority.HIGH

    def test_success_is_low_priority(self, engine):
        r = make_reflection(succeeded=True, lesson="Translation produced correct output")
        record = engine.learn_from(r)
        assert record.priority == LearningPriority.LOW


# ===========================================================================
# STEP 22: LearningStore — deduplication + reinforcement
# ===========================================================================

class TestLearningStoreDeduplication:
    def test_duplicate_increments_frequency(self, tmp_store):
        r = LearningRecord(
            domain="translation",
            knowledge="Always validate input tokens before decoding.",
        )
        saved1 = tmp_store.save(r)
        assert saved1.frequency == 1

        # Same domain + knowledge → should reinforce
        r2 = LearningRecord(
            domain="translation",
            knowledge="Always validate input tokens before decoding.",
        )
        saved2 = tmp_store.save(r2)
        assert saved2.record_id == saved1.record_id
        assert saved2.frequency == 2

    def test_duplicate_nudges_confidence_up(self, tmp_store):
        r = LearningRecord(domain="code", knowledge="Must write tests first.", confidence=0.5)
        saved1 = tmp_store.save(r)

        r2 = LearningRecord(domain="code", knowledge="Must write tests first.", confidence=0.5)
        saved2 = tmp_store.save(r2)
        assert saved2.confidence > 0.5

    def test_duplicate_upgrades_priority(self, tmp_store):
        r1 = LearningRecord(domain="x", knowledge="X rule.", priority=LearningPriority.LOW)
        tmp_store.save(r1)

        r2 = LearningRecord(domain="x", knowledge="X rule.", priority=LearningPriority.HIGH)
        saved = tmp_store.save(r2)
        assert saved.priority == LearningPriority.HIGH

    def test_different_knowledge_creates_new_record(self, tmp_store):
        tmp_store.save(LearningRecord(domain="d", knowledge="Fact A."))
        tmp_store.save(LearningRecord(domain="d", knowledge="Fact B."))
        assert tmp_store.count() == 2

    def test_persistence_across_instances(self, tmp_path):
        path = str(tmp_path / "l.jsonl")
        s1 = LearningStore(path=path)
        s1.save(LearningRecord(domain="p", knowledge="Test persistence."))

        s2 = LearningStore(path=path)
        assert s2.count() == 1

    def test_success_rate_ema_update(self, tmp_store):
        r = LearningRecord(domain="t", knowledge="EMA test rule.")
        saved = tmp_store.save(r)
        assert saved.success_rate == -1.0  # unobserved

        tmp_store.update_success_rate(saved.record_id, observed_success=True)
        updated = tmp_store.get_by_domain("t")[0]
        assert updated.success_rate == pytest.approx(1.0)

        tmp_store.update_success_rate(saved.record_id, observed_success=False)
        updated = tmp_store.get_by_domain("t")[0]
        assert 0.0 < updated.success_rate < 1.0


# ===========================================================================
# STEP 22: LearningEngine integration
# ===========================================================================

class TestLearningEngineIntegration:
    def test_learn_from_returns_record(self, engine):
        r = make_reflection(succeeded=True)
        record = engine.learn_from(r)
        assert isinstance(record, LearningRecord)
        assert record.knowledge  # non-empty

    def test_semantic_memory_promoted_on_every_learn(self, engine, mock_memory):
        engine.learn_from(make_reflection(succeeded=True))
        mock_memory.writer.store_fact.assert_called_once()

    def test_source_reflection_id_preserved(self, engine):
        rf = make_reflection(succeeded=False)
        record = engine.learn_from(rf)
        assert record.source_reflection_id == rf.reflection_id

    def test_next_review_set(self, engine):
        rf = make_reflection(succeeded=False)
        record = engine.learn_from(rf)
        assert record.next_review  # non-empty ISO timestamp

    def test_custom_distiller_hook(self, mock_memory, tmp_store, tmp_skill_mem):
        def my_distil(r: Reflection) -> str:
            return "Custom knowledge!"

        eng = LearningEngine(
            memory=mock_memory,
            skill_memory=tmp_skill_mem,
            store=tmp_store,
            knowledge_distiller=my_distil,
        )
        record = eng.learn_from(make_reflection(succeeded=True))
        assert record.knowledge == "Custom knowledge!"

    def test_distiller_hook_fallback_on_error(self, mock_memory, tmp_store, tmp_skill_mem):
        def bad_distil(r):
            raise RuntimeError("LLM unavailable")

        eng = LearningEngine(
            memory=mock_memory,
            skill_memory=tmp_skill_mem,
            store=tmp_store,
            knowledge_distiller=bad_distil,
        )
        record = eng.learn_from(make_reflection(succeeded=True))
        assert len(record.knowledge) > 5  # fallback produced something

    def test_skill_memory_updated(self, engine, tmp_skill_mem):
        engine.learn_from(make_reflection(domain="python", succeeded=True))
        profile = tmp_skill_mem.get("python")
        assert profile is not None
        assert profile.attempts == 1
        assert profile.successes == 1

    def test_weakness_added_for_skill_gap(self, engine, tmp_skill_mem):
        r = make_reflection(
            domain="rf_systems",
            succeeded=False,
            lesson="Insufficient understanding of impedance matching"
        )
        engine.learn_from(r)
        profile = tmp_skill_mem.get("rf_systems")
        assert profile is not None
        assert len(profile.weaknesses) >= 1


# ===========================================================================
# STEP 23: Skill Memory
# ===========================================================================

class TestSkillProfile:
    def test_success_rate_no_attempts(self):
        p = SkillProfile(domain="x")
        assert p.success_rate == -1.0

    def test_success_rate_computed(self):
        p = SkillProfile(domain="x", attempts=10, successes=8)
        assert p.success_rate == pytest.approx(0.8)

    def test_confidence_labels(self):
        assert SkillProfile(domain="x", confidence=0.90).confidence_label == "Expert"
        assert SkillProfile(domain="x", confidence=0.72).confidence_label == "Proficient"
        assert SkillProfile(domain="x", confidence=0.55).confidence_label == "Developing"
        assert SkillProfile(domain="x", confidence=0.40).confidence_label == "Beginner"
        assert SkillProfile(domain="x", confidence=0.10).confidence_label == "Critical Gap"

    def test_to_dict_roundtrip(self):
        p = SkillProfile(domain="translation", confidence=0.75, attempts=5, successes=4)
        d = p.to_dict()
        assert d["success_rate"] == pytest.approx(0.8)
        assert d["confidence_label"] == "Proficient"

        p2 = SkillProfile.from_dict(d)
        assert p2.domain == "translation"
        assert p2.confidence == pytest.approx(0.75)
        assert p2.attempts == 5


class TestSkillMemory:
    def test_record_attempt_increments(self, tmp_skill_mem):
        tmp_skill_mem.record_attempt("python", succeeded=True, confidence_delta=+0.05)
        p = tmp_skill_mem.get("python")
        assert p.attempts == 1
        assert p.successes == 1

    def test_record_failure_no_success_increment(self, tmp_skill_mem):
        tmp_skill_mem.record_attempt("python", succeeded=False, confidence_delta=-0.10)
        p = tmp_skill_mem.get("python")
        assert p.attempts == 1
        assert p.successes == 0

    def test_confidence_clamped_upper(self, tmp_skill_mem):
        tmp_skill_mem._profiles["x"] = SkillProfile(domain="x", confidence=0.98)
        tmp_skill_mem.record_attempt("x", succeeded=True, confidence_delta=+0.10)
        assert tmp_skill_mem.get("x").confidence == pytest.approx(1.0)

    def test_confidence_clamped_lower(self, tmp_skill_mem):
        tmp_skill_mem._profiles["x"] = SkillProfile(domain="x", confidence=0.05)
        tmp_skill_mem.record_attempt("x", succeeded=False, confidence_delta=-0.20)
        assert tmp_skill_mem.get("x").confidence == pytest.approx(0.0)

    def test_learning_velocity_updated(self, tmp_skill_mem):
        tmp_skill_mem.record_attempt("v", succeeded=True, confidence_delta=+0.05)
        p = tmp_skill_mem.get("v")
        assert p.learning_velocity != 0.0

    def test_add_weakness_deduplication(self, tmp_skill_mem):
        tmp_skill_mem.add_weakness("rf", "impedance matching")
        tmp_skill_mem.add_weakness("rf", "impedance matching")  # duplicate
        tmp_skill_mem.add_weakness("rf", "IMPEDANCE MATCHING")  # case-insensitive dup
        p = tmp_skill_mem.get("rf")
        assert len(p.weaknesses) == 1

    def test_add_multiple_unique_weaknesses(self, tmp_skill_mem):
        tmp_skill_mem.add_weakness("rf", "impedance matching")
        tmp_skill_mem.add_weakness("rf", "antenna gain calculation")
        p = tmp_skill_mem.get("rf")
        assert len(p.weaknesses) == 2

    def test_weakest_skills(self, tmp_skill_mem):
        for domain, conf in [("a", 0.9), ("b", 0.3), ("c", 0.5)]:
            tmp_skill_mem._profiles[domain] = SkillProfile(domain=domain, confidence=conf)
        tmp_skill_mem._save()
        weakest = tmp_skill_mem.weakest_skills(n=1)
        assert weakest[0].domain == "b"

    def test_strongest_skills(self, tmp_skill_mem):
        for domain, conf in [("a", 0.9), ("b", 0.3), ("c", 0.5)]:
            tmp_skill_mem._profiles[domain] = SkillProfile(domain=domain, confidence=conf)
        tmp_skill_mem._save()
        strongest = tmp_skill_mem.strongest_skills(n=1)
        assert strongest[0].domain == "a"

    def test_summary_table_non_empty(self, tmp_skill_mem):
        tmp_skill_mem.record_attempt("python", succeeded=True, confidence_delta=+0.05)
        table = tmp_skill_mem.summary_table()
        assert "python" in table
        assert "Developing" in table or "Proficient" in table or "Expert" in table

    def test_summary_table_no_skills(self, tmp_skill_mem):
        assert "No skills" in tmp_skill_mem.summary_table()

    def test_persistence_across_instances(self, tmp_path):
        p = str(tmp_path / "s.json")
        sm1 = SkillMemory(path=p)
        sm1.record_attempt("git", succeeded=True, confidence_delta=+0.05)

        sm2 = SkillMemory(path=p)
        assert sm2.get("git") is not None
        assert sm2.get("git").attempts == 1

    def test_get_returns_none_for_unknown(self, tmp_skill_mem):
        assert tmp_skill_mem.get("unknown_domain_xyz") is None

    def test_get_or_default_creates_profile(self, tmp_skill_mem):
        p = tmp_skill_mem.get_or_default("brand_new_skill")
        assert p.domain == "brand_new_skill"
        assert p.confidence == pytest.approx(0.6)
