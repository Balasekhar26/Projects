from __future__ import annotations

import pytest

from backend.core.value_engine import (
    LENSES,
    PROFILES,
    PlanSignals,
    ValueDriftMonitor,
    ValueEngine,
    ValueProfile,
    weighted_score,
)


@pytest.fixture(autouse=True)
def _clean():
    ValueDriftMonitor.reset()
    yield
    ValueDriftMonitor.reset()


# ===========================================================================
# Lens scoring (required output)
# ===========================================================================

def test_score_plan_returns_required_keys():
    scores = ValueEngine.score_plan(PlanSignals("p"))
    for key in ("ethics", "creativity", "simplification", "strategy", "loyalty"):
        assert key in scores
        assert 0.0 <= scores[key] <= 1.0
    assert "feasibility" in scores  # Vishwakarma


def test_ethics_tracks_validator_and_tests():
    weak = ValueEngine.score_plan(PlanSignals("w", validator_score=0.2, reliability_score=0.2,
                                              test_score=0.2, safety_score=0.2))
    strong = ValueEngine.score_plan(PlanSignals("s", validator_score=1.0, reliability_score=1.0,
                                                test_score=1.0, safety_score=1.0))
    assert strong["ethics"] > weak["ethics"]


def test_simplification_is_monotonic_in_complexity():
    simple = ValueEngine.score_plan(PlanSignals("a", steps=3))["simplification"]
    complex_ = ValueEngine.score_plan(PlanSignals("b", steps=12))["simplification"]
    assert simple > complex_


def test_loyalty_is_goal_match():
    assert ValueEngine.score_plan(PlanSignals("p", goal_match=0.95))["loyalty"] == 0.95


# ===========================================================================
# User-intent GATE (not a weight)
# ===========================================================================

def test_intent_conflict_cannot_outrank_compliant_plan():
    # A plan that conflicts with explicit intent, despite higher raw value.
    conflicting = PlanSignals(
        "conflicting", contradicts_user_intent=True,
        validator_score=1.0, reliability_score=1.0, test_score=1.0, novelty=1.0, goal_match=1.0,
    )
    compliant = PlanSignals("compliant", goal_match=0.4, novelty=0.2, validator_score=0.5)
    ranking = ValueEngine.rank([conflicting, compliant])
    assert ranking.selected.name == "compliant"          # gate beats raw score
    assert ranking.ranked[-1].name == "conflicting"
    assert ranking.ranked[-1].disqualified is True


def test_all_conflicting_still_produces_ordering_with_warning():
    ranking = ValueEngine.rank([
        PlanSignals("a", contradicts_user_intent=True, goal_match=0.5),
        PlanSignals("b", contradicts_user_intent=True, goal_match=0.9),
    ])
    assert ranking.selected is not None            # never blocks
    assert "conflict" in ranking.warning


# ===========================================================================
# Context profiles change preference
# ===========================================================================

def _novel_plan() -> PlanSignals:
    return PlanSignals("novel", novelty=0.95, validator_score=0.4, reliability_score=0.4,
                       test_score=0.4, safety_score=0.4, steps=9, reversible=False,
                       optionality=0.5, resource_preservation=0.5, goal_match=0.6,
                       capability_coverage=0.6, sim_success=0.6, cost_score=0.6)


def _stable_plan() -> PlanSignals:
    return PlanSignals("stable", novelty=0.2, validator_score=0.95, reliability_score=0.95,
                       test_score=0.95, safety_score=0.95, steps=6, reversible=True,
                       optionality=0.5, resource_preservation=0.5, goal_match=0.6,
                       capability_coverage=0.7, sim_success=0.7, cost_score=0.7)


def test_greenfield_prefers_novel_production_prefers_stable():
    plans = [_novel_plan(), _stable_plan()]
    assert ValueEngine.rank(plans, ValueProfile.GREENFIELD).selected.name == "novel"
    assert ValueEngine.rank(plans, ValueProfile.PRODUCTION).selected.name == "stable"


def test_profiles_sum_to_one():
    for profile, weights in PROFILES.items():
        assert sum(weights.values()) == pytest.approx(1.0), profile
        assert set(weights) == set(LENSES)


# ===========================================================================
# Deterministic tiebreakers
# ===========================================================================

def test_tiebreak_prefers_higher_user_alignment():
    # Identical except goal_match -> the one with higher loyalty wins the tie.
    a = PlanSignals("a", goal_match=0.6, novelty=0.5)
    b = PlanSignals("b", goal_match=0.9, novelty=0.5)
    ranking = ValueEngine.rank([a, b], ValueProfile.DEFAULT)
    # loyalty differs so final differs slightly, but b must win regardless.
    assert ranking.selected.name == "b"


def test_rank_is_deterministic():
    plans = [_novel_plan(), _stable_plan()]
    r1 = ValueEngine.rank(plans, ValueProfile.DEFAULT).to_dict()
    r2 = ValueEngine.rank(plans, ValueProfile.DEFAULT).to_dict()
    assert r1 == r2


# ===========================================================================
# Rank-only contract & consensus integration
# ===========================================================================

def test_engine_never_blocks_or_overrides():
    for forbidden in ("veto", "reject", "block", "escalate", "approve", "execute"):
        assert not hasattr(ValueEngine, forbidden)


def test_rank_after_consensus_only_runs_when_approved():
    from backend.core.consensus_engine import (
        AgentOutput, ConsensusEngine, Decision, Recommendation, Veto,
    )
    approved = ConsensusEngine.decide([
        AgentOutput("Engineer", Decision.APPROVE, source_id="m1",
                    recommendations=(Recommendation("Engineer", "go", 1.0),)),
    ])
    plans = [_novel_plan(), _stable_plan()]
    ranking = ValueEngine.rank_after_consensus(approved, plans, ValueProfile.PRODUCTION)
    assert ranking is not None and ranking.selected.name == "stable"

    rejected = ConsensusEngine.decide([
        AgentOutput("Security", veto=Veto("Security", passed=False, reason="unsafe")),
    ])
    # Value Engine does not run on a non-approved decision (and cannot revive it).
    assert ValueEngine.rank_after_consensus(rejected, plans) is None


# ===========================================================================
# Value Drift Monitor (advisory)
# ===========================================================================

def test_drift_monitor_flags_dominance_collapse():
    # Record many decisions where 'ethics' dominates.
    for _ in range(10):
        ranking = ValueEngine.rank([PlanSignals(
            "p", validator_score=1.0, reliability_score=1.0, test_score=1.0, safety_score=1.0,
            novelty=0.1, goal_match=0.2)])
        ValueDriftMonitor.record(ranking, novel=False)
    report = ValueDriftMonitor.report()
    assert report["decisions"] == 10
    assert any("diversity collapsing" in w for w in report["warnings"])
    # Advisory only: monitor exposes no auto-correction.
    assert not hasattr(ValueDriftMonitor, "correct")


def test_weighted_score_matches_manual():
    scores = {lens: 0.5 for lens in LENSES}
    assert weighted_score(scores, ValueProfile.DEFAULT) == pytest.approx(0.5)
