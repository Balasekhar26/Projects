"""Mission Temporal Scheduler (Program 24.0).

Enables time-delayed, event-triggered, or periodic background evaluations of mission tasks.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class MissionTemporalScheduler:
    """Dispatches scheduled mission tasks based on relative timeouts or periodic intervals."""

    def __init__(self) -> None:
        self._delayed_tasks: List[Dict[str, Any]] = []
        self._periodic_tasks: List[Dict[str, Any]] = []

    def schedule_delay(
        self,
        mission_id: str,
        delay_seconds: float,
        action_fn: Callable[[], Any]
    ) -> str:
        """Schedules an action to run once after the specified delay."""
        task_id = f"del_{int(time.time())}_{len(self._delayed_tasks)}"
        self._delayed_tasks.append({
            "task_id": task_id,
            "mission_id": mission_id,
            "trigger_time": time.time() + delay_seconds,
            "action": action_fn
        })
        logger.info("MissionTemporalScheduler: Scheduled delayed task %s for mission %s", task_id, mission_id)
        return task_id

    def schedule_periodic(
        self,
        mission_id: str,
        interval_seconds: float,
        action_fn: Callable[[], Any]
    ) -> str:
        """Schedules a periodic action to run repeatedly at the given interval."""
        task_id = f"per_{int(time.time())}_{len(self._periodic_tasks)}"
        self._periodic_tasks.append({
            "task_id": task_id,
            "mission_id": mission_id,
            "interval": interval_seconds,
            "last_run": time.time(),
            "action": action_fn
        })
        logger.info("MissionTemporalScheduler: Scheduled periodic task %s for mission %s", task_id, mission_id)
        return task_id

    def tick(self) -> List[Dict[str, Any]]:
        """Processes scheduled timers, executing ready tasks.

        Returns list of execution log summaries:
            [{"task_id": str, "result": Any}, ...]
        """
        now = time.time()
        executed = []

        # 1. Dispatch delayed tasks
        remaining_delayed = []
        for task in self._delayed_tasks:
            if now >= task["trigger_time"]:
                try:
                    res = task["action"]()
                    executed.append({"task_id": task["task_id"], "result": res})
                except Exception as e:
                    logger.error("MissionTemporalScheduler: Failed delayed task %s — %s", task["task_id"], e)
                    executed.append({"task_id": task["task_id"], "error": str(e)})
            else:
                remaining_delayed.append(task)
        self._delayed_tasks = remaining_delayed

        # 2. Dispatch periodic tasks
        for task in self._periodic_tasks:
            if now >= task["last_run"] + task["interval"]:
                try:
                    res = task["action"]()
                    executed.append({"task_id": task["task_id"], "result": res})
                except Exception as e:
                    logger.error("MissionTemporalScheduler: Failed periodic task %s — %s", task["task_id"], e)
                    executed.append({"task_id": task["task_id"], "error": str(e)})
                finally:
                    task["last_run"] = now

        return executed
