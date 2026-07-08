"""Reflection Engine Data Models (Program 6).

Defines the ExecutionRecord schema, ExecutionReview summary, and LearningCandidate.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExecutionRecord:
    """Canonical, immutable record representing a finished execution session."""
    session_id: str
    plan_id: str
    status: str  # Completed, Failed, Cancelled
    total_duration: float = 0.0
    task_durations: Dict[str, float] = field(default_factory=dict)
    retries: Dict[str, int] = field(default_factory=dict)
    failures: List[Dict[str, Any]] = field(default_factory=list)
    variables_snapshot: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ExecutionReview:
    """Consolidated performance evaluation of an execution session."""
    session_id: str
    success_rate: float = 100.0  # Percentage of successfully completed nodes
    avg_latency: float = 0.0
    total_retries: int = 0
    failure_category: Optional[str] = None  # Classified failure group
    bottleneck_nodes: List[str] = field(default_factory=list)
    parallelization_score: float = 1.0  # Metric of concurrent vs sequential steps
    quality_score: float = 1.0  # Overall aggregated score from 0.0 to 1.0


@dataclass
class LearningCandidate:
    """Proposed advisory updates to memory or planner configurations."""
    candidate_id: str
    target_type: str  # ToolPolicy, ModelRoute, RetryLimit, ConstraintRule
    explanation: str
    proposed_update: Dict[str, Any]
    confidence: float = 1.0
    priority: str = "Medium"  # Low, Medium, High
    status: str = "Advisory"  # Advisory, Approved, Rejected
