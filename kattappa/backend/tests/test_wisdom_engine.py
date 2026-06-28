"""Tests for Phase K9 (multi-label): Wisdom Engine, Decision Classifier, and Gita Principles."""
from __future__ import annotations

import pytest
from backend.core.wisdom.gita_principles import (
    PRINCIPLES,
    get_principles_for_domain,
    get_principle_by_id,
    is_excluded_domain,
)
from backend.core.wisdom.classifier import (
    DecisionClassifier,
    SCIENCE_LABELS,
    WISDOM_LABELS,
)
from backend.core.wisdom.wisdom_engine import WisdomEngine
from backend.core.wisdom.science_engine import ScienceEngine


# ── Gita Principles tests ──────────────────────────────────────────────────────

def test_all_principles_have_required_fields():
    for p in PRINCIPLES:
        assert p.id.startswith("BG-"), f"{p.id} missing BG- prefix"
        assert p.chapter >= 1
        assert len(p.principle) > 10
        assert len(p.guidance) > 20
        assert len(p.application_domains) > 0


def test_technical_domains_are_excluded_from_all_principles():
    for p in PRINCIPLES:
        for tech in ("electronics", "code", "mathematics"):
            assert tech in p.exclusion_domains, (
                f"Principle {p.id} does not exclude {tech!r}"
            )


def test_get_principles_for_ethics_domain():
    hits = get_principles_for_domain("ethics")
    assert len(hits) >= 5


def test_get_principles_for_planning_domain():
    hits = get_principles_for_domain("planning")
    assert len(hits) >= 3


def test_get_principle_by_id():
    p = get_principle_by_id("BG-02-47")
    assert p is not None
    assert p.chapter == 2
    assert "right" in p.principle.lower()


def test_is_excluded_domain_true():
    assert is_excluded_domain("electronics") is True
    assert is_excluded_domain("CODE") is True
    assert is_excluded_domain("mathematics") is True


def test_is_excluded_domain_false():
    assert is_excluded_domain("ethics") is False
    assert is_excluded_domain("planning") is False
    assert is_excluded_domain("conflict") is False


# ── DecisionClassifier multi-label tests ──────────────────────────────────────

def test_classifier_returns_labels_list():
    result = DecisionClassifier.classify("How do I debug this Python function?")
    assert isinstance(result.labels, list)
    assert len(result.labels) >= 1
    assert all(hasattr(lw, "label") and hasattr(lw, "weight") for lw in result.labels)


def test_classifier_routes_code_question_to_science():
    result = DecisionClassifier.classify("How do I debug this Python function?")
    assert result.primary == "CODING"
    assert result.use_wisdom_engine is False
    assert result.use_science_engine is True


def test_classifier_routes_circuit_question_to_engineering():
    result = DecisionClassifier.classify("What resistor do I need for this LED circuit?")
    assert result.primary == "ENGINEERING"
    assert result.use_science_engine is True
    assert result.use_wisdom_engine is False


def test_classifier_routes_ethical_question_to_wisdom():
    result = DecisionClassifier.classify("Should I tell the user this might harm them?")
    assert result.primary == "ETHICAL"
    assert result.use_wisdom_engine is True
    assert "ethics" in result.suggested_domains


def test_classifier_multilabel_resign_example():
    """'Help me resign politely' should produce CONVERSATION + EMOTIONAL + PLANNING labels."""
    result = DecisionClassifier.classify(
        "Help me resign politely from my job."
    )
    label_names = {lw.label for lw in result.labels}
    assert result.use_wisdom_engine is True
    # Must activate at least 2 wisdom labels — CONVERSATION and EMOTIONAL both have signals
    wisdom_hits = label_names & WISDOM_LABELS
    assert len(wisdom_hits) >= 2, (
        f"Expected multiple wisdom labels for resignation request, got: {label_names}"
    )


def test_classifier_technical_wins_suppress_wisdom():
    """Heavy technical signals must block wisdom routing even when planning words appear."""
    result = DecisionClassifier.classify(
        "Plan how to refactor this Python code and debug the algorithm."
    )
    # CODING should be primary with high weight, suppressing PLANNING
    assert result.primary in SCIENCE_LABELS


def test_classifier_weights_sum_to_reasonable_range():
    result = DecisionClassifier.classify("What is machine learning?")
    for lw in result.labels:
        assert 0.0 < lw.weight <= 1.0, f"Weight out of range: {lw}"


def test_classifier_labels_sorted_descending():
    result = DecisionClassifier.classify(
        "I feel overwhelmed by my plan. Should I delay the milestone?"
    )
    weights = [lw.weight for lw in result.labels]
    assert weights == sorted(weights, reverse=True), "Labels not sorted by weight descending"


def test_classifier_conversation_fallback():
    result = DecisionClassifier.classify("Hello, how are you?")
    assert result.primary == "CONVERSATION"
    assert result.use_wisdom_engine is True


# ── WisdomEngine tests ─────────────────────────────────────────────────────────

def test_wisdom_engine_returns_principles_for_ethics():
    advice = WisdomEngine.advise("Should I proceed?", domains=["ethics", "decision_making"])
    assert len(advice.principles) > 0
    assert advice.confidence > 0.0
    assert "wisdom" in advice.summary.lower() or "ethics" in advice.summary.lower()


def test_wisdom_engine_blocks_technical_domain():
    advice = WisdomEngine.advise("How to code?", domains=["code"])
    assert len(advice.principles) == 0
    assert advice.confidence == 0.0
    assert "technical" in advice.summary.lower()


def test_wisdom_engine_caps_at_4_principles():
    advice = WisdomEngine.advise(
        "Complex ethical conflict",
        domains=["ethics", "conflict", "planning", "discipline", "decision_making"],
    )
    assert len(advice.principles) <= 4


def test_wisdom_engine_all_principles_in_correct_domain():
    advice = WisdomEngine.advise("planning question", domains=["planning"])
    for p in advice.principles:
        assert "planning" in p.application_domains


# ── ScienceEngine tests ────────────────────────────────────────────────────────

def test_science_engine_routes_code_to_coder():
    advice = ScienceEngine.advise("How do I write this algorithm?")
    assert advice.recommended_agent == "coder"


def test_science_engine_routes_circuit_to_engineer():
    advice = ScienceEngine.advise("Explain this circuit design.")
    assert advice.recommended_agent == "engineer"


def test_science_engine_routes_research_to_researcher():
    advice = ScienceEngine.advise("Find research papers on radar technology.")
    assert advice.recommended_agent == "researcher"


def test_science_engine_always_excludes_wisdom():
    advice = ScienceEngine.advise("Write Python code for FFT.")
    assert "Wisdom Engine" in advice.context_summary
    assert "does not apply" in advice.context_summary or "No Wisdom Engine" in advice.context_summary
