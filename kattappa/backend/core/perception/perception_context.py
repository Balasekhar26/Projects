"""Perception Context (Program 18.0).

Maintains a sliding visual history of perception frames and structures.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from backend.core.perception.perception_frame import PerceptionFrame
from backend.core.perception.screen_graph import ScreenGraph

logger = logging.getLogger(__name__)


class PerceptionContext:
    """Thread-safe visual execution memory holding frame updates and layout changes."""

    def __init__(self, max_history: int = 10) -> None:
        self.max_history = max_history
        self._history: List[PerceptionFrame] = []
        self._latest_graph: Optional[ScreenGraph] = None
        self._lock = threading.Lock()

    def update_frame(self, frame: PerceptionFrame, screen_graph: Optional[ScreenGraph] = None) -> None:
        """Register a new captured frame to the sliding perception context."""
        with self._lock:
            self._history.append(frame)
            if len(self._history) > self.max_history:
                self._history.pop(0)

            if screen_graph:
                self._latest_graph = screen_graph
            logger.debug("PerceptionContext: Added frame %s, history length = %d", frame.frame_id, len(self._history))

    def get_latest_frame(self) -> Optional[PerceptionFrame]:
        with self._lock:
            return self._history[-1] if self._history else None

    def get_latest_graph(self) -> Optional[ScreenGraph]:
        with self._lock:
            return self._latest_graph

    def get_visible_text(self) -> str:
        """Returns consolidated visible text parsed from the latest screen graph."""
        graph = self.get_latest_graph()
        if not graph or not graph.text_nodes:
            return ""
        return "\n".join(node["text"] for node in graph.text_nodes)

    def get_context_summary(self) -> Dict[str, Any]:
        """Compiles standard visible and application metadata."""
        latest = self.get_latest_frame()
        graph = self.get_latest_graph()
        
        if not latest:
            return {"active": False}

        return {
            "active": True,
            "frame_id": latest.frame_id,
            "timestamp": latest.timestamp,
            "source": latest.source,
            "window_title": latest.metadata.get("window_title", "Unknown"),
            "active_app": latest.metadata.get("active_app", "Unknown"),
            "elements_count": len(graph.text_nodes) if graph else 0,
            "visible_text_summary": self.get_visible_text()[:400]
        }
