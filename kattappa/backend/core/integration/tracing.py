"""Cognitive Integration Distributed Tracing Engine (Program 8).

Tracks timing metrics and sequence pathways across cognitive loops.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.core.integration.events import CognitiveEvent

logger = logging.getLogger(__name__)


@dataclass
class TraceSpan:
    span_id: str
    trace_id: str
    source: str
    start_time: float
    end_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class CognitiveTracer:
    """Orchestrates structured distributed tracing for module boundaries."""

    _instance: Optional[CognitiveTracer] = None

    def __init__(self) -> None:
        self.spans: Dict[str, TraceSpan] = {}
        self.events: List[CognitiveEvent] = []

    @classmethod
    def get_instance(cls) -> CognitiveTracer:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start_span(self, trace_id: str, source: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Begins recording a new cognitive span."""
        span_id = f"span_{source.lower()}_{int(time.time() * 1000) % 100000}"
        self.spans[span_id] = TraceSpan(
            span_id=span_id,
            trace_id=trace_id,
            source=source,
            start_time=time.time(),
            metadata=metadata or {},
        )
        logger.info("Started span %s for trace %s from %s", span_id, trace_id, source)
        return span_id

    def end_span(self, span_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Completes span recording, calculating elapsed runtime."""
        span = self.spans.get(span_id)
        if span:
            span.end_time = time.time()
            if metadata:
                span.metadata.update(metadata)
            duration = span.end_time - span.start_time
            logger.info("Ended span %s. Duration: %.3fs", span_id, duration)

    def record_event(self, event: CognitiveEvent) -> None:
        """Logs global events for structural review."""
        self.events.append(event)
        logger.info("Recorded event %s type %s from %s", event.event_id, event.event_type, event.source)

    def get_trace_history(self, trace_id: str) -> List[Dict[str, Any]]:
        """Returns sequence timeline details for a target trace ID."""
        trace_spans = [s for s in self.spans.values() if s.trace_id == trace_id]
        trace_spans.sort(key=lambda s: s.start_time)

        history = []
        for span in trace_spans:
            duration = (span.end_time - span.start_time) if span.end_time else 0.0
            history.append({
                "span_id": span.span_id,
                "source": span.source,
                "duration": duration,
                "metadata": span.metadata,
            })
        return history
