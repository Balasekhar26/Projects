"""Belief Management Component 12: Probabilistic Reasoning Engine (Program 5D).

Implements Expected Utility Calculation, Decision Tree Evaluation,
Value of Perfect Information (VPI) estimation, Risk Assessment, and Explanation traces.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decision Tree Node Classes
# ---------------------------------------------------------------------------

@dataclass
class DecisionTreeNode:
    """Base class for decision tree nodes."""
    node_id: str


@dataclass
class UtilityNode(DecisionTreeNode):
    """Leaf node containing final utility payoff value."""
    utility: float


@dataclass
class ChanceNode(DecisionTreeNode):
    """Node where nature/environment selects an outcome based on probabilities."""
    # List of tuples: (probability, child_node, outcome_name)
    outcomes: List[Tuple[float, DecisionTreeNode, str]] = field(default_factory=list)


@dataclass
class DecisionNode(DecisionTreeNode):
    """Node where the agent selects a choice choice."""
    # List of tuples: (child_node, choice_name)
    choices: List[Tuple[DecisionTreeNode, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core Reasoning Engine
# ---------------------------------------------------------------------------

class ProbabilisticReasoningEngine:
    """Performs decision-theoretic utility calculations and evaluations."""

    @staticmethod
    def calculate_expected_utility(outcomes: List[Tuple[float, float]]) -> float:
        """Calculates Expected Utility: EU = sum(P_i * U_i)."""
        return sum(prob * utility for prob, utility in outcomes)

    def evaluate_decision_tree(self, node: DecisionTreeNode) -> Tuple[float, Optional[str]]:
        """Evaluates a decision tree recursively.

        Returns a tuple: (expected_utility, best_choice_name)
        """
        if isinstance(node, UtilityNode):
            return node.utility, None

        elif isinstance(node, ChanceNode):
            # Chance node: compute expected utility over all outcomes
            eu = 0.0
            for prob, child, _ in node.outcomes:
                child_val, _ = self.evaluate_decision_tree(child)
                eu += prob * child_val
            return eu, None

        elif isinstance(node, DecisionNode):
            # Decision node: maximize expected utility
            best_utility = float("-inf")
            best_choice = None
            for child, choice_name in node.choices:
                child_val, _ = self.evaluate_decision_tree(child)
                if child_val > best_utility:
                    best_utility = child_val
                    best_choice = choice_name
            return best_utility, best_choice

        else:
            raise TypeError("Invalid decision tree node type.")

    @staticmethod
    def calculate_vpi(
        prior_eu: float,
        conditional_eus: List[Tuple[float, float]],
    ) -> float:
        """Calculates the Value of Perfect Information (VPI).

        Formula: VPI = (sum(P(evidence=v) * Max_Action EU(Action | evidence=v))) - prior_eu
        """
        post_eu_sum = sum(prob * max_eu for prob, max_eu in conditional_eus)
        return max(0.0, post_eu_sum - prior_eu)

    @staticmethod
    def assess_risk(
        node: DecisionTreeNode,
        threshold: float,
        path_probability: float = 1.0,
    ) -> float:
        """Computes the risk probability: sum(P(outcome) where utility < threshold)."""
        if isinstance(node, UtilityNode):
            return path_probability if node.utility < threshold else 0.0

        elif isinstance(node, ChanceNode):
            risk = 0.0
            for prob, child, _ in node.outcomes:
                risk += ProbabilisticReasoningEngine.assess_risk(child, threshold, path_probability * prob)
            return risk

        elif isinstance(node, DecisionNode):
            # Evaluate paths to find the optimal decision path, then evaluate risk on that path
            best_utility = float("-inf")
            best_child = None
            for child, _ in node.choices:
                # We reuse tree evaluation logic to select the node
                engine = ProbabilisticReasoningEngine()
                child_val, _ = engine.evaluate_decision_tree(child)
                if child_val > best_utility:
                    best_utility = child_val
                    best_child = child
            if best_child:
                return ProbabilisticReasoningEngine.assess_risk(best_child, threshold, path_probability)
            return 0.0

        return 0.0


# ---------------------------------------------------------------------------
# Decision Explanation Generator
# ---------------------------------------------------------------------------

class DecisionExplanationGenerator:
    """Compiles detailed, mathematical justifications for decisions."""

    def __init__(self) -> None:
        self._engine = ProbabilisticReasoningEngine()

    def generate_explanation(self, root: DecisionTreeNode, threshold: float = 0.0) -> str:
        """Generates a complete markdown layout justifying optimal tree choices and risks."""
        utility, choice = self._engine.evaluate_decision_tree(root)
        risk = self._engine.assess_risk(root, threshold)

        lines = [
            "### Probabilistic Decision Analysis Report",
            f"- **Optimal Decision Choice**: `{choice}`" if choice else "- **Optimal Choice**: N/A (Leaf node evaluated)",
            f"- **Expected Utility (EU)**: {utility:.4f}",
            f"- **Risk Probability (Utility < {threshold})**: {risk:.2%}",
        ]

        if risk > 0.30:
            lines.append("> [!WARNING]")
            lines.append(f"> High-risk path detected! Downside path probability is {risk:.2%}.")
        else:
            lines.append("> [!NOTE]")
            lines.append("Decision path matches safety standards.")

        return "\n".join(lines)
