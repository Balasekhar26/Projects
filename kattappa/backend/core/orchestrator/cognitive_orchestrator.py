"""Autonomous Cognitive Loop Orchestrator (Program 37.0).

Coordinates HTN Planning, Decision Network Policy Selection, Resumable Runtime Execution,
Outcome Evaluation, Reflection Log Generation, and Counterfactual Simulations
into a single closed-loop cognitive execution cycle.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from backend.core.planning.goal import Goal
from backend.core.planning.task import Plan, Operator, PlannerState
from backend.core.planning.planner import HTNPlanner
from backend.core.planning.decision_network import DecisionNetworkEngine
from backend.core.planning.resumable_runtime import ResumableWorkflowRuntime
from backend.core.reflection.outcome_evaluator import OutcomeEvaluator
from backend.core.reflection.reflection_generator import ReflectionGenerator
from backend.core.reflection.counterfactual_engine import CounterfactualSimulationEngine

logger = logging.getLogger(__name__)


class CognitiveOrchestrator:
    """Orchestrates closed-loop cognitive cycles from goal input to policy adaptation."""

    def __init__(
        self,
        runtime: Optional[ResumableWorkflowRuntime] = None,
    ) -> None:
        self.runtime = runtime or ResumableWorkflowRuntime()

    def run_cognitive_cycle(
        self,
        goal: Goal,
        initial_state: PlannerState,
        htn_planner: HTNPlanner,
        step_executor: Callable[[Operator], None],
        success_probability_map: Dict[str, float],
        scenario_weights: Dict[str, float],
        operator_substitution_map: Dict[str, List[Operator]],
    ) -> Dict[str, Any]:
        """Runs the complete cognitive sequence: plan, select, run, evaluate, reflect, simulate."""
        logger.info(f"Starting cognitive cycle for goal: {goal.name}")

        # 1. Generate baseline plan using HTN decomposition
        plan = htn_planner.find_plan(goal, initial_state)
        if plan is None:
            return {
                "status": "failed_planning",
                "detail": f"HTN planner failed to decompose goal: {goal.name}",
            }

        # 2. Select optimal policy plan under uncertainty (can check substitutions as alternatives)
        alternatives = CounterfactualSimulationEngine.generate_alternatives(
            plan,
            operator_substitution_map,
        )
        all_candidate_plans = [plan] + alternatives

        selected_plan, _ = DecisionNetworkEngine.select_optimal_policy(
            all_candidate_plans,
            success_probability_map,
            scenario_weights,
        )
        logger.info(f"Policy selected: {selected_plan.plan_id}")

        # 3. Execute plan via ResumableWorkflowRuntime
        run_res = self.runtime.execute_plan(selected_plan, initial_state, step_executor)

        # 4. Evaluate execution outcome metrics
        actual_cost = selected_plan.expected_cost
        actual_duration = selected_plan.expected_duration
        if run_res["status"] == "failed":
            # Adjust costs based on failure step count
            completed_count = run_res["step_index"]
            actual_cost = sum(op.estimated_cost for op in selected_plan.steps[:completed_count])
            actual_duration = sum(op.estimated_time for op in selected_plan.steps[:completed_count])

        evaluation = OutcomeEvaluator.evaluate_outcome(
            plan=selected_plan,
            final_variables=run_res["variables"],
            actual_cost=actual_cost,
            actual_duration=actual_duration,
        )

        # 5. Generate reflection logs
        reflection = ReflectionGenerator.generate_reflection(
            plan=selected_plan,
            evaluation=evaluation,
            failed_step_index=run_res.get("step_index"),
            failed_operator=run_res.get("failed_operator"),
            failure_detail=run_res.get("detail"),
        )

        # 6. Counterfactual Analysis: simulate alternatives to check if we would have run better
        counterfactual_runs = []
        for alt in alternatives:
            sim_res = CounterfactualSimulationEngine.simulate_alternative(alt, initial_state.variables)
            counterfactual_runs.append(sim_res)

        utility_comparison = CounterfactualSimulationEngine.compare_utility(
            original_outcome={
                "plan_id": selected_plan.plan_id,
                "is_success": evaluation["is_success"],
                "actual_cost": actual_cost,
                "actual_duration": actual_duration,
            },
            simulated_runs=counterfactual_runs,
        )

        # 7. Package complete cognitive review trace
        return {
            "status": "success" if evaluation["is_success"] else "failed",
            "selected_plan_id": selected_plan.plan_id,
            "execution_outcome": run_res,
            "evaluation": evaluation,
            "reflection": reflection,
            "counterfactual_utility": utility_comparison,
        }
