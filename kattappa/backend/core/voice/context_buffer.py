"""Multimodal Context Buffer (Program 30.0).

Maintains a temporal sliding history window containing interleaved text prompts,
audio chunk paths/features, visual frames, and tool execution logs.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List


class MultimodalContextBuffer:
    """Sliding-window temporal context buffer for multi-modal conversational inputs."""

    def __init__(self, max_history_size: int = 50) -> None:
        self.max_history_size = max_history_size
        self.buffer: List[Dict[str, Any]] = []

    def append_interaction(self, modality: str, data: Any) -> None:
        """Appends a new interaction event, enforcing sliding window bounds."""
        if modality not in ("text", "audio", "image", "tool"):
            raise ValueError(f"Unsupported modality: {modality}")

        entry = {
            "timestamp": time.time(),
            "modality": modality,
            "data": data,
        }

        self.buffer.append(entry)

        # Enforce history limit by dropping oldest entries
        if len(self.buffer) > self.max_history_size:
            self.buffer = self.buffer[-self.max_history_size :]

    def get_flattened_context(self) -> List[Dict[str, Any]]:
        """Returns the chronological history of active interactions."""
        return list(self.buffer)

    def clear(self) -> None:
        """Resets the context buffer."""
        self.buffer.clear()

    @property
    def size(self) -> int:
        return len(self.buffer)
