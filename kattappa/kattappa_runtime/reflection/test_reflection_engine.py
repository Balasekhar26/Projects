"""
Tests for Step 21 — Reflection Engine
======================================
Covers:
  - Outcome classification (success / partial / failure)
  - Confidence delta application (bounds respected)
  - Episodic memory write called with correct importance
  - Semantic lesson promotion only on SUCCESS
  - Mistake logging only on PARTIAL / FAILURE
  - Rule-based lesson text formatting
  - from_dict / to_dict roundtrip on Reflection schema
"""

import pytest
from unittest.mock import MagicMock, patch, call

from kattappa_runtime.reflection.schema import Reflection, OutcomeLabel
from kattappa_runtime.reflection.confidence import ConfidenceTracker
from kattappa_runtime.reflection.mistake_log import MistakeLog
from kattappa_runtime.reflection.engine import ReflectionEngine, _shorten


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_memory():
    """A mock MemoryProvider with writer sub-object."""
    mem = MagicMock()
    mem.writer = MagicMock()
    mem.writer.store_episode = MagicMock()
    mem.writer.store_fact = MagicMock()
    return mem


@pytest.fixture()
def tmp_confidence(tmp_path):
    return ConfidenceTracker(persist_path=str(tmp_path / "conf.json"))


@pytest.fixture()
def tmp_mistakes(tmp_path):
    return MistakeLog(path=str(tmp_path / "mistakes.jsonl"))


@pytest.fixture()
def engine(mock_memory, tmp_confidence, tmp_mistakes):
    return ReflectionEngine(
        memory=mock_memory,
        confidence_tracker=tmp_confidence,
        mistake_log=tmp_mistakes,
    )


# ---------------------------------------------------------------------------
# Schema: Reflection dataclass
# ---------------------------------------------------------------------------

class TestReflectionSchema:
    def test_default_fields(self):
        r = Reflection()
        assert r.outcome == OutcomeLabel.SUCCESS
        assert r.is_mistake is False
        assert r.confidence_delta == 0.0
        assert r.reflection_id  # UUID populated

    def test_to_dict_roundtrip(self):
        r = Reflection(
            domain="translation",
            input_text="hello",
            action_taken="call model",
            result="నమస్కారం",
            outcome=OutcomeLabel.FAILURE,
            lesson="model failed on short input",
            confidence_delta=-0.10,
            is_mistake=True,
        )
        d = r.to_dict()
        assert d["outcome"] == "failure"
        assert d["is_mistake"] is True

        r2 = Reflection.from_dict(d)
        assert r2.outcome == OutcomeLabel.FAILURE
        assert r2.domain == "translation"
        assert r2.is_mistake is True


# ---------------------------------------------------------------------------
# ConfidenceTracker
# ---------------------------------------------------------------------------

class TestConfidenceTracker:
    def test_default_confidence(self, tmp_confidence):
        assert tmp_confidence.get("unknown_domain") == pytest.approx(0.6)

    def test_update_clamps_upper(self, tmp_confidence):
        tmp_confidence._scores["domain_x"] = 0.98
        new_val = tmp_confidence.update("domain_x", +0.10)
        assert new_val == pytest.approx(1.0)

    def test_update_clamps_lower(self, tmp_confidence):
        tmp_confidence._scores["domain_y"] = 0.05
        new_val = tmp_confidence.update("domain_y", -0.20)
        assert new_val == pytest.approx(0.0)

    def test_persistence(self, tmp_path):
        p = str(tmp_path / "c.json")
        t1 = ConfidenceTracker(persist_path=p)
        t1.update("code", +0.10)

        t2 = ConfidenceTracker(persist_path=p)
        assert t2.get("code") == pytest.approx(0.70)

    def test_reset(self, tmp_confidence):
        tmp_confidence.update("yyy", +0.30)
        tmp_confidence.reset("yyy")
        assert tmp_confidence.get("yyy") == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# MistakeLog
# ---------------------------------------------------------------------------

class TestMistakeLog:
    def test_only_logs_mistakes(self, tmp_mistakes):
        r_ok = Reflection(is_mistake=False, domain="ok")
        r_bad = Reflection(is_mistake=True, domain="bad", outcome=OutcomeLabel.FAILURE)
        tmp_mistakes.record(r_ok)
        tmp_mistakes.record(r_bad)
        loaded = tmp_mistakes.load_all()
        assert len(loaded) == 1
        assert loaded[0].domain == "bad"

    def test_persistence_across_instances(self, tmp_path):
        path = str(tmp_path / "m.jsonl")
        log1 = MistakeLog(path=path)
        log1.record(Reflection(is_mistake=True, domain="x", outcome=OutcomeLabel.FAILURE))

        log2 = MistakeLog(path=path)
        assert log2.count() == 1


# ---------------------------------------------------------------------------
# ReflectionEngine — Outcome Classification
# ---------------------------------------------------------------------------

class TestOutcomeClassification:
    def test_success(self, engine):
        r = engine.reflect("q", "a", "good result", succeeded=True)
        assert r.outcome == OutcomeLabel.SUCCESS

    def test_failure(self, engine):
        r = engine.reflect("q", "a", "bad result", succeeded=False)
        assert r.outcome == OutcomeLabel.FAILURE

    def test_partial(self, engine):
        r = engine.reflect("q", "a", "meh result", succeeded=True, partial=True)
        assert r.outcome == OutcomeLabel.PARTIAL

    def test_partial_explicit(self, engine):
        r = engine.reflect("q", "a", "partial", succeeded=False, partial=True)
        assert r.outcome == OutcomeLabel.PARTIAL


