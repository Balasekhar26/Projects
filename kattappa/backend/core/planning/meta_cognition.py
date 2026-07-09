"""Meta-Cognition Engine (Program 43.0).

Enables Kattappa to reason about its own reasoning processes: tracks internal states,
calibrates confidence thresholds, allocates token and planning budgets, introspects
decision clarity, and dynamically routes planner selections.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class SelfAwarenessState:
    """Tracks Kattappa's internal cognitive performance metrics."""
    confidence: float = 1.0
    uncertainty: float = 0.0
    fatigue_metric: float = 0.0
    resource_consumption: float = 0.0
    failure_count: int = 0


class ConfidenceManager:
    """Estimates and calibrates execution confidence, defining escalation policies."""

    @classmethod
    def calibrate_confidence(cls, state: SelfAwarenessState, complexity: float) -> float:
        """Derives a calibrated confidence rating between 0.0 and 1.0."""
        # Baseline confidence matches inverse of state uncertainty
        calibrated = 1.0 - state.uncertainty

        # Adjust for complexity (higher complexity reduces confidence baseline)
        calibrated -= 0.05 * complexity

        # Deduct heavily for failures and fatigue limits
        calibrated -= 0.1 * state.failure_count
        calibrated -= 0.05 * state.fatigue_metric

        return max(0.0, min(1.0, round(calibrated, 2)))

    @classmethod
    def get_escalation_action(cls, confidence: float) -> str:
        """Determines automation limits and human-in-the-loop escalation gates."""
        if confidence < 0.40:
            return "ASK_HUMAN"
        elif confidence < 0.70:
            return "EXECUTE_CONSERVATIVE"
        else:
            return "AUTONOMOUS"


class ComputeAllocator:
    """Allocates computational budgets dynamically based on task properties."""

    @classmethod
    def allocate_compute(cls, task_priority: str, complexity: float) -> Dict[str, Any]:
        """Maps priorities and complexities to token limits and simulation budgets."""
        # Base budgets
        token_budget = 4000
        simulation_iterations = 5
        planning_timeout = 5.0

        # Adjust for task priority
        p = task_priority.upper()
        if p == "HIGH":
            token_budget = 10000
            simulation_iterations = 20
            planning_timeout = 15.0
        elif p == "CRITICAL":
            token_budget = 30000
            simulation_iterations = 50
            planning_timeout = 30.0

        # Scale iteratively by complexity
        scale_factor = 1.0 + (0.1 * complexity)
        token_budget = int(token_budget * scale_factor)
        simulation_iterations = int(simulation_iterations * scale_factor)

        return {
            "token_budget": token_budget,
            "simulation_iterations": simulation_iterations,
            "planning_timeout": round(planning_timeout * scale_factor, 2),
        }


class IntrospectionEngine:
    """Evaluates cognitive readiness and decides if more reasoning iterations are needed."""

    @classmethod
    def introspect(cls, state: SelfAwarenessState, current_plan_success_prob: float) -> str:
        """Determines if the system knows enough, should think longer, or escalates to the user."""
        # 1. Check escalation conditions (high failure rates or severe uncertainty)
        if state.failure_count >= 3 or state.uncertainty > 0.80:
            return "NEED_HELP"

        # 2. Check if current solution is not solid (e.g. low probability success)
        if current_plan_success_prob < 0.60:
            return "THINK_LONGER"

        # 3. Default proceed
        return "PROCEED"


class MetaReasoner:
    """Routes goal configurations to optimal planner strategies."""

    @classmethod
    def select_planner_strategy(cls, complexity: float, uncertainty: float) -> str:
        """Dynamically chooses routing architectures based on complexity and uncertainty."""
        if complexity < 3.0:
            return "RULE_PLANNER"
        elif complexity >= 3.0 and uncertainty < 0.50:
            return "HTN_PLANNER"
        else:
            return "HYBRID_DECISION_NETWORK"
