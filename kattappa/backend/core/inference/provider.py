"""Inference Provider Interface and Adapters (Program 10).

Defines BaseProvider abstract base class and simulator adapters.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict

from backend.core.inference.models import InferenceRequest, InferenceResponse


class BaseProvider(ABC):
    """Abstract contract representing a unified LLM API client adapter."""

    @abstractmethod
    def execute(self, request: InferenceRequest) -> InferenceResponse:
        pass


class MockProvider(BaseProvider):
    """Simulates provider connections, returning predictable mock responses."""

    def __init__(self, model_name: str = "mock-gpt-4") -> None:
        self.model_name = model_name
        self.throw_error = False

    def execute(self, request: InferenceRequest) -> InferenceResponse:
        if self.throw_error:
            raise RuntimeError(f"Connection timed out for provider {self.model_name}")

        start_time = time.time()
        # Basic mock output compilation
        text = f"Mock response from model {self.model_name} answering: {request.prompt[:30]}"
        
        # Calculate simulated costs (approx $0.03 per 1k input tokens, $0.06 per 1k output tokens)
        input_tokens = len(request.prompt) // 4
        output_tokens = len(text) // 4
        cost = (input_tokens * 0.00003) + (output_tokens * 0.00006)
        latency = time.time() - start_time

        return InferenceResponse(
            text_content=text,
            model_used=self.model_name,
            cost=cost,
            latency=latency,
            token_usage={"input": input_tokens, "output": output_tokens},
        )
