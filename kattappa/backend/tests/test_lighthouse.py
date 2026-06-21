from __future__ import annotations

import pytest

from backend.core.lighthouse import (
    AttentionAction,
    AttentionRing,
    AttentionScorer,
    CuriosityEngine,
    FocusGuardian,
    GoalRegistry,
    LIGHTHOUSE,
    LighthouseAttention,
    MemoryDisposition,
    RelationshipRegistry,
)


@pytest.fixture(autouse=True)
def _clean_state():
    """Each test starts from an empty recent window and empty registries."""
    LighthouseAttention.reset()
    for goal in GoalRegistry.list_goals():
        GoalRegistry.remove_goal(goal["id"])
    for entity in RelationshipRegistry.list_entities():
        RelationshipRegistry.remove_entity(entity["id"])
    for item in CuriosityEngine.list_queue():
        CuriosityEngine.resolve(item["id"], status="cleared")
    yield
    LighthouseAttention.reset()


# ---------------------------------------------------------------------------
# Scoring & ring classification
# ---------------------------------------------------------------------------

def test_direct_command_reaches_high_attention():
    result = LIGHTHOUSE.process_event("Kattappa, fix the build now!", source="user")
    assert result.score >= 70
    assert result.action in (AttentionAction.FOCUS, AttentionAction.CRITICAL)
    assert result.ring in (AttentionRing.CRITICAL, AttentionRing.IMPORTANT, AttentionRing.ACTIVE)
    assert result.should_remember is True
    assert result.memory_disposition is MemoryDisposition.STORE


def test_critical_urgency_lands_in_critical_ring():
    result = LIGHTHOUSE.process_event(
        "Kattappa emergency the production server crashed and failed right now",
        source="user",
    )
    assert result.ring is AttentionRing.CRITICAL
    assert result.action is AttentionAction.CRITICAL
    assert result.factors.urgency >= 0.85


def test_background_noise_is_ignored_and_forgotten():
    result = LIGHTHOUSE.process_event(
        "system background cpu telemetry sample tick logged",
        source="system",
    )
    assert result.ring in (AttentionRing.BACKGROUND, AttentionRing.NOISE)
    if result.ring is AttentionRing.NOISE:
        assert result.memory_disposition is MemoryDisposition.FORGET
    else:
        assert result.memory_disposition is MemoryDisposition.COMPRESS


def test_empty_event_is_noise():
    result = LIGHTHOUSE.process_event("   ", source="screen")
    assert result.ring is AttentionRing.NOISE
    assert result.action is AttentionAction.IGNORE
    assert result.score == 0.0
    assert result.should_remember is False


def test_explicit_save_request_is_high_user_importance():
    factors, reasons, _, _ = AttentionScorer.score(
        "remember that my api key lives in the vault",
        tokens={"api", "key", "lives", "vault"},
        source="user",
        recent=[],
    )
    assert factors.user_importance >= 0.9
    assert any("explicit save" in r for r in reasons)


def test_score_is_bounded_0_100():
    score = AttentionScorer.aggregate(
        AttentionScorer.score("anything at all here", {"anything", "all", "here"}, "user", [])[0]
    )
    assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# Noise filter / de-duplication
# ---------------------------------------------------------------------------

def test_near_duplicate_event_is_filtered_as_noise():
    text = "the unit test pipeline runs the firmware regression suite nightly"
    first = LIGHTHOUSE.process_event(text, source="user")
    assert first.duplicate is False
    second = LIGHTHOUSE.process_event(text, source="user")
    assert second.duplicate is True
    assert second.ring is AttentionRing.NOISE
    assert second.action is AttentionAction.IGNORE


def test_record_false_does_not_pollute_window():
    LIGHTHOUSE.process_event("hypothetical scoring only", source="user", record=False)
    # Window stays empty, so the same text is not seen as a duplicate next time.
    result = LIGHTHOUSE.process_event("hypothetical scoring only", source="user", record=False)
    assert result.duplicate is False


# ---------------------------------------------------------------------------
# Goal-locked attention (goal resonance)
# ---------------------------------------------------------------------------

def test_goal_resonance_lifts_attention_into_important_ring():
    baseline = LIGHTHOUSE.process_event(
        "notes about quantum entanglement experiments", source="web"
    )
    LighthouseAttention.reset()

    GoalRegistry.add_goal("Build Kattappa AI OS", keywords=["kattappa", "agent", "memory"])
    boosted = LIGHTHOUSE.process_event(
        "found a new agent memory framework for kattappa", source="web"
    )
    assert boosted.factors.goal_relevance > 0
    assert "Build Kattappa AI OS" in boosted.matched_goals
    assert boosted.score > baseline.score
    assert boosted.ring in (AttentionRing.IMPORTANT, AttentionRing.CRITICAL)


