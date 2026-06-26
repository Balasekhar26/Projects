"""
Tests for Step 25 (Self-Improvement Engine) + Step 26 (Tool Mastery)
=====================================================================

All tests are hermetic (no network, no disk side effects outside tmp_path).

Step 25 — Self-Improvement Engine
  - ImprovementGoal schema roundtrip
  - GoalStore: save, status lifecycle, priority queue, persistence, exists_for_domain
  - PatternMiner: failure grouping, weakness_score computation, recency weight,
    top_phrases extraction, minimum failure threshold
  - SelfImprovementEngine.analyse():
      * Returns empty when no mistakes
      * Generates one goal per weak domain
      * Skips domain if open goal exists (idempotency)
      * Priority escalates with weakness_score
      * Triggers ResearchEngine for CRITICAL/HIGH goals
      * Custom action_generator hook
  - weakness_report() returns non-empty string

Step 26 — Tool Mastery
  - ToolProfile computed properties: success_rate, latency_penalty, mastery_score, mastery_label
  - ToolProfile roundtrip (to_dict / from_dict)
  - record_use: increments attempts/successes, updates confidence (clamped), EMA latency
  - Failure note deduplication
  - weakest_tools / strongest_tools ordering
  - by_category filtering
  - summary_table non-empty string
  - JSON persistence across instances
"""

import json
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta

from kattappa_runtime.reflection.schema           import Reflection, OutcomeLabel
from kattappa_runtime.learning.schema             import LearningRecord, RecordType
from kattappa_runtime.self_improvement.schema     import (
    ImprovementGoal, DomainWeakness, ImprovementPriority, GoalStatus
)
from kattappa_runtime.self_improvement.store      import GoalStore
from kattappa_runtime.self_improvement.pattern_miner import PatternMiner
from kattappa_runtime.self_improvement.engine     import SelfImprovementEngine
from kattappa_runtime.reflection.mistake_log      import MistakeLog
from kattappa_runtime.learning.store              import LearningStore
from kattappa_runtime.tool_mastery.store          import ToolMastery, ToolProfile, ToolCategory


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _rf_failure(n: int = 1, minutes_ago: int = 10) -> Reflection:
    """Create n failure Reflections for rf_systems domain."""
    ts = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    reflections = []
    for _ in range(n):
        r = Reflection(
            domain="rf_systems", outcome=OutcomeLabel.FAILURE,
            lesson="Insufficient understanding of impedance matching failed the calculation",
            confidence_delta=-0.10, is_mistake=True, timestamp=ts,
        )
        reflections.append(r)
    return reflections


def _make_mistake_log(tmp_path, reflections: list) -> MistakeLog:
    log = MistakeLog(path=str(tmp_path / "mistakes.jsonl"))
    for r in reflections:
        log.record(r)
    return log


def _make_learning_store(tmp_path, gaps: list = None) -> LearningStore:
    store = LearningStore(path=str(tmp_path / "learning.jsonl"))
    for rec in (gaps or []):
        store.save(rec)
    return store


def _make_engine(tmp_path, reflections, gaps=None, skill_mem=None,
                 research_engine=None, action_generator=None):
    log    = _make_mistake_log(tmp_path, reflections)
    lstore = _make_learning_store(tmp_path, gaps or [])
    gstore = GoalStore(path=str(tmp_path / "goals.jsonl"))
    return SelfImprovementEngine(
        mistake_log     = log,
        learning_store  = lstore,
        skill_memory    = skill_mem,
        research_engine = research_engine,
        goal_store      = gstore,
        action_generator= action_generator,
    )


# ===========================================================================
# STEP 25: ImprovementGoal Schema
# ===========================================================================

class TestImprovementGoalSchema:
    def test_default_fields(self):
        g = ImprovementGoal()
        assert g.goal_id
        assert g.status == GoalStatus.OPEN
        assert g.priority == ImprovementPriority.MEDIUM
        assert g.effectiveness == -1.0

    def test_to_dict_roundtrip(self):
        g = ImprovementGoal(
            domain="rf_systems",
            problem="Fails 67% of time",
            root_cause="impedance matching unknown",
            priority=ImprovementPriority.HIGH,
            recommended_actions=["Study Smith Chart", "Do exercises"],
            evidence_count=10,
        )
        d = g.to_dict()
        assert d["priority"] == "high"
        assert d["status"]   == "open"

        g2 = ImprovementGoal.from_dict(d)
        assert g2.domain    == "rf_systems"
        assert g2.priority  == ImprovementPriority.HIGH
        assert g2.evidence_count == 10
        assert g2.recommended_actions[0] == "Study Smith Chart"


