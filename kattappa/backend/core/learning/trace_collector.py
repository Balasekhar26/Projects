"""Trace Collector Event Ingestion Engine (Program 14.0).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from backend.core.learning.experience_store import ExperienceStore
from backend.core.learning.trajectory_builder import Trajectory, TrajectoryBuilder
from backend.core.learning.learning_events import ExperienceCapturedEvent

logger = logging.getLogger(__name__)


class TraceCollector:
    """Subscribes to ledger logs to generate and register structured trajectories."""

    def __init__(self, store: Optional[ExperienceStore] = None) -> None:
        self.store = store or ExperienceStore()

    def collect_events(
        self,
        goal_id: str,
        events_payloads: List[Dict[str, Any]],
        session_id: str = "default_session"
    ) -> Trajectory:
        """Translates a batch of event payloads, saves the trajectory, and logs experience events."""
        logger.info("TraceCollector compiling trajectory for goal '%s'...", goal_id)
        
        trajectory = TrajectoryBuilder.build_trajectory(goal_id, events_payloads)
        self.store.add_trajectory(trajectory)

        # Emit capture confirmation to ledger
        event = ExperienceCapturedEvent.create(
            goal_id=goal_id,
            plan_id=trajectory.plan_id,
            success=trajectory.success,
            score=trajectory.combined_score,
            failures_count=trajectory.failures_count,
            session_id=session_id,
        )
        self._emit_event(event)

        return trajectory

    def _emit_event(self, event: Any) -> None:
        try:
            from backend.core.cos.kernel import KERNEL
            if KERNEL and KERNEL.ledger:
                KERNEL.ledger.append(event)
        except Exception:
            pass
