"""Background Counterfactual Self-Play Engine (Program 41.0).

Hallucinates alternative planning paths, runs simulated rollouts, measures expected
utility scores, and saves high-scoring execution strategies to lifelong memory.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from backend.core.planning.goal import Goal
from backend.core.planning.task import Plan, Operator, PlannerState
from backend.core.planning.planner import HTNPlanner
from backend.core.planning.decision_network import DecisionNetworkEngine
from backend.core.reflection.counterfactual_engine import CounterfactualSimulationEngine
from backend.core.planning.strategy_memory import StrategyMemory, PolicyConsolidationEngine

logger = logging.getLogger(__name__)


class BackgroundSelfPlayEngine:
    """Simulates plan permutations in self-play mode to consolidate optimized policies."""

    @classmethod
    def run_self_play_simulation(
        cls,
        goal: Goal,
        initial_state: PlannerState,
        htn_planner: HTNPlanner,
        operator_substitution_map: Dict[str, List[Operator]],
        success_probability_map: Dict[str, float],
        scenario_weights: Dict[str, float],
        strategy_memory: StrategyMemory,
    ) -> Dict[str, Any]:
        """Runs offline permutations of tool sequences, scoring them and updating strategy memory."""
        logger.info(f"Starting self-play simulation for goal: {goal.name}")

        # 1. Plan baseline using HTN planner decomposition
        base_plan = htn_planner.find_plan(goal, initial_state)
        if base_plan is None:
            return {
                "status": "failed",
                "detail": "HTN planner failed to produce a base plan.",
            }

        # 2. Hallucinate candidate paths via counterfactual substitution sweeps
        alternatives = CounterfactualSimulationEngine.generate_alternatives(
            base_plan,
            operator_substitution_map,
        )
        if not alternatives:
            return {
                "status": "completed",
                "detail": "No alternative plan paths to explore.",
                "registered_policy_id": None,
            }

        # 3. Simulate rollouts and score expected utilities
        best_plan: Plan | None = None
        best_utility = -9999.0

        for alt in alternatives:
            # Check feasibility / preconditions
            sim_run = CounterfactualSimulationEngine.simulate_alternative(alt, initial_state.variables)
            if not sim_run["is_success"]:
                continue  # skip invalid path combinations

            # Compute utility expectation
            utility = DecisionNetworkEngine.compute_expected_utility(
                plan=alt,
                success_probability_map=success_probability_map,
                scenario_weights=scenario_weights,
            )

            if utility > best_utility:
                best_utility = utility
                best_plan = alt

        # 4. Automatically consolidate optimal choices if quality is high
        registered_id = None
        if best_plan is not None:
            # Synthesize outcome evaluation scores matching simulated utility
            simulated_score = max(0.0, min(1.0, (best_utility + 10.0) / 20.0))
            mock_evaluation = {
                "is_success": True,
                "score": simulated_score,
            }

            registered_id = PolicyConsolidationEngine.consolidate_trace(
                plan=best_plan,
                evaluation=mock_evaluation,
                memory=strategy_memory,
            )

        return {
            "status": "completed",
            "best_plan_id": best_plan.plan_id if best_plan else None,
            "best_utility": best_utility,
            "registered_policy_id": registered_id,
        }
