"""Master Inference Engine Coordinator (Program 10).

Orchestrates prompt compilation, capability routing, fallback chains execution,
response caching, and token cost tracking.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from backend.core.inference.models import InferenceRequest, InferenceResponse
from backend.core.inference.provider import BaseProvider, MockProvider
from backend.core.inference.routing import RoutingEngine
from backend.core.inference.fallback import FallbackEngine
from backend.core.inference.cost import CostManager
from backend.core.inference.response_cache import ResponseCache

logger = logging.getLogger(__name__)


class InferenceEngine:
    """Master controller managing the Kattappa inference platform pipeline."""

    _instance: Optional[InferenceEngine] = None

    def __init__(self) -> None:
        self.router = RoutingEngine()
        self.cost_mgr = CostManager.get_instance()
        self.cache = ResponseCache()
        
        # Register default adapters mapping model names to Provider clients
        self.providers: Dict[str, BaseProvider] = {
            "gpt-4o": MockProvider("gpt-4o"),
            "claude-3-5-sonnet": MockProvider("claude-3-5-sonnet"),
            "gemini-1.5-pro": MockProvider("gemini-1.5-pro"),
            "ollama-llama-3": MockProvider("ollama-llama-3"),
        }
        self.fallback_engine = FallbackEngine(self.providers)

    @classmethod
    def get_instance(cls) -> InferenceEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_provider(self, model_name: str, provider: BaseProvider) -> None:
        self.providers[model_name] = provider

    def execute_inference(
        self,
        request: InferenceRequest,
        bypass_cache: bool = False,
    ) -> InferenceResponse:
        """Executes prompt inference through cache -> router -> fallback executor -> cost auditor."""
        # 1. Cache check
        if not bypass_cache:
            cached = self.cache.get(request.prompt, request.system_instruction)
            if cached:
                logger.info("Inference Cache hit.")
                return cached

        # 2. Select optimal target model using RoutingEngine
        primary_model = self.router.route(request)

        # 3. Compile fallback chain sequence (Try primary model, then fall back through others)
        model_chain = [primary_model]
        # Append other eligible models as backups
        all_models = ["gpt-4o", "claude-3-5-sonnet", "gemini-1.5-pro", "ollama-llama-3"]
        for m in all_models:
            if m not in model_chain:
                model_chain.append(m)

        # 4. Execute with FallbackEngine failovers
        start_time = time.time()
        response = self.fallback_engine.execute_with_fallback(request, model_chain)
        response.latency = time.time() - start_time

        # 5. Record usage cost totals
        self.cost_mgr.record_usage(
            cost=response.cost,
            input_tokens=response.token_usage.get("input", 0),
            output_tokens=response.token_usage.get("output", 0),
        )

        # 6. Cache response
        self.cache.put(request.prompt, request.system_instruction, response)

        return response
