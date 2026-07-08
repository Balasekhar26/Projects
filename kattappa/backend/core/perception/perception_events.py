"""Perception Events (Program 18.0).

Publishes privacy-compliant perception audit traces to the central event bus.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Events constants
PERCEPTION_CAPTURE           = "PerceptionCapture"
PERCEPTION_OCR_COMPLETE      = "PerceptionOCRComplete"
PERCEPTION_GROUNDING_MATCH   = "PerceptionGroundingMatch"
PERCEPTION_ANOMALY_DETECTED  = "PerceptionAnomalyDetected"


def _publish(event_name: str, payload: Dict[str, Any]) -> None:
    try:
        from backend.core.event_bus import EVENT_BUS
        EVENT_BUS.publish(event_name, payload=payload, source="core.perception")
    except Exception as exc:
        logger.debug("PerceptionEvents: could not publish %s — %s", event_name, exc)


def emit_frame_captured(frame_id: str, source: str, frame_hash: str, size_bytes: int) -> None:
    """Logs frame capture events without storing raw bytes/biometrics."""
    _publish(PERCEPTION_CAPTURE, {
        "frame_id": frame_id,
        "source": source,
        "hash": frame_hash,
        "size_bytes": size_bytes,
        "privacy_gated": True
    })


def emit_ocr_complete(frame_id: str, word_count: int, confidence: float) -> None:
    _publish(PERCEPTION_OCR_COMPLETE, {
        "frame_id": frame_id,
        "word_count": word_count,
        "average_confidence": confidence
    })


def emit_grounding_match(query: str, match_text: str, confidence: float, center_coords: tuple[int, int]) -> None:
    _publish(PERCEPTION_GROUNDING_MATCH, {
        "query": query,
        "matched_label": match_text,
        "confidence": confidence,
        "center": center_coords
    })


def emit_anomaly_detected(frame_id: str, error_labels: list[str]) -> None:
    _publish(PERCEPTION_ANOMALY_DETECTED, {
        "frame_id": frame_id,
        "detected_errors_count": len(error_labels),
        "errors": error_labels
    })
