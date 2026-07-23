"""
Production Configured Model Client.
Routes requests to the configured local model backend with explicit timeouts, connection limits, and response validation.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Optional

from backend.core.model_clients.protocol import ModelClient, ModelRequest, ModelResponse

logger = logging.getLogger(__name__)


class ConfiguredModelClient:
    """Production client using local model backend with explicit configuration and response validation."""

    def __init__(
        self,
        endpoint_url: str = "http://127.0.0.1:11434/api/generate",
        model_name: str = "kattappa-local",
        request_timeout_sec: float = 5.0,
        connect_timeout_sec: float = 2.0,
        max_response_bytes: int = 10 * 1024 * 1024
    ):
        self.endpoint_url = endpoint_url
        self.model_name = model_name
        self.request_timeout_sec = request_timeout_sec
        self.connect_timeout_sec = connect_timeout_sec
        self.max_response_bytes = max_response_bytes

    def health_check(self) -> bool:
        try:
            req = urllib.request.Request(self.endpoint_url, method="HEAD")
            with urllib.request.urlopen(req, timeout=self.connect_timeout_sec):
                return True
        except Exception:
            return False

    def ask(self, request: ModelRequest) -> ModelResponse:
        try:
            payload = json.dumps({
                "model": self.model_name,
                "prompt": request.prompt,
                "stream": False
            }).encode("utf-8")

            req = urllib.request.Request(
                self.endpoint_url,
                data=payload,
                headers={"Content-Type": "application/json"}
            )

            effective_timeout = request.timeout_sec or self.request_timeout_sec

            with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                if resp.status != 200:
                    return ModelResponse(success=False, error=f"HTTP_{resp.status}", confidence=0.0)

                raw_data = resp.read(self.max_response_bytes + 1)
                if len(raw_data) > self.max_response_bytes:
                    return ModelResponse(success=False, error="OVERSIZED_RESPONSE", confidence=0.0)

                if not raw_data:
                    return ModelResponse(success=False, error="EMPTY_RESPONSE", confidence=0.0)

                data = json.loads(raw_data.decode("utf-8"))
                if not isinstance(data, dict):
                    return ModelResponse(success=False, error="MALFORMED_JSON_STRUCTURE", confidence=0.0)

                response_text = data.get("response", "")
                if not response_text:
                    return ModelResponse(success=False, error="EMPTY_OUTPUT_TEXT", confidence=0.0)

                return ModelResponse(success=True, text=str(response_text), confidence=0.85)

        except urllib.error.HTTPError as http_err:
            return ModelResponse(success=False, error=f"HTTP_{http_err.code}", confidence=0.0)
        except urllib.error.URLError as url_err:
            return ModelResponse(success=False, error="CONNECTION_REFUSED", confidence=0.0)
        except TimeoutError:
            return ModelResponse(success=False, error="TIMEOUT", confidence=0.0)
        except Exception as exc:
            return ModelResponse(success=False, error=type(exc).__name__, confidence=0.0)
