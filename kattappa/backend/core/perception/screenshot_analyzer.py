"""Screenshot Analyzer (Program 18.0).

Scans screenshots for visual bugs, popups, dialog boxes, and text error banners.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from backend.core.perception.screen_graph import ScreenGraph

logger = logging.getLogger(__name__)


class ScreenshotAnalyzer:
    """Scans structured screen layout graphs for semantic warning nodes or popup containers."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def inspect_layout(screen_graph: ScreenGraph) -> Dict[str, Any]:
        """Examines screen graph nodes for common visual anomalies or modal titles.

        Returns analysis report:
            {
                "success": bool,
                "popup_detected": bool,
                "anomaly_detected": bool,
                "critical_errors": list[str]
            }
        """
        popup_detected = False
        anomaly_detected = False
        critical_errors = []

        error_keywords = ["error", "failed", "crash", "denied", "exception", "unauthorized"]
        popup_headers = ["confirm", "warning", "permission", "alert", "modal", "dialog"]

        for node in screen_graph.text_nodes:
            text_lower = node["text"].lower()
            
            # 1. Look for error keywords
            for err in error_keywords:
                if err in text_lower:
                    anomaly_detected = True
                    critical_errors.append(node["text"])
                    break

            # 2. Look for modal/dialog identifiers
            for pop in popup_headers:
                if pop in text_lower:
                    # If this is near top of its column, likely a header/dialog box title
                    popup_detected = True
                    break

        return {
            "success": True,
            "popup_detected": popup_detected,
            "anomaly_detected": anomaly_detected,
            "critical_errors": list(set(critical_errors))
        }