# ===========================================================================
# STEP 25: GoalStore
# ===========================================================================

class TestGoalStore:
    def test_save_and_count(self, tmp_path):
        store = GoalStore(path=str(tmp_path / "g.jsonl"))
        store.save(ImprovementGoal(domain="d"))
        assert store.count() == 1

    def test_mark_in_progress(self, tmp_path):
        store = GoalStore(path=str(tmp_path / "g.jsonl"))
        g = ImprovementGoal(domain="x")
        store.save(g)
        updated = store.mark_in_progress(g.goal_id)
        assert updated.status == GoalStatus.IN_PROGRESS

    def test_mark_completed_with_effectiveness(self, tmp_path):
        store = GoalStore(path=str(tmp_path / "g.jsonl"))
        g = ImprovementGoal(domain="x")
        store.save(g)
        updated = store.mark_completed(g.goal_id, effectiveness=0.75)
        assert updated.status == GoalStatus.COMPLETED
        assert updated.effectiveness == pytest.approx(0.75)
        assert updated.completed_at  # non-empty timestamp

    def test_mark_stale(self, tmp_path):
        store = GoalStore(path=str(tmp_path / "g.jsonl"))
        g = ImprovementGoal(domain="x")
        store.save(g)
        updated = store.mark_stale(g.goal_id)
        assert updated.status == GoalStatus.STALE

    def test_priority_queue_orders_correctly(self, tmp_path):
        store = GoalStore(path=str(tmp_path / "g.jsonl"))
        store.save(ImprovementGoal(domain="a", priority=ImprovementPriority.LOW))
        store.save(ImprovementGoal(domain="b", priority=ImprovementPriority.CRITICAL))
        store.save(ImprovementGoal(domain="c", priority=ImprovementPriority.MEDIUM))
        q = store.get_priority_queue()
        assert q[0].priority == ImprovementPriority.CRITICAL
        assert q[-1].priority == ImprovementPriority.LOW

    def test_exists_for_domain_true(self, tmp_path):
        store = GoalStore(path=str(tmp_path / "g.jsonl"))
        store.save(ImprovementGoal(domain="rf_systems", status=GoalStatus.OPEN))
        assert store.exists_for_domain("rf_systems") is True

    def test_exists_for_domain_false_after_completion(self, tmp_path):
        store = GoalStore(path=str(tmp_path / "g.jsonl"))
        g = ImprovementGoal(domain="rf_systems")
        store.save(g)
        store.mark_completed(g.goal_id)
        assert store.exists_for_domain("rf_systems") is False

    def test_persistence_across_instances(self, tmp_path):
        p = str(tmp_path / "g.jsonl")
        s1 = GoalStore(path=p)
        g = ImprovementGoal(domain="python", priority=ImprovementPriority.HIGH)
        s1.save(g)

        s2 = GoalStore(path=p)
        assert s2.count() == 1
        loaded = s2.get_by_domain("python")
        assert loaded[0].priority == ImprovementPriority.HIGH

    def test_unknown_goal_id_returns_none(self, tmp_path):
        store = GoalStore(path=str(tmp_path / "g.jsonl"))
        assert store.mark_in_progress("nonexistent-id") is None


# ===========================================================================
# STEP 25: PatternMiner
# ===========================================================================

