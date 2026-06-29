"""Unit tests for Program 5D: Probabilistic Reasoning Engine.
"""
from __future__ import annotations

import pytest

from backend.core.beliefs.probabilistic_reasoning import (
    ProbabilisticReasoningEngine,
    DecisionExplanationGenerator,
    DecisionNode,
    ChanceNode,
    UtilityNode,
)


def test_expected_utility_calculator():
    """Verifies that Expected Utility computes EU = sum(P_i * U_i) correctly."""
    outcomes = [
        (0.6, 100.0),  # Success: 60% probability, utility 100
        (0.4, -50.0),  # Failure: 40% probability, utility -50
    ]
    eu = ProbabilisticReasoningEngine.calculate_expected_utility(outcomes)
    # 0.6 * 100 + 0.4 * -50 = 60 - 20 = 40
    assert eu == 40.0


def test_decision_tree_evaluation():
    """Tests evaluating a decision tree with decision, chance, and utility nodes."""
    engine = ProbabilisticReasoningEngine()

    # Build Tree:
    #             Decision (D)
    #            /            \
    #    Option A (Chance A)   Option B (Utility B: 45)
    #     /         \
    #  A1 (U=100)  A2 (U=-10)
    #  P=0.5        P=0.5

    # Branch A (Chance)
    u_a1 = UtilityNode("a1", 100.0)
    u_a2 = UtilityNode("a2", -10.0)
    chance_a = ChanceNode("chance_a", outcomes=[
        (0.5, u_a1, "success"),
        (0.5, u_a2, "failure"),
    ])

    # Branch B (Utility)
    u_b = UtilityNode("utility_b", 45.0)

    # Root Decision
    root = DecisionNode("root", choices=[
        (chance_a, "Option A"),
        (u_b, "Option B"),
    ])

    # Option A Expected Utility = 0.5 * 100 + 0.5 * -10 = 50 - 5 = 45
    # Option B Utility = 45
    # Since both are equal (45), evaluating should return 45 and "Option A" or "Option B" (based on ordering/maximizer)
    val, best_choice = engine.evaluate_decision_tree(root)
    assert val == 45.0
    assert best_choice in ("Option A", "Option B")


def test_value_of_perfect_information():
    """Tests that Value of Perfect Information (VPI) calculates utility improvements correctly."""
    # Prior expected utility of default action is 50.0
    prior_eu = 50.0

    # Conditional expected utilities if we gain information E:
    # If E is True (P(E)=0.4), new optimal action utility is 80.0
    # If E is False (P(E)=0.6), new optimal action utility is 40.0 (fallback to default is 50.0)
    # So: sum(P(e)*max(EU(a|e))) = 0.4 * 80 + 0.6 * 50 = 32 + 30 = 62.0
    # VPI = 62.0 - 50.0 = 12.0
    conditional_eus = [
        (0.4, 80.0),
        (0.6, 50.0),
    ]

    vpi = ProbabilisticReasoningEngine.calculate_vpi(prior_eu, conditional_eus)
    assert vpi == 12.0


def test_risk_assessment_thresholds():
    """Verifies that risk assessment correctly sums path probabilities below the utility threshold."""
    # Build Chance Node:
    #             Chance (C)
    #            /    |     \
    #        0.2     0.5    0.3
    #        /        |       \
    #     U=-100     U=10     U=50

    c = ChanceNode("c", outcomes=[
        (0.2, UtilityNode("u1", -100.0), "crash"),
        (0.5, UtilityNode("u2", 10.0), "nominal"),
        (0.3, UtilityNode("u3", 50.0), "optimum"),
    ])

    # Assess Risk (threshold = 0.0)
    # Downside outcomes: crash (utility -100 < 0). Probability = 0.2
    risk_0 = ProbabilisticReasoningEngine.assess_risk(c, threshold=0.0)
    assert risk_0 == 0.2

    # Assess Risk (threshold = 20.0)
    # Downside outcomes: crash (-100) and nominal (10). Probability = 0.2 + 0.5 = 0.7
    risk_20 = ProbabilisticReasoningEngine.assess_risk(c, threshold=20.0)
    assert risk_20 == 0.7


def test_decision_explanation_formatting():
    """Verifies that the explanation generator compiles expected sections."""
    u_win = UtilityNode("win", 100.0)
    u_lose = UtilityNode("lose", -50.0)
    chance = ChanceNode("gamble", outcomes=[
        (0.8, u_win, "win"),
        (0.2, u_lose, "lose"),
    ])

    root = DecisionNode("root", choices=[
        (chance, "Gamble"),
        (UtilityNode("safe", 10.0), "Safe Choice"),
    ])

    explainer = DecisionExplanationGenerator()
    explanation = explainer.generate_explanation(root, threshold=0.0)
    assert "Expected Utility" in explanation
    assert "Risk Probability" in explanation
    assert "Gamble" in explanation
