"""Execution Telemetry Monitor (Program 5G-6).

Tracks performance metrics like task duration, latency, and resource usage.
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Dict

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    total_duration: float = 0.0
    task_latencies: Dict[str, float] = field(default_factory=dict)
    failures_count: int = 0
    retries_count: int = 0


class ExecutionMonitor:
    """Collects and organizes runtime statistics during plan execution runs."""

    def __init__(self) -> None:
        self.metrics: Dict[str, PerformanceMetrics] = {}
        self.start_times: Dict[str, float] = {}

    def start_session(self, session_id: str) -> None:
        self.metrics[session_id] = PerformanceMetrics()
        self.start_times[session_id] = time.time()

    def record_task_start(self, session_id: str, node_id: str) -> None:
        self.start_times[f"{session_id}_{node_id}"] = time.time()

    def record_task_end(self, session_id: str, node_id: str) -> None:
        key = f"{session_id}_{node_id}"
        if key in self.start_times:
            latency = time.time() - self.start_times[key]
            if session_id in self.metrics:
                self.metrics[session_id].task_latencies[node_id] = latency

    def record_failure(self, session_id: str) -> None:
        if session_id in self.metrics:
            self.metrics[session_id].failures_count += 1

    def record_retry(self, session_id: str) -> None:
        if session_id in self.metrics:
            self.metrics[session_id].retries_count += 1

    def end_session(self, session_id: str) -> PerformanceMetrics:
        if session_id in self.start_times and session_id in self.metrics:
            self.metrics[session_id].total_duration = time.time() - self.start_times[session_id]
        return self.metrics.get(session_id, PerformanceMetrics())
