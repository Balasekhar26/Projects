from __future__ import annotations

import time

import pytest

from backend.core.goal_manager import GoalManager, GoalStatus
from backend.core.reflection_engine import ReflectionEngine, ReflectionStatus
from backend.core.reliability_monitor import ReliabilityMonitor


@pytest.fixture(autouse=True)
def _clean():
    ReliabilityMonitor.reset()
    GoalManager.reset()
    ReflectionEngine.reset()
    yield
    ReliabilityMonitor.reset()
    GoalManager.reset()
    ReflectionEngine.reset()


# ===========================================================================
# Reliability Monitor
# ===========================================================================

def test_accuracy_tracked_over_time():
    for success in (True, True, True, False):
        ReliabilityMonitor.record_outcome("Engineer", success)
    assert ReliabilityMonitor.accuracy("Engineer") == 0.75
    assert ReliabilityMonitor.weight_hint("Engineer") == 0.75


def test_unseen_agent_defaults_neutral():
    assert ReliabilityMonitor.accuracy("Ghost") is None
    assert ReliabilityMonitor.weight_hint("Ghost") == 0.5


def test_stats_lists_all_agents():
    ReliabilityMonitor.record_outcome("Scientist", True)
    ReliabilityMonitor.record_outcome("Planner", False)
    names = {a["agent"] for a in ReliabilityMonitor.stats()["agents"]}
    assert names == {"Scientist", "Planner"}


# ===========================================================================
# Goal Manager
# ===========================================================================

def test_goal_tree_and_progress():
    root = GoalManager.add_goal("Build DEWS")
    hw = GoalManager.add_goal("Hardware", parent_id=root["id"])
    fw = GoalManager.add_goal("Firmware", parent_id=root["id"])
    assert GoalManager.progress(root["id"]) == 0.0
    GoalManager.complete(hw["id"])
    assert GoalManager.progress(root["id"]) == 0.5
    GoalManager.complete(fw["id"])
    assert GoalManager.progress(root["id"]) == 1.0


def test_dependency_blocks_start():
    hw = GoalManager.add_goal("Hardware")
    fw = GoalManager.add_goal("Firmware", depends_on=[hw["id"]])
    started = GoalManager.start(fw["id"])
    assert started["status"] == GoalStatus.BLOCKED.value  # dependency not done
    GoalManager.complete(hw["id"])
    started = GoalManager.start(fw["id"])
    assert started["status"] == GoalStatus.ACTIVE.value


def test_ready_goals():
    hw = GoalManager.add_goal("Hardware")
    fw = GoalManager.add_goal("Firmware", depends_on=[hw["id"]])
    ready_ids = {g["id"] for g in GoalManager.ready_goals()}
    assert hw["id"] in ready_ids and fw["id"] not in ready_ids
    GoalManager.complete(hw["id"])
    ready_ids = {g["id"] for g in GoalManager.ready_goals()}
    assert fw["id"] in ready_ids


def test_unknown_dependency_rejected():
    with pytest.raises(ValueError):
        GoalManager.add_goal("X", depends_on=["nope"])


def test_empty_title_rejected():
    with pytest.raises(ValueError):
        GoalManager.add_goal("   ")


def test_goal_status_summary():
    GoalManager.add_goal("Root")
    s = GoalManager.status()
    assert s["total_goals"] == 1
    assert len(s["roots"]) == 1


# ===========================================================================
# Reflection Engine
# ===========================================================================

def test_reflection_starts_pending_and_not_actionable():
    rec = ReflectionEngine.reflect(
        "Forgot active project context", "retrieval threshold too strict",
        "Investigate project retrieval weighting", category="retrieval",
        evidence_source="conversation", confidence=70,
    )
    assert rec["status"] == ReflectionStatus.PENDING.value
    assert ReflectionEngine.is_actionable(rec) is False  # 1 obs, 1 source


def test_reflection_dedups_and_corroborates():
    a = ReflectionEngine.reflect("Forgot active project context",
                                 "threshold", "lower it", evidence_source="conversation")
    b = ReflectionEngine.reflect("Forgot active project context often",
                                 "threshold", "lower it", evidence_source="user_correction")
    # Folded into the same record, now 2 sources.
    assert a["id"] == b["id"]
    assert b["evidence_count"] == 2
    assert set(b["evidence_sources"]) == {"conversation", "user_correction"}
    assert len(ReflectionEngine.list_reflections()) == 1


def test_reflection_becomes_actionable_with_cross_source_evidence():
    for src in ("conversation", "user_correction", "validator"):
        rec = ReflectionEngine.reflect("Recurring sync leak in memory writes",
                                       "missing lock", "add a lock", evidence_source=src)
    assert rec["evidence_count"] == 3
    assert ReflectionEngine.is_actionable(rec) is True
    assert rec in ReflectionEngine.actionable()


def test_accept_requires_actionable():
    rec = ReflectionEngine.reflect("One-off blip", "noise", "ignore", evidence_source="reasoning")
    with pytest.raises(ValueError):
        ReflectionEngine.accept(rec["id"])  # only 1 observation


def test_accept_marks_accepted_but_applies_nothing():
    for src in ("a", "b", "c"):
        rec = ReflectionEngine.reflect("Validator keeps failing on RF math",
                                       "unit bug", "fix units", evidence_source=src)
    accepted = ReflectionEngine.accept(rec["id"])
    assert accepted["status"] == ReflectionStatus.ACCEPTED.value
    # Hypotheses-not-mutations: the engine never applies anything itself.
    for forbidden in ("apply", "execute", "mutate", "commit", "run"):
        assert not hasattr(ReflectionEngine, forbidden)


def test_reflection_expires():
    rec = ReflectionEngine.reflect("Stale issue", "x", "y", evidence_source="reasoning",
                                   window_days=30)
    expired = ReflectionEngine.expire_old(now=time.time() + 31 * 86400)
    assert expired == 1
    assert ReflectionEngine.get(rec["id"])["status"] == ReflectionStatus.EXPIRED.value


def test_reflection_status_summary():
    ReflectionEngine.reflect("Problem A", "c", "i", category="safety", evidence_source="reasoning")
    s = ReflectionEngine.status()
    assert s["total"] == 1
    assert s["by_category"]["safety"] == 1
