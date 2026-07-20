"""Kattappa Voice package (Program 30.0)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.core.voice.context_buffer import MultimodalContextBuffer
    from backend.core.voice.orchestrator import CognitiveSessionOrchestrator

__all__ = [
    "MultimodalContextBuffer",
    "CognitiveSessionOrchestrator",
]


def __getattr__(name: str) -> Any:
    """Keep optional model/PyTorch code off the HTTP startup path."""

    if name == "MultimodalContextBuffer":
        from backend.core.voice.context_buffer import MultimodalContextBuffer

        return MultimodalContextBuffer
    if name == "CognitiveSessionOrchestrator":
        from backend.core.voice.orchestrator import CognitiveSessionOrchestrator

        return CognitiveSessionOrchestrator
    raise AttributeError(name)
