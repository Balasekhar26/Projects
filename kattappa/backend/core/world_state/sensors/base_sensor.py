from __future__ import annotations
from typing import Any

class BaseSensor:
    def collect(self) -> dict[str, Any]:
        """Collect environmental metrics from the system layer."""
        raise NotImplementedError