class TestPatternMiner:
    def test_returns_empty_when_no_mistakes(self):
        miner = PatternMiner()
        result = miner.mine([], [])
        assert result == []

    def test_returns_empty_below_min_failures(self, tmp_path):
        # Only 1 failure — below MIN_FAILURES=2
        miner = PatternMiner()
        r = Reflection(domain="x", outcome=OutcomeLabel.FAILURE,
                       lesson="something failed", is_mistake=True)
        result = miner.mine([r], [])
        assert result == []

    def test_detects_domain_weakness(self, tmp_path):
        miner = PatternMiner()
        failures = _rf_failure(n=5)
        result = miner.mine(failures, [])
        assert len(result) == 1
        assert result[0].domain == "rf_systems"
        assert result[0].failure_count == 5

    def test_weakness_score_in_range(self, tmp_path):
        miner = PatternMiner()
        failures = _rf_failure(n=8)
        result = miner.mine(failures, [])
        w = result[0]
        assert 0.0 <= w.weakness_score <= 1.0

    def test_gap_density_raises_score(self, tmp_path):
        miner = PatternMiner()
        failures = _rf_failure(n=3)

        # Same data but with gaps added
        gaps = [
            LearningRecord(domain="rf_systems", record_type=RecordType.SKILL_GAP,
                           knowledge="impedance matching"),
            LearningRecord(domain="rf_systems", record_type=RecordType.SKILL_GAP,
                           knowledge="smith chart"),
        ]
        miner_no_gaps = PatternMiner()
        miner_with_gaps = PatternMiner()

        w_no_gap   = miner_no_gaps.mine(failures, [])[0]
        w_with_gap = miner_with_gaps.mine(failures, gaps)[0]

        assert w_with_gap.weakness_score > w_no_gap.weakness_score

    def test_sorts_weakest_first(self, tmp_path):
        miner = PatternMiner()
        rf_failures  = _rf_failure(n=8)
        code_failures = [
            Reflection(domain="code", outcome=OutcomeLabel.FAILURE,
                       lesson="syntax error", is_mistake=True)
            for _ in range(2)   # fewer failures
        ]
        result = miner.mine(rf_failures + code_failures, [])
        assert result[0].domain == "rf_systems"  # higher weakness score

    def test_recency_weight_recent_failures_score_higher(self):
        miner = PatternMiner()

        # Recent failures (1 min ago)
        recent = _rf_failure(n=3, minutes_ago=1)
        # Old failures (5 days ago)
        old_failures = _rf_failure(n=3, minutes_ago=60 * 24 * 5)

        w_recent = miner.mine(recent, [])[0]
        w_old    = miner.mine(old_failures, [])[0]

        assert w_recent.weakness_score >= w_old.weakness_score

    def test_top_lessons_extracted(self):
        miner = PatternMiner()
        failures = [
            Reflection(domain="x", outcome=OutcomeLabel.FAILURE, is_mistake=True,
                       lesson="impedance matching failed on this calculation")
            for _ in range(3)
        ]
        result = miner.mine(failures, [])
        assert len(result[0].top_lessons) >= 1


# ===========================================================================
# STEP 25: SelfImprovementEngine Integration
# ===========================================================================

