"""
Deterministic Model Client Test Double for Offline Execution.
"""

from __future__ import annotations

from backend.core.model_clients.protocol import ModelRequest, ModelResponse


class DeterministicModelClient:
    """Deterministic test double for offline execution without network access."""

    def __init__(self, default_response: str = "PASS", confidence: float = 0.85):
        self.default_response = default_response
        self.confidence = confidence
        self.call_count = 0
        self.last_request = None

    def ask(self, request: ModelRequest) -> ModelResponse:
        self.call_count += 1
        self.last_request = request
        return ModelResponse(success=True, text=self.default_response, confidence=self.confidence)
