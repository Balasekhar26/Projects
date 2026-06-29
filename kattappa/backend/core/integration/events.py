"""Standardized Event Schemas and Identifiers for Cognitive Integration (Program 8).

Defines tracing IDs standards and integration lifecycle events schemas.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict


def generate_trace_id() -> str:
    """Generates a standardized global distributed tracing ID."""
    return f"tr_{uuid.uuid4().hex[:8]}"


def generate_session_id() -> str:
    """Generates a standardized global execution session ID."""
    return f"sess_{uuid.uuid4().hex[:8]}"


@dataclass
class CognitiveEvent:
    """Canonical event schema spanning cross-module transition boundaries."""
    event_id: str = field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:6]}")
    session_id: str = ""
    execution_id: str = ""
    trace_id: str = ""
    source: str = ""  # Planner, Executor, Reflection, Learning
    event_type: str = ""
    timestamp: float = field(default_factory=time.time)
    payload: Dict[str, Any] = field(default_factory=dict)
