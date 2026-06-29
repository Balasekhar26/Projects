"""Execution Context Parameter Object (Program 11.8).

Enables clean trace context propagation across tool invocations.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from backend.core.execution.cancellation import CancellationToken


@dataclass
class ExecutionContext:
    """Carries trace credentials, cancellations tokens, and timeout deadlines."""
    user_id: str = "anonymous"
    session_id: str = "default_session"
    workflow_id: str = "default_workflow"
    trace_id: str = field(default_factory=lambda: f"tr_{uuid.uuid4().hex[:8]}")
    cancellation_token: Optional[CancellationToken] = None
    deadline: Optional[float] = None  # Epoch timestamp
    metadata: Dict[str, Any] = field(default_factory=dict)
