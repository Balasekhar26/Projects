"""Counterfactual Simulation Engine (Program 35.0).

Generates hypothetical alternative plans using operator substitutions, simulates
their execution metrics, and compares utility metrics to optimize planners.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from backend.core.planning.task import Plan, Operator


class CounterfactualSimulationEngine:
    """Simulates alternative histories and evaluates hypothetical plan utilities."""

    @classmethod
    def generate_alternatives(
        cls,
        plan: Plan,
        operator_substitution_map: Dict[str, List[Operator]],
    ) -> List[Plan]:
        """Substitutes original plan step operators to generate alternative candidate plans."""
        alternatives = []
        steps = plan.steps

        for idx, original_op in enumerate(steps):
            substitutes = operator_substitution_map.get(original_op.name, [])
            for sub_op in substitutes:
                # Create a cloned list of steps, replacing the current one
                alt_steps = list(steps)
                alt_steps[idx] = sub_op

                # Compute new totals
                total_cost = sum(op.estimated_cost for op in alt_steps)
                total_duration = sum(op.estimated_time for op in alt_steps)

                alt_plan = Plan(
                    plan_id=f"{plan.plan_id}_alt_{sub_op.operator_id}",
                    goal_id=plan.goal_id,
                    steps=alt_steps,
                    expected_cost=total_cost,
                    expected_duration=total_duration,
                    expected_reward=plan.expected_reward,
                    expected_risk=plan.expected_risk,
                    confidence=plan.confidence,
                )
                alternatives.append(alt_plan)

        return alternatives

    @classmethod
    def simulate_alternative(
        cls,
        alternative_plan: Plan,
        initial_variables: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Simulates step-by-step variables propagation and aggregates resource metrics."""
        current_vars = dict(initial_variables)
        total_cost = 0.0
        total_duration = 0.0
        is_success = True

        for idx, op in enumerate(alternative_plan.steps):
            # Check step preconditions
            precond_met = all(current_vars.get(k) == v for k, v in op.preconditions.items())
            if not precond_met:
                is_success = False
                break

            # Aggregate costs
            total_cost += op.estimated_cost
            total_duration += op.estimated_time

            # Apply effects
            current_vars.update(op.effects)

        # Check if final target goals are satisfied (cumulative effects of final plan steps)
        target_conditions: Dict[str, Any] = {}
        for step in alternative_plan.steps:
            target_conditions.update(step.effects)

        for key, expected_val in target_conditions.items():
            if current_vars.get(key) != expected_val:
                is_success = False
                break

        return {
            "plan_id": alternative_plan.plan_id,
            "is_success": is_success,
            "simulated_cost": total_cost,
            "simulated_duration": total_duration,
            "final_variables": current_vars,
        }

    @classmethod
    def compare_utility(
        cls,
        original_outcome: Dict[str, Any],
        simulated_runs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Evaluates utility scores (success - cost - time penalties) across candidates.

        Utility equation:
            U = (1.0 if success else 0.0) - (0.05 * cost) - (0.02 * duration)
        """
        # Calculate original utility
        orig_success = original_outcome.get("is_success", False)
        orig_cost = original_outcome.get("actual_cost", original_outcome.get("simulated_cost", 0.0))
        orig_duration = original_outcome.get("actual_duration", original_outcome.get("simulated_duration", 0.0))
        
        orig_val = 1.0 if orig_success else 0.0
        orig_utility = orig_val - (0.05 * orig_cost) - (0.02 * orig_duration)

        best_plan_id = original_outcome.get("plan_id", "original")
        best_utility = orig_utility
        optimal_run = original_outcome

        for run in simulated_runs:
            if not run["is_success"]:
                continue
            
            run_val = 1.0
            run_utility = run_val - (0.05 * run["simulated_cost"]) - (0.02 * run["simulated_duration"])
            
            if run_utility > best_utility:
                best_utility = run_utility
                best_plan_id = run["plan_id"]
                optimal_run = run

        utility_delta = best_utility - orig_utility

        return {
            "optimal_plan_id": best_plan_id,
            "original_utility": round(orig_utility, 3),
            "optimal_utility": round(best_utility, 3),
            "utility_delta": round(utility_delta, 3),
            "recommendation": (
                f"Substitute step operators with {best_plan_id} path."
                if utility_delta > 0.01 else "Maintain original execution structure."
            ),
        }
