"""Ledger-Integrated Agent Lifecycle Events (Program 16.0).

Publishes structured events to the system EventBus so every agent state
transition is persisted to the SQLite event ledger and is therefore
deterministically replayable.

Event names follow the EventName registry in event_bus.py conventions.
New agent-specific names are added as string constants here to avoid
modifying event_bus.py directly (open/closed principle).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Agent lifecycle event name constants ──────────────────────────────────────
AGENT_SPAWNED            = "AgentSpawned"
AGENT_TASK_STARTED       = "AgentTaskStarted"
AGENT_TASK_COMPLETED     = "AgentTaskCompleted"
AGENT_TASK_FAILED        = "AgentTaskFailed"
AGENT_TASK_CANCELLED     = "AgentTaskCancelled"
AGENT_BUDGET_EXCEEDED    = "AgentBudgetExceeded"
AGENT_DEADLOCK_DETECTED  = "AgentDeadlockDetected"
AGENT_DUPLICATE_SKIPPED  = "AgentDuplicateSkipped"


def _publish(event_name: str, payload: Dict[str, Any], source: str = "agents") -> None:
    """Best-effort publish to the system EventBus. Swallows errors to stay non-blocking."""
    try:
        from backend.core.event_bus import EVENT_BUS
        EVENT_BUS.publish(event_name, payload=payload, source=source)
    except Exception as exc:
        logger.debug("AgentEvents: could not publish %s — %s", event_name, exc)


# ── Public emit helpers ───────────────────────────────────────────────────────

def emit_spawned(agent_name: str, task_id: str, delegation_depth: int = 0) -> None:
    _publish(AGENT_SPAWNED, {
        "agent_name": agent_name,
        "task_id": task_id,
        "delegation_depth": delegation_depth,
    })


def emit_task_started(agent_name: str, task_id: str, action: str) -> None:
    _publish(AGENT_TASK_STARTED, {
        "agent_name": agent_name,
        "task_id": task_id,
        "action": action,
    })


def emit_task_completed(agent_name: str, task_id: str, output: Any = None) -> None:
    _publish(AGENT_TASK_COMPLETED, {
        "agent_name": agent_name,
        "task_id": task_id,
        "output_summary": str(output)[:200] if output is not None else None,
    })


def emit_task_failed(agent_name: str, task_id: str, error: str) -> None:
    _publish(AGENT_TASK_FAILED, {
        "agent_name": agent_name,
        "task_id": task_id,
        "error": error,
    })


def emit_task_cancelled(agent_name: str, task_id: str, reason: str = "") -> None:
    _publish(AGENT_TASK_CANCELLED, {
        "agent_name": agent_name,
        "task_id": task_id,
        "reason": reason,
    })


def emit_budget_exceeded(agent_name: str, task_id: str, dimension: str, used: float, limit: float) -> None:
    _publish(AGENT_BUDGET_EXCEEDED, {
        "agent_name": agent_name,
        "task_id": task_id,
        "dimension": dimension,
        "used": used,
        "limit": limit,
    })


def emit_deadlock_detected(cycle: list[str]) -> None:
    _publish(AGENT_DEADLOCK_DETECTED, {"cycle": cycle})


def emit_duplicate_skipped(task_id: str, fingerprint: str) -> None:
    _publish(AGENT_DUPLICATE_SKIPPED, {
        "task_id": task_id,
        "fingerprint": fingerprint,
    })
