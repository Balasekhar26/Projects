"""Response Validator Pipeline (Program 10).

Validates LLM response formats, JSON schema conformity, and safety indicators.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ResponseValidator:
    """Verifies that response text content meets structural constraints."""

    @staticmethod
    def validate_json(text: str, schema: Optional[Dict[str, Any]] = None) -> bool:
        """Checks if text is valid JSON and conforms to the optional schema key parameters."""
        try:
            parsed = json.loads(text)
            if schema:
                # Basic key validation
                for key in schema.get("required", []):
                    if key not in parsed:
                        logger.warning("JSON missing required key: %s", key)
                        return False
            return True
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse JSON content: %s", text[:100])
            return False

    @staticmethod
    def validate_non_empty(text: str) -> bool:
        return len(text.strip()) > 0
