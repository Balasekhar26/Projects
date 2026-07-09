"""World Model Engine (Program 42.0).

Maintains a predictive simulation of reality: predicts transition states under operator actions,
tracks resource evolution budgets, propagates confidence bounds, and checks trajectory feasibility.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

from backend.core.planning.task import Operator, PlannerState


class WorldModelEngine:
    """Predicts state transitions and resource dynamics over multi-step planning horizons."""

    @classmethod
    def predict_transition(cls, state: PlannerState, action: Operator) -> PlannerState:
        """Simulates execution of a single action, applying effects and depleting budgets."""
        # Clone planner state variables
        new_vars = copy.deepcopy(state.variables)

        # Apply operator effects
        new_vars.update(action.effects)

        # Propagate resource evolution: deduct budget balances, increment elapsed metrics
        current_budget = float(new_vars.get("budget", 100.0))
        new_budget = current_budget - action.estimated_cost
        new_vars["budget"] = max(0.0, new_budget)

        current_time = float(new_vars.get("time_elapsed", 0.0))
        new_vars["time_elapsed"] = current_time + action.estimated_time

        # Append visited node list
        new_visited = list(state.visited_nodes) + [action.operator_id]

        return PlannerState(
            current_goal=state.current_goal,
            variables=new_vars,
            completed_tasks=copy.deepcopy(state.completed_tasks),
            failed_tasks=copy.deepcopy(state.failed_tasks),
            visited_nodes=new_visited,
        )

    @classmethod
    def simulate_trajectory(
        cls,
        initial_state: PlannerState,
        steps: List[Operator],
        horizon: int = 5,
    ) -> Dict[str, Any]:
        """Projects trajectory feasibility, resource metrics, and joint success probabilities."""
        current_state = initial_state
        total_cost = 0.0
        total_duration = 0.0
        joint_confidence = 1.0
        is_feasible = True
        failure_reason = None

        limit = min(len(steps), horizon)
        for idx in range(limit):
            op = steps[idx]

            # 1. Precondition verification check
            precond_met = all(current_state.variables.get(k) == v for k, v in op.preconditions.items())
            if not precond_met:
                is_feasible = False
                failure_reason = f"Preconditions failed for operator '{op.operator_id}' at index {idx}."
                break

            # 2. Predict next state transition
            current_state = cls.predict_transition(current_state, op)

            # 3. Aggregate totals
            total_cost += op.estimated_cost
            total_duration += op.estimated_time
            
            # Simple probability product confidence propagation
            step_prob = 0.95  # default baseline step confidence probability
            joint_confidence *= step_prob

            # 4. Resource constraint check (ensure budget remains positive)
            if current_state.variables.get("budget", 100.0) <= 0.0:
                is_feasible = False
                failure_reason = f"Draining budget constraint crossed at operator '{op.operator_id}'."
                break

        return {
            "is_feasible": is_feasible,
            "failure_reason": failure_reason,
            "projected_cost": total_cost,
            "projected_duration": total_duration,
            "final_confidence": round(joint_confidence, 4),
            "final_variables": current_state.variables,
        }
