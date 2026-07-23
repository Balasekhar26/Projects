"""
Production ModelClient Protocol & Dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ModelRequest:
    prompt: str
    timeout_sec: float = 5.0
    context: str = ""


@dataclass
class ModelResponse:
    success: bool
    text: str = ""
    confidence: float = 0.80
    error: str = ""


class ModelClient(Protocol):
    """Explicit production model dependency interface."""

    def ask(self, request: ModelRequest) -> ModelResponse:
        ...
