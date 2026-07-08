"""Evaluation Layer Ledger Events (Program 13.0).
"""
from __future__ import annotations

from typing import Any, Dict
from backend.core.ledger.models.event import LedgerEvent
from backend.core.ledger.models.enums import EventType
from backend.core.planning.planner_events import create_planner_ledger_event


class EvaluationCompletedEvent:
    @staticmethod
    def create(
        planner_version: str,
        combined_score: float,
        total_plans: int,
        session_id: str = "default_session"
    ) -> LedgerEvent:
        return create_planner_ledger_event(
            event_type=EventType.STATE_TRANSITIONED,
            goal_id=f"eval-{planner_version}",
            session_id=session_id,
            payload={
                "planner_version": planner_version,
                "combined_score": combined_score,
                "total_plans": total_plans,
                "transition": "EVALUATION_COMPLETE",
            },
        )


class RegressionDetectedEvent:
    @staticmethod
    def create(
        planner_version: str,
        current_score: float,
        baseline_score: float,
        degradations: list[str],
        session_id: str = "default_session"
    ) -> LedgerEvent:
        return create_planner_ledger_event(
            event_type=EventType.STATE_TRANSITIONED,
            goal_id=f"regression-{planner_version}",
            session_id=session_id,
            payload={
                "planner_version": planner_version,
                "current_score": current_score,
                "baseline_score": baseline_score,
                "degradations": degradations,
                "transition": "REGRESSION_DETECTED",
            },
        )
