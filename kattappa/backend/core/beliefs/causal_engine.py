"""Belief Management Component 13: Causal Reasoning Engine (Program 5E).

Implements Structural Causal Models (SCMs), exogenous noise variables,
interventions (do-calculus), Judea Pearl's 3-step Counterfactuals process,
Root Cause Analysis, and Causal Explanation traces.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CausalVariable:
    """Represents an endogenous variable inside the Structural Causal Model."""
    name: str
    parents: List[str] = field(default_factory=list)
    # Structural equation mapping parent values + exogenous noise (bool) to this variable's value (bool).
    # E.g. equation = lambda parents, noise: parents.get("A", False) or noise
    equation: Callable[[Dict[str, bool], bool], bool] = field(default_factory=lambda: (lambda p, u: u))


class StructuralCausalModel:
    """Represents a set of causal variables and exogenous noise priors."""

    def __init__(self) -> None:
        self.variables: Dict[str, CausalVariable] = {}
        # Prior probability of exogenous noise variables being True: U_name -> probability
        self.exogenous_priors: Dict[str, float] = {}

    def add_variable(self, var: CausalVariable, exogenous_prior: float = 0.5) -> None:
        # Validate parent existence
        for p in var.parents:
            if p not in self.variables:
                raise ValueError(f"Parent '{p}' must be added before child '{var.name}'")

        # Check for cycles
        if self._would_cause_cycle(var.name, var.parents):
            raise ValueError(f"Adding variable '{var.name}' would introduce a circular cycle.")

        self.variables[var.name] = var
        # Register corresponding exogenous noise variable U_name
        self.exogenous_priors[f"U_{var.name}"] = exogenous_prior

    def get_variable_order(self) -> List[str]:
        """Returns topological ordering of endogenous variables."""
        visited: Set[str] = set()
        temp: Set[str] = set()
        order: List[str] = []

        def visit(name: str):
            if name in temp:
                raise ValueError("Causal cycle detected!")
            if name not in visited:
                temp.add(name)
                for child_id, child_var in self.variables.items():
                    if name in child_var.parents:
                        visit(child_id)
                temp.remove(name)
                visited.add(name)
                order.insert(0, name)

        for name in self.variables:
            if name not in visited:
                visit(name)
        return order

    def simulate(self, exogenous_states: Dict[str, bool]) -> Dict[str, bool]:
        """Runs SCM simulation given a fixed state of exogenous noise variables."""
        order = self.get_variable_order()
        values: Dict[str, bool] = {}

        for var_name in order:
            var = self.variables[var_name]
            parent_vals = {p: values[p] for p in var.parents}
            noise_val = exogenous_states.get(f"U_{var_name}", False)
            values[var_name] = var.equation(parent_vals, noise_val)

        return values

    def intervene(self, do_dict: Dict[str, bool]) -> StructuralCausalModel:
        """Applies do-calculus intervention do(X = Value), returning a modified SCM.

        Clips the incoming links of the intervened variables.
        """
        intervened = StructuralCausalModel()
        intervened.exogenous_priors = dict(self.exogenous_priors)

        for name, var in self.variables.items():
            if name in do_dict:
                val = do_dict[name]
                # Clip incoming links: parents = [], equation returns constant value regardless of noise
                intervened.variables[name] = CausalVariable(
                    name=name,
                    parents=[],
                    equation=lambda p, u, val=val: val
                )
            else:
                intervened.variables[name] = var

        return intervened

    # ------------------------------------------------------------------
    # Pearl's Three-Step Counterfactual Engine
    # ------------------------------------------------------------------

    def counterfactual(
        self,
        evidence: Dict[str, bool],
        intervention: Dict[str, bool],
        target: str,
    ) -> float:
        """Answers counterfactual queries: 'P(target = True | intervention, given evidence)'

        Steps:
        1. Abduction: Update exogenous variable probabilities P(U | evidence).
        2. Action: Modify SCM via do(intervention).
        3. Prediction: Simulate intervened SCM under updated exogenous priors.
        """
        # 1. Abduction: Calculate posterior probability of exogenous states given evidence
        exog_names = list(self.exogenous_priors.keys())
        updated_exog_priors = self._abduct(exog_names, evidence)

        # 2. Action: Create intervened model
        intervened_scm = self.intervene(intervention)

        # 3. Prediction: Compute target probability under updated exogenous priors
        return intervened_scm._predict(exog_names, updated_exog_priors, target)

    def _abduct(self, exog_names: List[str], evidence: Dict[str, bool]) -> Dict[str, float]:
        """Abduction step: computes P(U_i | evidence) for all exogenous variables."""
        num_exog = len(exog_names)
        joint_probs: Dict[Tuple[bool, ...], float] = {}

        # 1. Evaluate all 2^N combinations of exogenous variables
        total_evidence_prob = 0.0
        for i in range(1 << num_exog):
            exog_state = tuple(bool((i >> j) & 1) for j in range(num_exog))
            exog_state_dict = {exog_names[j]: exog_state[j] for j in range(num_exog)}

            # Prior probability of this exogenous state combination
            prob = 1.0
            for name, val in exog_state_dict.items():
                prior = self.exogenous_priors[name]
                prob *= prior if val else (1.0 - prior)

            # Simulate SCM under this exogenous state combination
            sim_vals = self.simulate(exog_state_dict)

            # Check if simulation matches our observations (evidence)
            matches_evidence = all(sim_vals.get(k) == v for k, v in evidence.items())

            if matches_evidence:
                joint_probs[exog_state] = prob
                total_evidence_prob += prob
            else:
                joint_probs[exog_state] = 0.0

        # 2. Normalize and compute marginal posteriors for each exogenous variable
        updated_priors = {}
        for name in exog_names:
            updated_priors[name] = self.exogenous_priors[name] # Default prior fallback

        if total_evidence_prob > 0.0:
            for j, name in enumerate(exog_names):
                prob_true = 0.0
                for exog_state, joint_prob in joint_probs.items():
                    if exog_state[j]:
                        prob_true += joint_prob
                updated_priors[name] = prob_true / total_evidence_prob

        return updated_priors

    def _predict(self, exog_names: List[str], exog_priors: Dict[str, float], target: str) -> float:
        """Prediction step: sums target variable probability over exogenous states."""
        num_exog = len(exog_names)
        target_prob_true = 0.0

        for i in range(1 << num_exog):
            exog_state = tuple(bool((i >> j) & 1) for j in range(num_exog))
            exog_state_dict = {exog_names[j]: exog_state[j] for j in range(num_exog)}

            # Joint probability of this exogenous state under updated priors
            prob = 1.0
            for name, val in exog_state_dict.items():
                prior = exog_priors[name]
                prob *= prior if val else (1.0 - prior)

            # Simulate intervened SCM
            sim_vals = self.simulate(exog_state_dict)
            if sim_vals.get(target, False):
                target_prob_true += prob

        return target_prob_true

    def _would_cause_cycle(self, name: str, parents: List[str]) -> bool:
        visited: Set[str] = set()

        def dfs(curr: str) -> bool:
            if curr == name:
                return True
            if curr in visited:
                return False
            visited.add(curr)
            var = self.variables.get(curr)
            if var:
                for p in var.parents:
                    if dfs(p):
                        return True
            return False

        for p in parents:
            if dfs(p):
                return True
        return False


# ---------------------------------------------------------------------------
# Root Cause Analyzer
# ---------------------------------------------------------------------------

class RootCauseAnalyzer:
    """Identifies and ranks causal contributors for system failure observations."""

    def __init__(self, scm: StructuralCausalModel) -> None:
        self.scm = scm

    def analyze_root_cause(self, failure_evidence: Dict[str, bool]) -> List[Tuple[str, float]]:
        """Ranks causal variables based on their counterfactual root cause score.

        Causal score = P(Failure = False | do(Var = False), given Failure = True)
        i.e. 'What is the probability the failure would not have occurred, if Var had been False?'
        """
        scores = []
        for name in self.scm.variables:
            # Skip scoring target failure node itself
            if name in failure_evidence:
                continue

            # Counterfactual query: P(Failure = False | do(Var = False), given failure_evidence)
            # We evaluate this for each failure key
            total_score = 0.0
            for failure_node, fail_val in failure_evidence.items():
                if not fail_val:
                    continue  # Only score causes for observed failures (True)

                p_fail_intervened = self.scm.counterfactual(
                    evidence=failure_evidence,
                    intervention={name: False},
                    target=failure_node,
                )
                # Counterfactual prevention probability: 1.0 - P(Fail | do(Not Var))
                prevent_prob = 1.0 - p_fail_intervened
                total_score += prevent_prob

            avg_score = total_score / max(1, len(failure_evidence))
            scores.append((name, avg_score))

        # Sort descending by prevention probability (higher prevention score = stronger root cause candidate)
        return sorted(scores, key=lambda x: x[1], reverse=True)


# ---------------------------------------------------------------------------
# Causal Explanation Generator
# ---------------------------------------------------------------------------

class CausalExplanationGenerator:
    """Formats structured explanation trace strings for causal interventions and queries."""

    @staticmethod
    def explain_counterfactual(
        evidence: Dict[str, bool],
        intervention: Dict[str, bool],
        target: str,
        result: float,
    ) -> str:
        explanation = [
            f"### Counterfactual Analysis for target variable: `{target}`",
            f"- **Observation/Evidence**: {', '.join(f'{k}={v}' for k, v in evidence.items())}",
            f"- **Intervention Query**: do({', '.join(f'{k}={v}' for k, v in intervention.items())})",
            f"- **Counterfactual Outcome Probability**: {result:.2%}",
        ]

        if result > 0.70:
            explanation.append(f"- **Conclusion**: The intervention is highly likely to cause `{target}` to become True.")
        elif result < 0.30:
            explanation.append(f"- **Conclusion**: The intervention makes it highly unlikely for `{target}` to occur.")
        else:
            explanation.append("- **Conclusion**: The counterfactual target remains highly uncertain under this intervention.")

        return "\n".join(explanation)
