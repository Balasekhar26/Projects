"""Telemetry Collector (Program 28.0).

Provides a thread-safe distributed tracing framework with parent-child nesting,
log annotations, and execution timing context propagation.
"""
from __future__ import annotations

import functools
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

F_Type = TypeVar("F_Type", bound=Callable[..., Any])


@dataclass
class Span:
    """Represents a single measured segment of execution."""

    name: str
    span_id: str
    parent_span_id: Optional[str] = None
    trace_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = "success"  # "success" or "error"
    metadata: Dict[str, Any] = field(default_factory=dict)
    annotations: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration(self) -> float:
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time

    def annotate(self, message: str, **kwargs: Any) -> None:
        """Adds a timed log event annotation to this span."""
        self.annotations.append({
            "timestamp": time.time(),
            "message": message,
            **kwargs,
        })


class TelemetryCollector:
    """Thread-safe collector storing completed execution spans and active tracing states."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls) -> TelemetryCollector:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_collector()
            return cls._instance

    def _init_collector(self) -> None:
        self.spans: List[Span] = []
        self._global_lock = threading.RLock()
        self._local = threading.local()

    def clear(self) -> None:
        """Clears all gathered spans and resets thread-local state."""
        with self._global_lock:
            self.spans.clear()
            self._local.__dict__.clear()

    @property
    def _active_stack(self) -> List[Span]:
        if not hasattr(self._local, "stack"):
            self._local.stack = []
        return self._local.stack

    def start_span(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> Span:
        """Starts a new span. Automatically sets active parent span if nesting exists."""
        span_id = str(uuid.uuid4())
        parent_id = None
        trace_id = None

        stack = self._active_stack
        if stack:
            parent_id = stack[-1].span_id
            trace_id = stack[-1].trace_id
        else:
            trace_id = str(uuid.uuid4())

        span = Span(
            name=name,
            span_id=span_id,
            parent_span_id=parent_id,
            trace_id=trace_id,
            metadata=metadata or {},
        )

        stack.append(span)
        return span

    def finish_span(self, span: Span, status: str = "success") -> None:
        """Completes the span, records end time, and pushes it to global store."""
        span.end_time = time.time()
        span.status = status

        stack = self._active_stack
        if stack and stack[-1].span_id == span.span_id:
            stack.pop()

        with self._global_lock:
            self.spans.append(span)

    def get_active_span(self) -> Optional[Span]:
        """Returns the currently executing span for the current thread."""
        stack = self._active_stack
        return stack[-1] if stack else None

    def get_spans(self) -> List[Span]:
        """Returns a snapshot of all completed spans."""
        with self._global_lock:
            return list(self.spans)


class trace_span:
    """Context manager and decorator for tracing block execution."""

    def __init__(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.name = name
        self.metadata = metadata
        self.collector = TelemetryCollector()
        self.span: Optional[Span] = None

    def __enter__(self) -> Span:
        self.span = self.collector.start_span(self.name, self.metadata)
        return self.span

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.span:
            status = "error" if exc_type is not None else "success"
            if exc_val:
                self.span.metadata["exception_type"] = exc_type.__name__
                self.span.metadata["exception_message"] = str(exc_val)
            self.collector.finish_span(self.span, status=status)

    def __call__(self, func: F_Type) -> F_Type:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            meta = dict(self.metadata or {})
            meta["function"] = func.__name__
            with trace_span(self.name or func.__name__, metadata=meta):
                return func(*args, **kwargs)
        return cast(F_Type, wrapper)
