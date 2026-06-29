"""Dynamic Tool Execution Scheduler (Program 11).

Registers and executes delayed or periodic tool calls.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    task_id: str
    tool_name: str
    arguments: Dict[str, Any]
    trigger_time: float  # Epoch timestamp
    interval: Optional[float] = None  # None for one-shot


class ToolScheduler:
    """Schedules background and periodic tool invocation runs."""

    _instance: Optional[ToolScheduler] = None

    def __init__(self) -> None:
        self.queue: List[ScheduledTask] = []

    @classmethod
    def get_instance(cls) -> ToolScheduler:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def schedule(
        self,
        task_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        delay_seconds: float,
        interval: Optional[float] = None,
    ) -> None:
        """Adds a new scheduled task to queue."""
        trigger = time.time() + delay_seconds
        task = ScheduledTask(
            task_id=task_id,
            tool_name=tool_name,
            arguments=arguments,
            trigger_time=trigger,
            interval=interval,
        )
        self.queue.append(task)
        logger.info("Scheduled task %s in queue (runs in %.1fs)", task_id, delay_seconds)

    def trigger_ready_tasks(self, execute_callback: Callable[[str, Dict[str, Any]], Any]) -> List[str]:
        """Triggers and executes scheduled tasks that have reached their run times."""
        now = time.time()
        triggered = []
        remaining = []

        for task in self.queue:
            if now >= task.trigger_time:
                logger.info("Executing scheduled task: %s", task.task_id)
                execute_callback(task.tool_name, task.arguments)
                triggered.append(task.task_id)
                
                # If periodic, reschedule
                if task.interval:
                    task.trigger_time = now + task.interval
                    remaining.append(task)
            else:
                remaining.append(task)

        self.queue = remaining
        return triggered
