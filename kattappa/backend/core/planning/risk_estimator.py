"""Causal Risk Estimator with SCM Integration (Program 12.3).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from backend.core.planning.plan import Plan
from backend.core.beliefs.causal_engine import StructuralCausalModel

logger = logging.getLogger(__name__)


class RiskEstimator:
    """Estimates plan execution risks by combining task parameters and causal belief state variables."""

    def __init__(self, scm: Optional[StructuralCausalModel] = None) -> None:
        self.scm = scm

    def estimate_risk(self, plan: Plan, world_state: Dict[str, Any]) -> float:
        """Computes a risk score between 0.0 (safe) and 1.0 (extremely risky)."""
        # 1. Base task-level risk aggregation (independent probability combinations)
        complement_product = 1.0
        for node in plan.graph.nodes.values():
            node_risk = getattr(node, "risk_score", 0.0)
            complement_product *= (1.0 - node_risk)

        base_risk = 1.0 - complement_product

        # 2. Causal environment risk boost (query SCM variables or world state)
        risk_boost = 0.0
        
        # If internet is marked unstable, online tasks get severe risk penalty
        if world_state.get("internet_instability", False):
            for node in plan.graph.nodes.values():
                cost_vector = getattr(node, "cost_vector", {})
                if cost_vector.get("api_tokens", 0.0) > 0.0:
                    # Boost risk due to network instability
                    risk_boost = max(risk_boost, 0.6)

        # Combine base risk and environmental risk boost securely
        final_risk = min(1.0, base_risk + risk_boost)
        return round(final_risk, 3)
