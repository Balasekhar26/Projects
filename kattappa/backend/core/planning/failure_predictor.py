"""Failure Predictor Diagnostician (Program 12.3).
"""
from __future__ import annotations

from typing import Any, Dict, List
from backend.core.planning.plan import Plan


class FailurePredictor:
    """Predicts potential failure modes for a candidate Plan based on task metrics and state variables."""

    def predict_failure_modes(self, plan: Plan, world_state: Dict[str, Any]) -> List[str]:
        """Scans plan parameters and environment states to output potential failure triggers."""
        failures = []

        # 1. Check environmental triggers
        if world_state.get("internet_instability", False):
            for node in plan.graph.nodes.values():
                cost_vector = getattr(node, "cost_vector", {})
                if cost_vector.get("api_tokens", 0.0) > 0.0:
                    failures.append(
                        f"Task '{node.title}' requires API access but internet is marked unstable."
                    )

        # 2. Check task-level success margins
        for node in plan.graph.nodes.values():
            success_prob = getattr(node, "success_probability", 1.0)
            if success_prob < 0.95:
                failures.append(
                    f"Task '{node.title}' has low base success probability ({success_prob * 100}%)."
                )

        # 3. Check low resource limits
        if world_state.get("resource_constrain_cpu", False):
            failures.append("Execution environment is CPU resource-constrained, risking task timeouts.")

        return failures
