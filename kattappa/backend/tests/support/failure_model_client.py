"""
Failure Model Client Test Double for Offline Execution.
"""

from __future__ import annotations

from backend.core.model_clients.protocol import ModelRequest, ModelResponse


class FailureModelClient:
    """Test double simulating unavailable backend failure."""

    def __init__(self):
        self.call_count = 0

    def ask(self, request: ModelRequest) -> ModelResponse:
        self.call_count += 1
        return ModelResponse(success=False, text="", confidence=0.0, error="BACKEND_UNAVAILABLE")
