"""Tool Result Schema Validator (Program 11).

Validates tool return structures against input schemas constraints.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class ToolResultValidator:
    """Verifies that tool output dictionaries conform to schema rules."""

    @staticmethod
    def validate(data: Any, schema: Optional[Dict[str, Any]] = None) -> bool:
        """Checks keys types in dictionary result data."""
        if schema is None:
            return True

        if not isinstance(data, dict):
            return False

        # Basic type matches
        for key, expected_type in schema.get("properties", {}).items():
            if key in data:
                val = data[key]
                # Validate simple types
                if expected_type == "int" and not isinstance(val, int):
                    return False
                elif expected_type == "str" and not isinstance(val, str):
                    return False
                elif expected_type == "float" and not isinstance(val, (float, int)):
                    return False

        # Check required fields
        for req in schema.get("required", []):
            if req not in data:
                return False

        return True
