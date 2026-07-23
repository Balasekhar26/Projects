"""
Unavailable Model Client — Fail-closed default when no production model is configured.
"""

from __future__ import annotations

from backend.core.model_clients.protocol import ModelRequest, ModelResponse


class UnavailableModelClient:
    """Fail-closed default model client returning structured failure without fabricating success."""

    def ask(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            success=False,
            text="",
            confidence=0.0,
            error="NO_MODEL_CLIENT_CONFIGURED"
        )
