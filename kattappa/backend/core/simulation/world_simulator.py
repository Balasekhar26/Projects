"""Belief Management Component 14: World Simulation Engine (Program 5F).

Provides isolated virtual sandboxing to clone current belief graphs,
apply SCM interventions (do-calculus), predict scenario outcomes,
and compare expected utilities and downside risks across branches.
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.core.beliefs.belief import Belief
from backend.core.beliefs.belief_store import BeliefStore
from backend.core.beliefs.causal_engine import StructuralCausalModel, CausalVariable
from backend.core.beliefs.probabilistic_reasoning import ProbabilisticReasoningEngine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SimulationState:
    """Represents an immutable, cloned snapshot of the active beliefs state."""
    timestamp: float
    variables: Dict[str, Any] = field(default_factory=dict)
    confidences: Dict[str, float] = field(default_factory=dict)

    def clone_with_update(self, updates: Dict[str, Any], conf_updates: Optional[Dict[str, float]] = None) -> SimulationState:
        """Returns a modified copy-on-write clone of this state."""
        new_vars = dict(self.variables)
        new_vars.update(updates)
        new_confs = dict(self.confidences)
        if conf_updates:
            new_confs.update(conf_updates)
        return SimulationState(
            timestamp=time.time(),
            variables=new_vars,
            confidences=new_confs,
        )


@dataclass
class Scenario:
    """Represents a candidate path of hypothetical interventions."""
    scenario_id: str
    name: str
    interventions: Dict[str, Any]  # do-calculus values (e.g. {"Grid": False})
    target_goal_node: str         # The node we want to achieve/evaluate (e.g. "ServerOnline")
    utility_map: Dict[bool, float] = field(default_factory=lambda: {True: 100.0, False: -50.0})


class OutcomePredictor:
    """Predicts outcome states using the Structural Causal Model (SCM)."""

    def __init__(self, scm: StructuralCausalModel) -> None:
        self.scm = scm

    def predict_outcome(self, initial_state: SimulationState, scenario: Scenario) -> Tuple[SimulationState, float]:
        """Applies scenario interventions, simulates SCM, and returns predicted state + success probability."""
        # 1. Abduce/map initial state values to exogenous noise priors if possible
        # For simplicity, if a variable is True with high confidence, set its exogenous prior to 0.9
        active_scm = StructuralCausalModel()
        for name, var in self.scm.variables.items():
            val = initial_state.variables.get(name, False)
            conf = initial_state.confidences.get(name, 0.5)
            prior = conf if val else (1.0 - conf)
            active_scm.add_variable(var, exogenous_prior=max(0.01, min(0.99, prior)))

        # 2. Apply do-intervention action
        intervened_scm = active_scm.intervene(scenario.interventions)

        # 3. Simulate predicted outcome values under average noise (True if prior >= 0.5)
        exog_states = {}
        for k, prior in intervened_scm.exogenous_priors.items():
            exog_states[k] = (prior >= 0.5)
        simulated_vals = intervened_scm.simulate(exog_states)

        # 4. Compute success probability of target goal node
        success_prob = intervened_scm.counterfactual(
            evidence={},
            intervention=scenario.interventions,
            target=scenario.target_goal_node,
        )

        predicted_confs = {}
        for var in simulated_vals:
            # Map confidences based on causal predictions
            if var == scenario.target_goal_node:
                predicted_confs[var] = success_prob
            else:
                predicted_confs[var] = 1.0 if simulated_vals[var] else 0.0

        predicted_state = SimulationState(
            timestamp=time.time(),
            variables=simulated_vals,
            confidences=predicted_confs,
        )

        return predicted_state, success_prob


class WorldSimulator:
    """Coordinates scenario cloning, predictive simulation, and rollback controls."""

    def __init__(self, store: BeliefStore, scm: StructuralCausalModel) -> None:
        self._store = store
        self._scm = scm
        self._predictor = OutcomePredictor(scm)
        self._history: List[Tuple[str, SimulationState]] = []  # Keeps rollback log of simulated states

    def clone_current_world(self) -> SimulationState:
        """Clones the current active beliefs database table to an in-memory snapshot."""
        beliefs = self._store.list_beliefs()
        variables = {}
        confidences = {}
        for b in beliefs:
            # Group by subject.predicate as unique simulation variables
            key = f"{b.claim_subject}.{b.claim_predicate}"
            variables[key] = b.claim_value
            confidences[key] = b.confidence

        return SimulationState(timestamp=time.time(), variables=variables, confidences=confidences)

    def run_simulation(self, scenario: Scenario) -> Tuple[SimulationState, float]:
        """Runs simulation for a given scenario, adding the output state to the history log."""
        init_state = self.clone_current_world()
        pred_state, prob = self._predictor.predict_outcome(init_state, scenario)
        self._history.append((scenario.scenario_id, pred_state))
        return pred_state, prob

    def rollback_simulation(self, scenario_id: str) -> Optional[SimulationState]:
        """Removes the latest simulated state for the target scenario from history."""
        for idx in range(len(self._history) - 1, -1, -1):
            sc_id, state = self._history[idx]
            if sc_id == scenario_id:
                self._history.pop(idx)
                log_event("simulation_rolled_back", f"Rolled back simulation for scenario: {scenario_id}")
                return state
        return None


# ---------------------------------------------------------------------------
# Scenario Comparator
# ---------------------------------------------------------------------------

class ScenarioComparator:
    """Compares simulated outcomes using decision-theoretic expected utility and risks."""

    @staticmethod
    def compare_scenarios(
        results: List[Tuple[Scenario, SimulationState, float]],
        risk_threshold: float = 0.0,
    ) -> str:
        """Compares list of (Scenario, PredictedState, SuccessProb) and generates optimal recommendations."""
        reports = []
        best_eu = float("-inf")
        best_scenario = None

        for sc, state, prob in results:
            # Expected Utility: prob * Utility(Success) + (1-prob) * Utility(Failure)
            u_success = sc.utility_map.get(True, 100.0)
            u_fail = sc.utility_map.get(False, -50.0)
            
            eu = prob * u_success + (1.0 - prob) * u_fail
            risk = (1.0 - prob) if u_fail < risk_threshold else 0.0

            reports.append(
                f"#### Scenario: `{sc.name}` ({sc.scenario_id})\n"
                f"- **Goal Target**: `{sc.target_goal_node}` = True\n"
                f"- **Success Probability**: {prob:.2%}\n"
                f"- **Expected Utility (EU)**: {eu:.2f}\n"
                f"- **Downside Failure Risk**: {risk:.2%}"
            )

            if eu > best_eu:
                best_eu = eu
                best_scenario = sc

        recommendation = ""
        if best_scenario:
            recommendation = (
                f"### Recommendation\n"
                f"Select **{best_scenario.name}** (`{best_scenario.scenario_id}`) "
                f"maximizing expected utility to {best_eu:.2f}."
            )

        return "\n\n".join([
            "### World Simulation Comparison Report",
            "\n\n".join(reports),
            recommendation,
        ])


def log_event(event_type: str, message: str) -> None:
    logger.info("[%s] %s", event_type.upper(), message)
