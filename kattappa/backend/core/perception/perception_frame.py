"""Perception Frame (Program 18.0).

Defines the core data representation structure for ingested visual frames.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class PerceptionFrame:
    """Represents a single visual snapshot captured by the perception engine."""
    frame_id: str = field(default_factory=lambda: f"frm_{uuid.uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time.time)
    source: str = "screenshot"  # screenshot, clipboard, file, video_stream
    image_bytes: bytes = b""    # Encoded image binaries (PNG/JPEG)
    metadata: Dict[str, Any] = field(default_factory=dict)
    workspace_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the frame object metadata (excluding raw binaries)."""
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "metadata": self.metadata,
            "workspace_id": self.workspace_id,
            "image_size_bytes": len(self.image_bytes),
        }
