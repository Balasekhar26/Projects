"""Inference Routing Engine (Program 10).

Matches incoming request criteria against model registries to resolve optimal configurations.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from backend.core.inference.models import InferenceRequest
from backend.core.inference.capabilities import CapabilitiesRegistry, ModelCapabilities

logger = logging.getLogger(__name__)


class RoutingEngine:
    """Selects the best model ID based on request capabilities requirements, cost, and latency caps."""

    def __init__(self) -> None:
        self.registry = CapabilitiesRegistry.get_instance()

    def route(self, request: InferenceRequest) -> str:
        """Selects the optimal model ID, falling back to lower-cost/local options if caps are hit."""
        eligible_models: List[ModelCapabilities] = []

        for model_name in self.registry.list_models():
            caps = self.registry.get_capabilities(model_name)
            if not caps:
                continue

            # Check required capabilities
            meets_requirements = True
            for req in request.required_capabilities:
                if req == "supports_tools" and not caps.supports_tools:
                    meets_requirements = False
                elif req == "supports_json" and not caps.supports_json:
                    meets_requirements = False
                elif req == "local" and "local" not in caps.additional_flags:
                    meets_requirements = False

            if meets_requirements:
                eligible_models.append(caps)

        if not eligible_models:
            # Fall back to default local if requirements cannot be met
            logger.warning("No model met all required capabilities. Defaulting to local model.")
            return "ollama-llama-3"

        # Sort matching models by cost (input + output rate)
        # Choose the model that has lowest pricing
        eligible_models.sort(key=lambda m: (m.cost_per_1k_input + m.cost_per_1k_output))
        
        # Filter by cost boundaries
        for model in eligible_models:
            # Check if estimated cost fits within limits
            estimated_cost = (model.cost_per_1k_input + model.cost_per_1k_output) * 0.05
            if estimated_cost <= request.max_cost:
                logger.info("Routed request to model: %s", model.model_name)
                return model.model_name

        # If none fit, return the cheapest overall
        logger.info("Defaulting to cheapest model: %s", eligible_models[0].model_name)
        return eligible_models[0].model_name
