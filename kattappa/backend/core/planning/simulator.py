"""Planner Simulator Coordination Engine (Program 12.3).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.core.planning.plan import Plan
from backend.core.planning.simulation_result import SimulationResult
from backend.core.planning.risk_estimator import RiskEstimator
from backend.core.planning.utility_estimator import UtilityEstimator
from backend.core.planning.failure_predictor import FailurePredictor
from backend.core.beliefs.causal_engine import StructuralCausalModel

logger = logging.getLogger(__name__)


class PlannerSimulator:
    """Coordinates deterministic duration aggregation, probabilistic variance, SCM queries, and utility estimators."""

    def __init__(self, scm: Optional[StructuralCausalModel] = None) -> None:
        self.scm = scm
        self.risk_estimator = RiskEstimator(scm)
        self.utility_estimator = UtilityEstimator()
        self.failure_predictor = FailurePredictor()

    def simulate_plan(self, plan: Plan, world_state: Dict[str, Any]) -> SimulationResult:
        """Simulates candidate plan outcomes under world state parameters."""
        logger.info("Starting simulation for Plan '%s'...", plan.plan_id)

        # 1. Deterministic critical path and duration
        path, duration = plan.graph.calculate_critical_path()

        # 2. Probabilistic duration variance (sum of variances along critical path)
        variance = 0.0
        for node_id in path:
            node = plan.graph.nodes.get(node_id)
            if node:
                variance += getattr(node, "duration_variance", 0.0)

        # 3. Overall success probability (joint probability product across all nodes)
        success_prob = 1.0
        for node in plan.graph.nodes.values():
            success_prob *= getattr(node, "success_probability", 1.0)
        success_prob = round(success_prob, 3)

        # 4. Expected costs accumulation
        expected_cost = 0.0
        accumulated_costs = plan.metadata.get("accumulated_costs", {})
        expected_cost = accumulated_costs.get("dollars", 0.0)
        # If not populated in plan metadata, sum dollars cost vectors manually
        if expected_cost == 0.0:
            for node in plan.graph.nodes.values():
                cost_vec = getattr(node, "cost_vector", {})
                expected_cost += cost_vec.get("dollars", 0.0)

        # 5. Risk score & Confidence aggregation
        risk_score = self.risk_estimator.estimate_risk(plan, world_state)
        
        node_confidences = [getattr(n, "confidence", 1.0) for n in plan.graph.nodes.values()]
        avg_confidence = round(sum(node_confidences) / len(node_confidences), 3) if node_confidences else 1.0

        # 6. Predict Failure Modes
        failures = self.failure_predictor.predict_failure_modes(plan, world_state)

        # 7. Evaluate Expected Utility
        # Retrieve reward from plan metadata, default to 100.0
        reward = world_state.get("goal_reward", 100.0)
        expected_utility = self.utility_estimator.calculate_utility(
            success_probability=success_prob,
            reward=reward,
            expected_cost=expected_cost,
            risk_score=risk_score,
        )

        return SimulationResult(
            success_probability=success_prob,
            expected_duration=round(duration, 3),
            duration_variance=round(variance, 3),
            expected_cost=round(expected_cost, 3),
            risk_score=risk_score,
            failure_modes=failures,
            confidence=avg_confidence,
            metadata={
                "expected_utility": expected_utility,
                "critical_path": path,
            }
        )

# Speedy formulas outperform heavy rollouts at this stage.


