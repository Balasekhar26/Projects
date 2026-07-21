"""Latency Metrics Telemetry (Program 17.0).

Calculates and publishes conversational latencies to the ledger.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from backend.core.orchestrator.runtime import agent_events as ae

logger = logging.getLogger(__name__)


class LatencyMetrics:
    """Telemetry tracker for speech-to-text, reasoning, and synthesis response times."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

        # Timers
        self.turn_start_time: Optional[float] = None
        self.stt_start_time: Optional[float] = None
        self.planning_start_time: Optional[float] = None
        self.tts_start_time: Optional[float] = None

        # Latencies (in milliseconds)
        self.stt_latency_ms: float = 0.0
        self.planning_latency_ms: float = 0.0
        self.tts_start_latency_ms: float = 0.0
        self.end_to_end_latency_ms: float = 0.0

    def mark_turn_start(self) -> None:
        self.turn_start_time = time.perf_counter()

    def mark_stt_start(self) -> None:
        self.stt_start_time = time.perf_counter()

    def mark_stt_end(self) -> None:
        if self.stt_start_time:
            self.stt_latency_ms = (time.perf_counter() - self.stt_start_time) * 1000

    def mark_planning_start(self) -> None:
        self.planning_start_time = time.perf_counter()

    def mark_planning_end(self) -> None:
        if self.planning_start_time:
            self.planning_latency_ms = (time.perf_counter() - self.planning_start_time) * 1000

    def mark_tts_start(self) -> None:
        self.tts_start_time = time.perf_counter()

    def mark_tts_first_chunk(self) -> None:
        now = time.perf_counter()
        if self.tts_start_time:
            self.tts_start_latency_ms = (now - self.tts_start_time) * 1000
        if self.turn_start_time:
            self.end_to_end_latency_ms = (now - self.turn_start_time) * 1000

    def get_metrics_dict(self) -> Dict[str, float]:
        """Returns rounded metric values in milliseconds."""
        return {
            "stt_latency_ms": round(self.stt_latency_ms, 2),
            "planning_latency_ms": round(self.planning_latency_ms, 2),
            "tts_start_latency_ms": round(self.tts_start_latency_ms, 2),
            "end_to_end_latency_ms": round(self.end_to_end_latency_ms, 2),
        }

    def publish_telemetry(self) -> None:
        """Pushes structured telemetry payload to EventBus via agent_events."""
        metrics = self.get_metrics_dict()
        ae.emit_voice_telemetry(self.session_id, metrics)
        logger.info("Voice stream telemetry published for session %s: %s", self.session_id, metrics)
