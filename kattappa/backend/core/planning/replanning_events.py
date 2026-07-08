"""Replanning and Recovery Ledger Events (Program 12.4).
"""
from __future__ import annotations

from typing import Any, Dict
from backend.core.ledger.models.event import LedgerEvent
from backend.core.ledger.models.enums import EventType
from backend.core.planning.planner_events import create_planner_ledger_event


class PlanRepairStartedEvent:
    @staticmethod
    def create(plan_id: str, failed_node_id: str, strategy: str, session_id: str = "default_session") -> LedgerEvent:
        return create_planner_ledger_event(
            event_type=EventType.STATE_TRANSITIONED,
            goal_id=plan_id,
            session_id=session_id,
            payload={
                "plan_id": plan_id,
                "failed_node_id": failed_node_id,
                "strategy": strategy,
                "transition": "REPAIR_START",
            },
        )


class PlanRepairSucceededEvent:
    @staticmethod
    def create(plan_id: str, repaired_plan_id: str, generation: int, session_id: str = "default_session") -> LedgerEvent:
        return create_planner_ledger_event(
            event_type=EventType.PLAN_GENERATED,
            goal_id=plan_id,
            session_id=session_id,
            payload={
                "parent_plan_id": plan_id,
                "repaired_plan_id": repaired_plan_id,
                "generation": generation,
                "transition": "REPAIR_SUCCESS",
            },
        )


class PlanRepairFailedEvent:
    @staticmethod
    def create(plan_id: str, failed_node_id: str, reason: str, session_id: str = "default_session") -> LedgerEvent:
        return create_planner_ledger_event(
            event_type=EventType.STATE_TRANSITIONED,
            goal_id=plan_id,
            session_id=session_id,
            payload={
                "plan_id": plan_id,
                "failed_node_id": failed_node_id,
                "reason": reason,
                "transition": "REPAIR_FAILURE",
            },
        )


class PlanAbortedEvent:
    @staticmethod
    def create(plan_id: str, reason: str, session_id: str = "default_session") -> LedgerEvent:
        return create_planner_ledger_event(
            event_type=EventType.EXECUTION_CANCELLED,
            goal_id=plan_id,
            session_id=session_id,
            payload={
                "plan_id": plan_id,
                "reason": reason,
                "status": "ABORTED",
            },
        )
