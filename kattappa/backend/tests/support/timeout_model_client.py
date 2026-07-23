"""
Timeout & Failure Model Client Test Doubles for Offline Execution.
"""

from __future__ import annotations

from backend.core.model_clients.protocol import ModelRequest, ModelResponse


class TimeoutModelClient:
    """Test double simulating model request timeout."""

    def __init__(self):
        self.call_count = 0

    def ask(self, request: ModelRequest) -> ModelResponse:
        self.call_count += 1
        return ModelResponse(success=False, text="", confidence=0.0, error="TIMEOUT")


class FailureModelClient:
    """Test double simulating unavailable backend failure."""

    def __init__(self):
        self.call_count = 0

    def ask(self, request: ModelRequest) -> ModelResponse:
        self.call_count += 1
        return ModelResponse(success=False, text="", confidence=0.0, error="BACKEND_UNAVAILABLE")