# ---------------------------------------------------------------------------
# ReflectionEngine — Confidence Updates
# ---------------------------------------------------------------------------

class TestConfidenceUpdates:
    def test_success_increases_confidence(self, engine):
        before = engine.get_confidence("translation")
        engine.reflect("q", "a", "ok", domain="translation", succeeded=True)
        after = engine.get_confidence("translation")
        assert after > before

    def test_failure_decreases_confidence(self, engine):
        before = engine.get_confidence("translation")
        engine.reflect("q", "a", "fail", domain="translation", succeeded=False)
        after = engine.get_confidence("translation")
        assert after < before

    def test_delta_values(self, engine):
        engine.reflect("q", "a", "r", domain="d1", succeeded=True)
        assert engine.get_confidence("d1") == pytest.approx(0.65)   # 0.6 + 0.05

        engine.reflect("q", "a", "r", domain="d2", succeeded=False, partial=True)
        assert engine.get_confidence("d2") == pytest.approx(0.58)   # 0.6 - 0.02

        engine.reflect("q", "a", "r", domain="d3", succeeded=False)
        assert engine.get_confidence("d3") == pytest.approx(0.50)   # 0.6 - 0.10


# ---------------------------------------------------------------------------
# ReflectionEngine — Memory Writes
# ---------------------------------------------------------------------------

class TestMemoryWrites:
    def test_episodic_written_on_success(self, engine, mock_memory):
        engine.reflect("q", "act", "result", domain="code", succeeded=True)
        mock_memory.writer.store_episode.assert_called_once()
        args = mock_memory.writer.store_episode.call_args
        assert "SUCCESS" in args.kwargs.get("event", args.args[0] if args.args else "")

    def test_episodic_written_on_failure(self, engine, mock_memory):
        engine.reflect("q", "act", "fail", domain="code", succeeded=False)
        mock_memory.writer.store_episode.assert_called_once()

    def test_semantic_promoted_only_on_success(self, engine, mock_memory):
        engine.reflect("q", "act", "good", domain="trans", succeeded=True)
        mock_memory.writer.store_fact.assert_called_once()

    def test_semantic_not_promoted_on_failure(self, engine, mock_memory):
        engine.reflect("q", "act", "fail", domain="trans", succeeded=False)
        mock_memory.writer.store_fact.assert_not_called()

    def test_semantic_not_promoted_on_partial(self, engine, mock_memory):
        engine.reflect("q", "act", "meh", domain="trans", succeeded=True, partial=True)
        mock_memory.writer.store_fact.assert_not_called()


# ---------------------------------------------------------------------------
# ReflectionEngine — Mistake Logging
# ---------------------------------------------------------------------------

class TestMistakeLogging:
    def test_success_not_logged_as_mistake(self, engine, tmp_mistakes):
        engine.reflect("q", "a", "ok", succeeded=True)
        assert tmp_mistakes.count() == 0

    def test_failure_logged_as_mistake(self, engine, tmp_mistakes):
        engine.reflect("q", "a", "fail", succeeded=False, domain="x")
        assert tmp_mistakes.count() == 1

    def test_partial_logged_as_mistake(self, engine, tmp_mistakes):
        engine.reflect("q", "a", "meh", succeeded=True, partial=True, domain="y")
        assert tmp_mistakes.count() == 1

    def test_mistake_domain_preserved(self, engine, tmp_mistakes):
        engine.reflect("q", "a", "fail", domain="reasoning", succeeded=False)
        m = tmp_mistakes.load_all()[0]
        assert m.domain == "reasoning"


# ---------------------------------------------------------------------------
# ReflectionEngine — Lesson Generation
# ---------------------------------------------------------------------------

class TestLessonGeneration:
    def test_lesson_non_empty(self, engine):
        r = engine.reflect("translate hello", "call translate_api", "నమస్కారం",
                           domain="translation", succeeded=True)
        assert len(r.lesson) > 10

    def test_lesson_custom_hook(self, mock_memory, tmp_confidence, tmp_mistakes):
        def custom_gen(r: Reflection) -> str:
            return "Custom lesson!"

        eng = ReflectionEngine(
            memory=mock_memory,
            confidence_tracker=tmp_confidence,
            mistake_log=tmp_mistakes,
            lesson_generator=custom_gen,
        )
        r = eng.reflect("q", "a", "r", succeeded=True)
        assert r.lesson == "Custom lesson!"

    def test_lesson_hook_fallback_on_error(self, mock_memory, tmp_confidence, tmp_mistakes):
        def bad_gen(r):
            raise RuntimeError("LLM down")

        eng = ReflectionEngine(
            memory=mock_memory,
            confidence_tracker=tmp_confidence,
            mistake_log=tmp_mistakes,
            lesson_generator=bad_gen,
        )
        # Should not raise; falls back to rule-based
        r = eng.reflect("q", "a", "r", succeeded=True)
        assert len(r.lesson) > 5


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

class TestShorten:
    def test_short_string_unchanged(self):
        assert _shorten("hello world", 100) == "hello world"

    def test_long_string_truncated(self):
        s = _shorten("a" * 200, 50)
        assert len(s) == 50
        assert s.endswith("…")

    def test_whitespace_normalized(self):
        s = _shorten("hello   world\n\there", 100)
        assert "  " not in s
