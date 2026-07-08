"""Failure Classification and Optimization Analysis (Program 6).

Categorizes task run failures and identifies planning parallelization opportunities.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.reflection.models import ExecutionRecord

logger = logging.getLogger(__name__)


class FailureClassifier:
    """Classifies execution errors into semantic categories."""

    @staticmethod
    def classify(failures: List[Dict[str, Any]]) -> Optional[str]:
        """Examines failure error strings to determine root cause category."""
        if not failures:
            return None

        # Look at the last failure message
        last_failure = failures[-1]
        msg = last_failure.get("error_message", "").lower()

        if "permission" in msg or "auth" in msg or "unauthorized" in msg:
            return "Permission"
        if "network" in msg or "connect" in msg or "socket" in msg:
            return "Network"
        if "api" in msg or "quota" in msg or "rate limit" in msg:
            return "API"
        if "timeout" in msg or "deadline" in msg:
            return "Temporal"
        if "resource" in msg or "gpu" in msg or "cpu" in msg:
            return "Resource"
        if "constraint" in msg:
            return "Constraint"
        if "planning" in msg:
            return "Planning"
        if "simulated" in msg or "crash" in msg:
            return "Tool"

        return "Unknown"


class OptimizationAnalyzer:
    """Scans telemetry records to detect performance and concurrency improvements."""

    @staticmethod
    def find_bottlenecks(task_durations: Dict[str, float], threshold: float = 3.0) -> List[str]:
        """Identifies tasks that exceeded typical performance durations."""
        bottlenecks = []
        if not task_durations:
            return []

        avg_duration = sum(task_durations.values()) / len(task_durations)
        # Identify nodes taking significantly longer than average or a fixed limit
        for node_id, duration in task_durations.items():
            if duration > threshold or duration > 2.0 * avg_duration:
                bottlenecks.append(node_id)

        return bottlenecks

    @staticmethod
    def analyze_parallelization(record: ExecutionRecord) -> float:
        """Computes parallel execution score ratio.

        Ratio of (max task duration) / (total duration). Higher represents better concurrency.
        """
        if not record.task_durations or record.total_duration <= 0:
            return 1.0
        max_duration = max(record.task_durations.values())
        # If max task duration is close to total duration, steps were executed largely sequentially.
        return max_duration / record.total_duration
