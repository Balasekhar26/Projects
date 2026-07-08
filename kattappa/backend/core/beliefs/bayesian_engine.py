"""Belief Management Component 10: Bayesian Belief Engine (Program 5C).

Implements exact Bayesian Network representation, Conditional Probability Tables (CPTs),
Belief Propagation via Exact Enumeration, and explanations of probability shifts.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class BayesianNode:
    """Represents a random variable in the Bayesian Network."""
    node_id: str
    parents: List[str] = field(default_factory=list)
    # Maps parent states (tuple of bool) to probability of this node being True.
    # E.g. for parents [A, B]: {(True, True): 0.95, (True, False): 0.6, ...}
    # For no parents (prior): {(): 0.5}
    cpt: Dict[Tuple[bool, ...], float] = field(default_factory=dict)

    def get_probability(self, parent_states: Tuple[bool, ...]) -> float:
        """Returns conditional probability of being True given parents."""
        # Fallback to default if parent states tuple not explicitly registered
        return self.cpt.get(parent_states, 0.5)


class BayesianNetwork:
    """Directed Acyclic Graph representing conditional probability dependencies."""

    def __init__(self) -> None:
        self.nodes: Dict[str, BayesianNode] = {}

    def add_node(self, node: BayesianNode) -> None:
        # Validate that parents exist
        for p in node.parents:
            if p not in self.nodes:
                raise ValueError(f"Parent '{p}' must be added before child '{node.node_id}'")
        
        # Check for cycles
        if self._would_cause_cycle(node.node_id, node.parents):
            raise ValueError(f"Adding node '{node.node_id}' would introduce a circular cycle.")

        self.nodes[node.node_id] = node

    def get_node(self, node_id: str) -> Optional[BayesianNode]:
        return self.nodes.get(node_id)

    def topological_sort(self) -> List[str]:
        """Returns nodes sorted topologically (parents before children)."""
        visited: Set[str] = set()
        temp_mark: Set[str] = set()
        order: List[str] = []

        def visit(node_id: str):
            if node_id in temp_mark:
                raise ValueError("Circular dependency cycle detected!")
            if node_id not in visited:
                temp_mark.add(node_id)
                # Find children (nodes that list node_id as parent)
                for child_id, child_node in self.nodes.items():
                    if node_id in child_node.parents:
                        visit(child_id)
                temp_mark.remove(node_id)
                visited.add(node_id)
                order.insert(0, node_id)

        # Start with nodes that have no parents
        for node_id in self.nodes:
            if node_id not in visited:
                visit(node_id)

        return order

    def query(self, target_id: str, evidence: Dict[str, bool]) -> float:
        """Computes exact posterior probability P(target_id = True | evidence) using Enumeration."""
        if target_id not in self.nodes:
            raise ValueError(f"Target node '{target_id}' not in network.")

        ordered_vars = self.topological_sort()

        # Enforce target_id value and compute joint sums
        e_true = dict(evidence)
        e_true[target_id] = True
        p_true = self._enumerate_all(ordered_vars, e_true)

        e_false = dict(evidence)
        e_false[target_id] = False
        p_false = self._enumerate_all(ordered_vars, e_false)

        total = p_true + p_false
        if total == 0.0:
            return 0.5  # Equal probability uncertainty default
        return p_true / total

    def _enumerate_all(self, variables: List[str], e: Dict[str, bool]) -> float:
        if not variables:
            return 1.0

        Y = variables[0]
        node = self.nodes[Y]
        
        # Determine parent state values from active variable state dictionary e
        # If parent is not instantiated in e, we default to False
        parent_states = tuple(e.get(p, False) for p in node.parents)
        prob_true = node.get_probability(parent_states)

        if Y in e:
            y_val = e[Y]
            p_y = prob_true if y_val else (1.0 - prob_true)
            return p_y * self._enumerate_all(variables[1:], e)
        else:
            # Y is unobserved — sum over Y = True and Y = False
            e_true = dict(e)
            e_true[Y] = True
            e_false = dict(e)
            e_false[Y] = False

            term_true = prob_true * self._enumerate_all(variables[1:], e_true)
            term_false = (1.0 - prob_true) * self._enumerate_all(variables[1:], e_false)
            return term_true + term_false

    def _would_cause_cycle(self, node_id: str, parents: List[str]) -> bool:
        """Returns True if establishing node_id -> parent paths introduces cycles."""
        visited: Set[str] = set()

        def dfs(curr: str) -> bool:
            if curr == node_id:
                return True
            if curr in visited:
                return False
            visited.add(curr)
            
            node = self.nodes.get(curr)
            if node:
                for p in node.parents:
                    if dfs(p):
                        return True
            return False

        for p in parents:
            if dfs(p):
                return True
        return False


class BayesianBeliefEngine:
    """Orchestrates Bayesian Network construction, probability shifts, and explanations."""

    def __init__(self) -> None:
        self.network = BayesianNetwork()
        self.evidence: Dict[str, bool] = {}

    def set_evidence(self, node_id: str, value: bool) -> None:
        self.evidence[node_id] = value

    def clear_evidence(self) -> None:
        self.evidence.clear()

    def generate_default_cpt(self, parents: List[str], dependency_types: List[str]) -> Dict[Tuple[bool, ...], float]:
        """Generates conditional probability values based on support/contradict relations."""
        cpt = {}
        num_parents = len(parents)
        
        # Iterate over all 2^N combinations
        for i in range(1 << num_parents):
            state = tuple(bool((i >> j) & 1) for j in range(num_parents))
            
            # Simple soft consensus score
            score = 0.5
            weight_per_parent = 0.4 / max(1, num_parents)
            
            for idx, val in enumerate(state):
                dep_type = dependency_types[idx] if idx < len(dependency_types) else "supports"
                if dep_type == "supports":
                    score += weight_per_parent if val else -weight_per_parent
                elif dep_type == "contradicts":
                    score += -weight_per_parent if val else weight_per_parent

            cpt[state] = max(0.01, min(0.99, score))
        return cpt

    def explain_probability_shift(self, target_id: str) -> str:
        """Computes prior vs posterior probabilities and explains the information shift."""
        if target_id not in self.network.nodes:
            return f"Node '{target_id}' not in network."

        prior = self.network.query(target_id, {})
        posterior = self.network.query(target_id, self.evidence)
        diff = posterior - prior

        explanation = [
            f"### Bayesian Probability Analysis for claim: {target_id}",
            f"- **Prior Probability**: {prior:.4f}",
            f"- **Posterior Probability (given active evidence)**: {posterior:.4f}",
            f"- **Probability Shift**: {diff:+.4f}",
        ]

        if self.evidence:
            explanation.append("- **Conditioning Evidence Applied**:")
            for e_id, val in self.evidence.items():
                explanation.append(f"  * {e_id} = {val}")
        else:
            explanation.append("- **Conditioning Evidence Applied**: None (Prior states active)")

        # Information shift analysis
        if abs(diff) > 0.05:
            direction = "reinforced" if diff > 0 else "degraded"
            explanation.append(f"- **Outcome**: Evidence has significantly {direction} the truth probability of this belief.")
        else:
            explanation.append("- **Outcome**: Active evidence has minimal information influence on this belief.")

        return "\n".join(explanation)
