"""Canonical models shared by action planners and executors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4


def _utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class Action:
    """Describe one immutable unit of work selected by an executor name."""

    executor: str
    operation: str
    parameters: Mapping[str, Any]
    priority: int = 0
    requires_confirmation: bool = False
    action_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        """Validate and defensively copy caller-owned action data."""

        executor = self.executor.strip().casefold()
        operation = self.operation.strip().casefold()
        if not executor:
            raise ValueError("executor must not be empty")
        if not operation:
            raise ValueError("operation must not be empty")
        if not self.action_id.strip():
            raise ValueError("action_id must not be empty")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be an integer")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")

        object.__setattr__(self, "executor", executor)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Canonical measured outcome returned by every action executor."""

    success: bool
    verified: bool
    executed: bool
    executor: str
    latency_ms: float
    retry_count: int
    error_code: str | None
    error_message: str | None
    action_id: str | None = None
    timestamp: datetime = field(default_factory=_utc_now)
    cpu_percent: float | None = None
    memory_mb: float | None = None
    confidence: float | None = None
    recovery_attempted: bool = False
    verification_method: str | None = None

    def __post_init__(self) -> None:
        """Reject internally inconsistent executor outcomes."""

        if self.success and (not self.executed or not self.verified):
            raise ValueError("successful results must be executed and verified")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must not be negative")
        if self.retry_count < 0:
            raise ValueError("retry_count must not be negative")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
