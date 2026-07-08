"""Execution State and Session Context Definitions (Program 5G-6).

Defines execution transitions, session status mappings, and ExecutionContext.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class ExecutionState(str, Enum):
    PENDING = "Pending"
    QUEUED = "Queued"
    RUNNING = "Running"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    FAILED = "Failed"
    RETRYING = "Retrying"
    ROLLING_BACK = "RollingBack"
    CANCELLED = "Cancelled"
    SKIPPED = "Skipped"


VALID_TRANSITIONS: Dict[ExecutionState, Set[ExecutionState]] = {
    ExecutionState.PENDING: {ExecutionState.QUEUED, ExecutionState.CANCELLED},
    ExecutionState.QUEUED: {ExecutionState.RUNNING, ExecutionState.CANCELLED},
    ExecutionState.RUNNING: {
        ExecutionState.COMPLETED,
        ExecutionState.FAILED,
        ExecutionState.PAUSED,
        ExecutionState.CANCELLED,
        ExecutionState.RETRYING,
        ExecutionState.ROLLING_BACK,
    },

    ExecutionState.PAUSED: {ExecutionState.RUNNING, ExecutionState.CANCELLED},
    ExecutionState.RETRYING: {ExecutionState.RUNNING, ExecutionState.FAILED, ExecutionState.CANCELLED},
    ExecutionState.FAILED: {ExecutionState.ROLLING_BACK, ExecutionState.PENDING},
    ExecutionState.ROLLING_BACK: {ExecutionState.FAILED, ExecutionState.PENDING},
    ExecutionState.CANCELLED: set(),
    ExecutionState.COMPLETED: set(),
    ExecutionState.SKIPPED: set(),
}


@dataclass
class ExecutionContext:
    """Carries plan parameters, outputs, cancellation flags, and locks context."""
    variables: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    allocated_resources: Set[str] = field(default_factory=set)
    is_cancelled: bool = False
    telemetry: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionSession:
    """Manages tracking status, progress, and timing of an active plan graph execution."""
    session_id: str
    plan_id: str
    status: ExecutionState = ExecutionState.PENDING
    progress: float = 0.0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    completed_nodes: Set[str] = field(default_factory=set)
    failed_nodes: Set[str] = field(default_factory=set)
    running_nodes: Set[str] = field(default_factory=set)
    retry_counts: Dict[str, int] = field(default_factory=dict)

    def transition_to(self, new_state: ExecutionState) -> None:
        """Transitions the session status, verifying valid path mapping."""
        if new_state == self.status:
            return
        allowed = VALID_TRANSITIONS.get(self.status, set())
        # Permit any terminal transition from running/queued to cancel, etc.
        if new_state not in allowed and new_state != ExecutionState.CANCELLED:
            raise ValueError(f"Invalid transition from state {self.status} to {new_state}")
        self.status = new_state
        if new_state == ExecutionState.RUNNING and self.start_time is None:
            self.start_time = time.time()
        elif new_state in {ExecutionState.COMPLETED, ExecutionState.FAILED, ExecutionState.CANCELLED}:
            self.end_time = time.time()
