"""Planner Lifecycle Events for Ledger Logging (Program 12.0).
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional
from backend.core.ledger.models.event import LedgerEvent
from backend.core.ledger.models.enums import EventType
from backend.core.planning.plan_node import PlanNode


def create_planner_ledger_event(
    event_type: EventType,
    goal_id: str,
    payload: Dict[str, Any],
    parent_event_ids: Optional[List[str]] = None,
    session_id: str = "default_session",
    correlation_id: Optional[str] = None,
    actor: str = "planner",
    subsystem: str = "planning_engine",
    confidence: float = 1.0,
    metadata: Optional[Dict[str, Any]] = None,
) -> LedgerEvent:
    """Helper to instantiate structured LedgerEvent objects for planning transitions."""
    evt_id = f"evt-{uuid.uuid4().hex[:8]}"
    return LedgerEvent(
        event_id=evt_id,
        parent_event_ids=parent_event_ids or [],
        goal_id=goal_id,
        session_id=session_id,
        correlation_id=correlation_id or goal_id,
        timestamp_utc=time.time(),
        actor=actor,
        subsystem=subsystem,
        event_type=event_type,
        payload=payload,
        confidence=confidence,
        status="COMMITTED",
        metadata=metadata or {},
    )


class GoalCreatedEvent:
    @staticmethod
    def create(node: PlanNode, session_id: str = "default_session") -> LedgerEvent:
        return create_planner_ledger_event(
            event_type=EventType.GOAL_CREATED,
            goal_id=node.goal_id,
            session_id=session_id,
            payload={
                "goal_id": node.goal_id,
                "title": node.title,
                "priority": node.priority.value,
                "dependencies": node.dependencies,
                "estimated_duration": node.estimated_duration,
            },
        )


class GoalStartedEvent:
    @staticmethod
    def create(goal_id: str, session_id: str = "default_session") -> LedgerEvent:
        return create_planner_ledger_event(
            event_type=EventType.STATE_TRANSITIONED,
            goal_id=goal_id,
            session_id=session_id,
            payload={
                "goal_id": goal_id,
                "transition": "START",
                "status": "ACTIVE",
            },
        )


class GoalCompletedEvent:
    @staticmethod
    def create(goal_id: str, session_id: str = "default_session") -> LedgerEvent:
        return create_planner_ledger_event(
            event_type=EventType.EXECUTION_COMPLETED,
            goal_id=goal_id,
            session_id=session_id,
            payload={
                "goal_id": goal_id,
                "status": "COMPLETED",
            },
        )


class GoalFailedEvent:
    @staticmethod
    def create(goal_id: str, reason: str, session_id: str = "default_session") -> LedgerEvent:
        return create_planner_ledger_event(
            event_type=EventType.STATE_TRANSITIONED,
            goal_id=goal_id,
            session_id=session_id,
            payload={
                "goal_id": goal_id,
                "status": "FAILED",
                "reason": reason,
            },
        )


class GoalCancelledEvent:
    @staticmethod
    def create(goal_id: str, session_id: str = "default_session") -> LedgerEvent:
        return create_planner_ledger_event(
            event_type=EventType.EXECUTION_CANCELLED,
            goal_id=goal_id,
            session_id=session_id,
            payload={
                "goal_id": goal_id,
                "status": "CANCELLED",
            },
        )
