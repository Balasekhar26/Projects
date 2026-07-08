"""Experience Captured Ledger Events (Program 14.0).
"""
from __future__ import annotations

from typing import Any, Dict
from backend.core.ledger.models.event import LedgerEvent
from backend.core.ledger.models.enums import EventType
from backend.core.planning.planner_events import create_planner_ledger_event


class ExperienceCapturedEvent:
    @staticmethod
    def create(
        goal_id: str,
        plan_id: str,
        success: bool,
        score: float,
        failures_count: int,
        session_id: str = "default_session"
    ) -> LedgerEvent:
        return create_planner_ledger_event(
            event_type=EventType.STATE_TRANSITIONED,
            goal_id=goal_id,
            session_id=session_id,
            payload={
                "goal_id": goal_id,
                "plan_id": plan_id,
                "success": success,
                "score": score,
                "failures_count": failures_count,
                "transition": "EXPERIENCE_CAPTURED",
            },
        )