def test_goal_add_and_remove_roundtrip():
    goal = GoalRegistry.add_goal("Ship DEWS")
    assert any(g["id"] == goal["id"] for g in GoalRegistry.list_goals())
    assert GoalRegistry.remove_goal(goal["id"]) is True
    assert GoalRegistry.remove_goal(goal["id"]) is False


def test_empty_goal_title_rejected():
    with pytest.raises(ValueError):
        GoalRegistry.add_goal("   ")


# ---------------------------------------------------------------------------
# Relationship attention layer
# ---------------------------------------------------------------------------

def test_relationship_match_boosts_personal_importance():
    RelationshipRegistry.add_entity("Bala", relation="self", importance=0.9)
    result = LIGHTHOUSE.process_event("Bala asked about the testing schedule", source="user")
    assert "Bala" in result.matched_entities
    assert result.ring in (AttentionRing.IMPORTANT, AttentionRing.CRITICAL, AttentionRing.ACTIVE)


def test_relationship_add_and_remove():
    entity = RelationshipRegistry.add_entity("Friend One")
    assert any(e["id"] == entity["id"] for e in RelationshipRegistry.list_entities())
    assert RelationshipRegistry.remove_entity(entity["id"]) is True
    assert RelationshipRegistry.remove_entity("missing") is False


# ---------------------------------------------------------------------------
# Curiosity engine
# ---------------------------------------------------------------------------

def test_curiosity_gap_queues_research():
    result = LIGHTHOUSE.process_event(
        "Kattappa what is retrieval augmented generation", source="user"
    )
    assert result.curiosity_triggered is True
    pending = CuriosityEngine.list_queue(status="pending")
    assert any("retrieval augmented generation" in item["topic"].lower() for item in pending)


def test_curiosity_dedupes_similar_topics():
    CuriosityEngine.enqueue("what is graph rag and how does it work")
    CuriosityEngine.enqueue("what is graph rag and how does it work")
    pending = CuriosityEngine.list_queue(status="pending")
    assert len([p for p in pending if "graph rag" in p["topic"].lower()]) == 1


def test_curiosity_resolve():
    item = CuriosityEngine.enqueue("research vector databases")
    assert CuriosityEngine.resolve(item["id"]) is True
    assert CuriosityEngine.resolve("nonexistent") is False
    done = CuriosityEngine.list_queue(status="done")
    assert any(d["id"] == item["id"] for d in done)


# ---------------------------------------------------------------------------
# Focus guardian (drift prevention)
# ---------------------------------------------------------------------------

def test_focus_guardian_detects_drift():
    check = FocusGuardian.check(
        objective="implement the lighthouse attention scoring engine",
        event_text="what is the weather in tokyo tomorrow",
    )
    assert check.drifted is True
    assert "Return to" in check.advice


def test_focus_guardian_on_track():
    check = FocusGuardian.check(
        objective="implement the lighthouse attention scoring engine",
        event_text="adding the attention scoring engine unit tests",
    )
    assert check.drifted is False
    assert check.similarity >= FocusGuardian.drift_threshold


def test_focus_guardian_no_objective():
    check = FocusGuardian.check(objective="", event_text="anything")
    assert check.drifted is False


# ---------------------------------------------------------------------------
# Reflection attention
# ---------------------------------------------------------------------------

def test_reflection_summarises_and_strengthens_recurring_topics():
    events = [
        LIGHTHOUSE.process_event("kattappa build the memory module", source="user").to_dict(),
        LIGHTHOUSE.process_event("update the memory module decay engine", source="user").to_dict(),
        LIGHTHOUSE.process_event("random unrelated screen pixel noise abc", source="screen").to_dict(),
    ]
    report = LIGHTHOUSE.reflect(events)
    assert report["events_reviewed"] == 3
    assert "memory" in report["strengthen_memories"]
    assert isinstance(report["ring_counts"], dict)
    assert report["summary"].startswith("Reviewed 3 events")


def test_reflection_handles_empty_batch():
    report = LIGHTHOUSE.reflect([])
    assert report["events_reviewed"] == 0
    assert report["recurring_topics"] == []


# ---------------------------------------------------------------------------
# Status / serialisation
# ---------------------------------------------------------------------------

def test_status_reports_rings_and_weights():
    status = LIGHTHOUSE.status()
    assert status["framework"] == "Lighthouse Attention Framework"
    assert len(status["rings"]) == 5
    assert status["rings"][0]["ring"] == AttentionRing.CRITICAL.value
    assert set(status["factor_weights"]) == {
        "user_importance",
        "goal_relevance",
        "urgency",
        "novelty",
        "emotional_weight",
        "repetition",
    }


def test_result_to_dict_is_json_serialisable():
    import json

    result = LIGHTHOUSE.process_event("kattappa please run the tests", source="user")
    payload = json.dumps(result.to_dict())
    assert "ring" in payload
    assert "factors" in payload
