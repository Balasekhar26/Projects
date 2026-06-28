"""Simulation Engine — Phase K16.5.

Evaluates candidate execution plans by simulating outcome state transitions,
predicting risks and utility values using the World Model, and returning
the optimal plan branch.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass
class SimulationBranchResult:
    branch_id: str
    steps: List[Dict[str, Any]]
    expected_utility: float  # Score from 0.0 to 1.0
    predicted_risk: float  # Score from 0.0 to 1.0
    completion_probability: float  # Score from 0.0 to 1.0
    reason: str


class SimulationEngine:
    """Simulates plan scenarios and computes optimal execution paths."""

    @classmethod
    def simulate_plans(
        cls,
        candidate_plans: List[Dict[str, Any]],
        world_state_context: Dict[str, Any]
    ) -> List[SimulationBranchResult]:
        """Simulates outcome state transitions for candidate plans."""
        log_event("simulation_engine_start", f"Simulating {len(candidate_plans)} plan branches")
        results = []

        for idx, plan in enumerate(candidate_plans):
            branch_id = plan.get("id") or f"branch-{idx}"
            steps = plan.get("steps") or []
            
            # Predict outcome per step using mock/transient World Model transitions
            accumulated_risk = 0.0
            accumulated_utility = 1.0
            failures = 0

            for step in steps:
                action = step.get("action", "").lower()
                
                # Simple rule-based prediction transitions:
                # 1. Shell commands carry execution risks
                if "shell" in action or "terminal" in action:
                    accumulated_risk += 0.25
                # 2. Deleting files carries high risk
                if "delete" in action or "remove" in action:
                    accumulated_risk += 0.40
                # 3. Actions with invalid params degrade completion probability
                if not step.get("params"):
                    accumulated_utility *= 0.8
                    failures += 1

            # Normalize risk and compute completion probability
            predicted_risk = min(1.0, accumulated_risk)
            completion_prob = max(0.0, 1.0 - (failures * 0.3))
            
            # Utility = (completion_prob * (1 - risk)) * goal_alignment
            expected_utility = completion_prob * (1.0 - (predicted_risk * 0.5))

            results.append(
                SimulationBranchResult(
                    branch_id=branch_id,
                    steps=steps,
                    expected_utility=round(expected_utility, 3),
                    predicted_risk=round(predicted_risk, 3),
                    completion_probability=round(completion_prob, 3),
                    reason=f"Risk: {predicted_risk:.2f}, Completion Probability: {completion_prob:.2f}"
                )
            )

        # Sort branches descending by expected utility
        results.sort(key=lambda b: b.expected_utility, reverse=True)
        
        if results:
            log_event("simulation_engine_complete", f"Best branch: {results[0].branch_id} (utility={results[0].expected_utility})")
        return results

    @classmethod
    def get_best_plan(
        cls,
        candidate_plans: List[Dict[str, Any]],
        world_state_context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Simulates all candidates and returns the plan dict with highest utility."""
        branches = cls.simulate_plans(candidate_plans, world_state_context)
        if not branches:
            return None
        
        best_branch = branches[0]
        # Locate the original plan dict matching best branch id
        for plan in candidate_plans:
            if plan.get("id") == best_branch.branch_id:
                # Inject simulation metadata
                plan["simulation"] = {
                    "expected_utility": best_branch.expected_utility,
                    "predicted_risk": best_branch.predicted_risk,
                    "completion_probability": best_branch.completion_probability,
                    "reason": best_branch.reason
                }
                return plan
        return candidate_plans[0]
