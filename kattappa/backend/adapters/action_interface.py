from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List

class ActionResult:
    """Unified result returned by all environmental adapters."""

    def __init__(
        self,
        success: bool,
        message: str,
        data: Dict[str, Any] = None,
        retryable: bool = False,
        latency_ms: float = 0.0
    ) -> None:
        self.success = success
        self.message = message
        self.data = data or {}
        self.retryable = retryable
        self.latency_ms = latency_ms


class ActionAdapter(ABC):
    """Abstract base class establishing the capability adapter protocol."""

    @abstractmethod
    def execute(self, action_name: str, payload: Dict[str, Any]) -> ActionResult:
        pass

    @abstractmethod
    def validate(self, payload: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def capabilities(self) -> List[str]:
        pass
