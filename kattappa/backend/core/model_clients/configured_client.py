"""
Production Configured Model Client.
Routes requests to the configured local model backend with explicit timeout, cancellation, and failure handling.
"""

from __future__ import annotations

import logging
from backend.core.model_clients.protocol import ModelClient, ModelRequest, ModelResponse

logger = logging.getLogger(__name__)


class ConfiguredModelClient:
    """Production client using local model backend with explicit timeouts."""

    def __init__(self, endpoint_url: str = "http://127.0.0.1:11434/api/generate"):
        self.endpoint_url = endpoint_url

    def ask(self, request: ModelRequest) -> ModelResponse:
        try:
            # Production client attempt to query configured local model endpoint
            import urllib.request
            import json

            payload = json.dumps({"prompt": request.prompt, "stream": False}).encode("utf-8")
            req = urllib.request.Request(self.endpoint_url, data=payload, headers={"Content-Type": "application/json"})
            
            with urllib.request.urlopen(req, timeout=request.timeout_sec) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return ModelResponse(success=True, text=data.get("response", ""), confidence=0.85)
        except Exception as exc:
            logger.warning("ConfiguredModelClient request failed: %s", exc)
            return ModelResponse(success=False, error=type(exc).__name__, confidence=0.0)
