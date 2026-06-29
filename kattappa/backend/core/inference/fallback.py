"""Fallback Chain Execution Handler (Program 10).

Attempts backups in a model sequence chain upon API connection errors.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from backend.core.inference.models import InferenceRequest, InferenceResponse
from backend.core.inference.provider import BaseProvider

logger = logging.getLogger(__name__)


class FallbackEngine:
    """Orchestrates backup model execution failovers when primary options throw errors."""

    def __init__(self, providers: Dict[str, BaseProvider]) -> None:
        self.providers = providers

    def execute_with_fallback(
        self,
        request: InferenceRequest,
        model_chain: List[str],
    ) -> InferenceResponse:
        """Executes request down a model chain sequence until one succeeds."""
        errors = []
        for model in model_chain:
            provider = self.providers.get(model)
            if not provider:
                logger.warning("Provider for model '%s' not registered. Skipping.", model)
                continue

            try:
                logger.info("Attempting inference on model: %s", model)
                # execute request
                # To simulate provider model selection, temporarily override model name
                if hasattr(provider, "model_name"):
                    provider.model_name = model
                
                response = provider.execute(request)
                logger.info("Successfully executed inference on model: %s", model)
                return response
            except Exception as exc:
                logger.error("Model '%s' failed. Error: %s", model, str(exc))
                errors.append(f"{model}: {str(exc)}")

        raise RuntimeError(f"All models in fallback chain failed. Errors: {'; '.join(errors)}")