class TestSelfImprovementEngine:
    def test_returns_empty_when_no_mistakes(self, tmp_path):
        eng = _make_engine(tmp_path, reflections=[])
        goals = eng.analyse()
        assert goals == []

    def test_generates_goal_for_weak_domain(self, tmp_path):
        failures = _rf_failure(n=5)
        eng = _make_engine(tmp_path, reflections=failures)
        goals = eng.analyse()
        assert len(goals) == 1
        assert goals[0].domain == "rf_systems"

    def test_goal_has_recommended_actions(self, tmp_path):
        failures = _rf_failure(n=5)
        eng = _make_engine(tmp_path, reflections=failures)
        goals = eng.analyse()
        assert len(goals[0].recommended_actions) >= 1

    def test_idempotent_no_duplicate_goals(self, tmp_path):
        failures = _rf_failure(n=5)
        eng = _make_engine(tmp_path, reflections=failures)
        goals1 = eng.analyse()
        goals2 = eng.analyse()   # second run
        assert len(goals1) == 1
        assert len(goals2) == 0   # existing open goal suppresses new one

    def test_priority_high_for_high_weakness_score(self, tmp_path):
        # 10 failures → high weakness
        failures = _rf_failure(n=10)
        eng = _make_engine(tmp_path, reflections=failures)
        goals = eng.analyse()
        assert goals[0].priority in (ImprovementPriority.HIGH, ImprovementPriority.CRITICAL)

    def test_research_engine_triggered_for_high_priority(self, tmp_path):
        mock_research = MagicMock()
        failures = _rf_failure(n=10)
        eng = _make_engine(tmp_path, reflections=failures, research_engine=mock_research)
        goals = eng.analyse()
        if goals and goals[0].priority in (ImprovementPriority.HIGH, ImprovementPriority.CRITICAL):
            mock_research.research.assert_called_once()

    def test_custom_action_generator(self, tmp_path):
        def my_gen(w: DomainWeakness):
            return [f"Custom action for {w.domain}"]

        failures = _rf_failure(n=5)
        eng = _make_engine(tmp_path, reflections=failures, action_generator=my_gen)
        goals = eng.analyse()
        assert "Custom action for rf_systems" in goals[0].recommended_actions

    def test_custom_action_generator_fallback_on_error(self, tmp_path):
        def bad_gen(w):
            raise RuntimeError("generator failed")

        failures = _rf_failure(n=5)
        eng = _make_engine(tmp_path, reflections=failures, action_generator=bad_gen)
        goals = eng.analyse()
        # Should fall back to rule-based — actions still non-empty
        assert len(goals[0].recommended_actions) >= 1

    def test_weakness_report_non_empty(self, tmp_path):
        failures = _rf_failure(n=5)
        eng = _make_engine(tmp_path, reflections=failures)
        eng.analyse()
        report = eng.weakness_report()
        assert "rf_systems" in report
        assert len(report) > 50

    def test_weakness_report_before_analyse(self, tmp_path):
        eng = _make_engine(tmp_path, reflections=[])
        report = eng.weakness_report()
        assert "No improvement goals" in report

    def test_mark_goal_completed(self, tmp_path):
        failures = _rf_failure(n=5)
        eng = _make_engine(tmp_path, reflections=failures)
        goals = eng.analyse()
        updated = eng.mark_goal_completed(goals[0].goal_id, effectiveness=0.8)
        assert updated.status == GoalStatus.COMPLETED
        assert updated.effectiveness == pytest.approx(0.8)


# ===========================================================================
# STEP 26: ToolProfile Properties
# ===========================================================================

class TestToolProfile:
    def test_success_rate_no_attempts(self):
        p = ToolProfile(name="git")
        assert p.success_rate == -1.0

    def test_success_rate_computed(self):
        p = ToolProfile(name="git", attempts=10, successes=9)
        assert p.success_rate == pytest.approx(0.9)

    def test_latency_penalty_fast(self):
        p = ToolProfile(name="x", avg_latency_ms=50.0)
        assert p.latency_penalty == 0.0

    def test_latency_penalty_max(self):
        p = ToolProfile(name="x", avg_latency_ms=6000.0)
        assert p.latency_penalty == pytest.approx(1.0)

    def test_mastery_score_range(self):
        p = ToolProfile(name="x", confidence=0.8, attempts=10, successes=8,
                        avg_latency_ms=100.0)
        assert 0.0 <= p.mastery_score <= 1.0

    def test_mastery_labels(self):
        assert ToolProfile(name="x", confidence=0.95, attempts=10, successes=10,
                           avg_latency_ms=50.0).mastery_label == "Expert"
        assert ToolProfile(name="x", confidence=0.1, attempts=10, successes=1,
                           avg_latency_ms=4000.0).mastery_label == "Critical Gap"

    def test_to_dict_roundtrip(self):
        p = ToolProfile(name="git", category=ToolCategory.SHELL,
                        confidence=0.80, attempts=20, successes=18,
                        avg_latency_ms=40.0)
        d = p.to_dict()
        assert d["category"] == "shell"
        assert d["mastery_score"] == p.mastery_score

        p2 = ToolProfile.from_dict(d)
        assert p2.name      == "git"
        assert p2.category  == ToolCategory.SHELL
        assert p2.attempts  == 20


# ===========================================================================
# STEP 26: ToolMastery
# ===========================================================================

