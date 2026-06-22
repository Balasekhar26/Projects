from __future__ import annotations

import json

import pytest

from backend.core.agent_router import (
    AgentRouter,
    ConfidenceTier,
    IntentCategory,
    RouterMode,
    classify_intent,
)


@pytest.fixture
def router() -> AgentRouter:
    return AgentRouter()


# ---------------------------------------------------------------------------
# Confidence scoring & classification
# ---------------------------------------------------------------------------

def test_physics_question_scores_scientist_top(router):
    scores = router.score_agents("Calculate RF propagation and signal frequency")
    assert scores[0].agent == "Scientist"
    assert scores[0].score > 0


def test_clear_query_is_high_confidence_single(router):
    decision = router.route("Calculate RF wave propagation frequency and energy")
    assert decision.selected_agent == "Scientist"
    assert decision.confidence_tier is ConfidenceTier.HIGH
    assert decision.routing_mode == "single"
    assert decision.escalated is False


def test_scores_ranked_top_first(router):
    decision = router.route("Design an embedded firmware system")
    scores = decision.agent_scores
    assert [s.score for s in scores] == sorted((s.score for s in scores), reverse=True)


# ---------------------------------------------------------------------------
# Ambiguity / threshold escalation
# ---------------------------------------------------------------------------

def test_ambiguous_query_escalates_to_multi_agent(router):
    decision = router.route("Build RF firmware")
    # Contested: Engineer (build, firmware) vs Scientist (rf).
    assert decision.confidence_tier is ConfidenceTier.LOW
    assert decision.escalated is True
    assert decision.routing_mode == "multi_agent"
    top2 = set(decision.top_agents)
    assert top2 == {"Engineer", "Scientist"}


def test_low_confidence_activates_top_two(router):
    decision = router.route("Build RF firmware")
    assert len(decision.top_agents) == 2


def test_medium_confidence_keeps_secondary(router):
    # "explain" alone -> Teacher uncontested-ish but only one keyword.
    decision = router.route("Explain and teach the basics")
    assert decision.selected_agent == "Teacher"
    assert decision.confidence_tier in (ConfidenceTier.MEDIUM, ConfidenceTier.HIGH)


# ---------------------------------------------------------------------------
# Security override (independent of who "wins")
# ---------------------------------------------------------------------------

def test_security_override_even_if_engineer_wins(router):
    decision = router.route("Design a login system", mode=RouterMode.BEAST)
    # Engineer wins the confidence score (design, system)...
    assert decision.selected_agent == "Engineer"
    # ...but Security is still activated in the working set.
    assert decision.security_mandatory is True
    assert "Security" in decision.agents


# ---------------------------------------------------------------------------
# New categories
# ---------------------------------------------------------------------------

def test_new_intent_categories():
    assert classify_intent("Help me debug this stack trace") is IntentCategory.DEBUGGING
    assert classify_intent("Write the README documentation") is IntentCategory.DOCUMENTATION
    assert classify_intent("Make a slide deck for the demo") is IntentCategory.PRESENTATION
    assert classify_intent("Compare and evaluate the two approaches") is IntentCategory.ANALYSIS


# ---------------------------------------------------------------------------
# Critical safety rule: routing confidence != correctness confidence
# ---------------------------------------------------------------------------

def test_routing_confidence_field_is_distinct_and_labelled(router):
    decision = router.route("Calculate RF propagation")
    data = decision.to_dict()
    # The field is explicitly named "routing_confidence", never "confidence",
    # so it cannot be mistaken for answer correctness.
    assert "routing_confidence" in data
    assert "confidence" not in data
    assert 0.0 <= data["routing_confidence"] <= 1.0


def test_routing_confidence_is_deterministic(router):
    a = router.route("Build RF firmware").to_dict()
    b = router.route("Build RF firmware").to_dict()
    assert a == b


def test_decision_json_serialisable_with_v2_fields(router):
    decision = router.route("Design an RF mesh node")
    payload = json.dumps(decision.to_dict())
    data = json.loads(payload)
    assert "agent_scores" in data and "confidence_tier" in data and "top_agents" in data