class TestToolMastery:
    def test_record_use_increments_attempts(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        tm.record_use("git", succeeded=True, latency_ms=40.0,
                      category=ToolCategory.SHELL)
        p = tm.get("git")
        assert p.attempts == 1
        assert p.successes == 1

    def test_record_failure_no_success_increment(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        tm.record_use("web_search", succeeded=False, latency_ms=3000.0,
                      category=ToolCategory.SEARCH)
        p = tm.get("web_search")
        assert p.attempts == 1
        assert p.successes == 0

    def test_confidence_updated_on_success(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        before = tm.get_or_default("git").confidence
        tm.record_use("git", succeeded=True, latency_ms=40.0)
        after = tm.get("git").confidence
        assert after > before

    def test_confidence_updated_on_failure(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        before = tm.get_or_default("web_search").confidence
        tm.record_use("web_search", succeeded=False, latency_ms=3000.0)
        after = tm.get("web_search").confidence
        assert after < before

    def test_confidence_clamped_upper(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        tm._profiles["x"] = ToolProfile(name="x", confidence=0.99)
        tm.record_use("x", succeeded=True, latency_ms=10.0)
        assert tm.get("x").confidence <= 1.0

    def test_confidence_clamped_lower(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        tm._profiles["x"] = ToolProfile(name="x", confidence=0.02)
        tm.record_use("x", succeeded=False, latency_ms=1000.0)
        assert tm.get("x").confidence >= 0.0

    def test_latency_ema_updated(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        tm.record_use("tool", succeeded=True, latency_ms=1000.0)
        p = tm.get("tool")
        # EMA of (default=500 → 0.2*1000 + 0.8*500 = 600)
        assert p.avg_latency_ms != 500.0

    def test_failure_note_appended(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        tm.record_use("api", succeeded=False, latency_ms=5000.0,
                      failure_note="connection timeout")
        p = tm.get("api")
        assert "connection timeout" in p.common_failures

    def test_failure_note_deduplication(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        tm.record_use("api", succeeded=False, failure_note="connection timeout")
        tm.record_use("api", succeeded=False, failure_note="connection timeout")
        tm.record_use("api", succeeded=False, failure_note="Connection Timeout")
        p = tm.get("api")
        assert len(p.common_failures) == 1

    def test_weakest_tools_ordering(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        tm._profiles["good_tool"] = ToolProfile(name="good_tool", confidence=0.90,
                                                  attempts=10, successes=9,
                                                  avg_latency_ms=50.0)
        tm._profiles["bad_tool"]  = ToolProfile(name="bad_tool",  confidence=0.20,
                                                  attempts=10, successes=2,
                                                  avg_latency_ms=4000.0)
        weakest = tm.weakest_tools(n=1)
        assert weakest[0].name == "bad_tool"

    def test_strongest_tools_ordering(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        tm._profiles["good_tool"] = ToolProfile(name="good_tool", confidence=0.90,
                                                  attempts=10, successes=9,
                                                  avg_latency_ms=50.0)
        tm._profiles["bad_tool"]  = ToolProfile(name="bad_tool",  confidence=0.20,
                                                  attempts=10, successes=2,
                                                  avg_latency_ms=4000.0)
        strongest = tm.strongest_tools(n=1)
        assert strongest[0].name == "good_tool"

    def test_by_category_filter(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        tm.record_use("git",        succeeded=True, category=ToolCategory.SHELL)
        tm.record_use("web_search", succeeded=True, category=ToolCategory.SEARCH)
        shells = tm.by_category(ToolCategory.SHELL)
        assert len(shells) == 1
        assert shells[0].name == "git"

    def test_summary_table_non_empty(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        tm.record_use("git", succeeded=True, latency_ms=40.0, category=ToolCategory.SHELL)
        table = tm.summary_table()
        assert "git" in table
        assert "shell" in table

    def test_summary_table_no_tools(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        assert "No tool" in tm.summary_table()

    def test_persistence_across_instances(self, tmp_path):
        p = str(tmp_path / "t.json")
        tm1 = ToolMastery(path=p)
        tm1.record_use("git", succeeded=True, latency_ms=40.0, category=ToolCategory.SHELL)

        tm2 = ToolMastery(path=p)
        assert tm2.get("git") is not None
        assert tm2.get("git").attempts == 1

    def test_register_tool_no_use(self, tmp_path):
        tm = ToolMastery(path=str(tmp_path / "t.json"))
        tm.register_tool("code_runner", category=ToolCategory.CODE, notes="sandboxed exec")
        p = tm.get("code_runner")
        assert p is not None
        assert p.attempts == 0
        assert p.notes == "sandboxed exec"
