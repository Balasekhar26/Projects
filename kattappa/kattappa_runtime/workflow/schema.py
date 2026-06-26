"""
Workflow Engine Schema — Step 28
==================================

WorkflowResult
    The final output of a completed (or stopped) workflow run.

WorkflowEvent
    A single event in the workflow execution log.
    Provides an auditable trace of every decision the engine made.

WorkflowStatus
    Lifecycle of a workflow run.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class WorkflowStatus(str, Enum):
    RUNNING   = "running"
    COMPLETED = "completed"  # All tasks done successfully
    FAILED    = "failed"     # Fatal failure — replan attempts exhausted
    STOPPED   = "stopped"    # Halted by safety limit or manual interrupt
    REPLANNED = "replanned"  # Mid-run replan triggered (intermediate state)


class EventType(str, Enum):
    GOAL_SUBMITTED   = "goal_submitted"
    PLAN_ACTIVATED   = "plan_activated"
    TASK_STARTED     = "task_started"
    TASK_COMPLETED   = "task_completed"
    TASK_FAILED      = "task_failed"
    REPLAN_TRIGGERED = "replan_triggered"
    REPLAN_COMPLETED = "replan_completed"
    WORKFLOW_DONE    = "workflow_done"
    SAFETY_HALT      = "safety_halt"


@dataclass
class WorkflowEvent:
    """
    One auditable event in a workflow execution.

    Fields
    ------
    event_id : str
    event_type : EventType
    timestamp : str
    task_title : str         Task name (if event is task-related)
    tool_hint : str          Tool used for this task
    message : str            Human-readable description
    result : str             Short result/error text
    """
    event_id:   str       = field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_type: EventType = EventType.TASK_STARTED
    timestamp:  str       = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    task_title: str = ""
    tool_hint:  str = ""
    message:    str = ""
    result:     str = ""

    def to_log_line(self) -> str:
        ts    = self.timestamp[11:19]  # HH:MM:SS
        icon  = {
            EventType.GOAL_SUBMITTED:   "🎯",
            EventType.PLAN_ACTIVATED:   "📋",
            EventType.TASK_STARTED:     "▶️ ",
            EventType.TASK_COMPLETED:   "✅",
            EventType.TASK_FAILED:      "❌",
            EventType.REPLAN_TRIGGERED: "🔄",
            EventType.REPLAN_COMPLETED: "📋",
            EventType.WORKFLOW_DONE:    "🏁",
            EventType.SAFETY_HALT:      "🛑",
        }.get(self.event_type, "• ")
        msg = self.message
        if self.result:
            msg += f" → {self.result[:60]}"
        return f"  [{ts}] {icon}  {msg}"


@dataclass
class WorkflowResult:
    """
    Final result of a workflow run.

    Fields
    ------
    run_id : str            UUID for this workflow run
    goal_id : str           The goal that was executed
    goal_title : str
    domain : str
    status : WorkflowStatus
    tasks_total : int       Total tasks in the selected plan
    tasks_done : int        Tasks completed successfully
    tasks_failed : int      Tasks that failed
    replan_count : int      How many times replanning was triggered
    events : List[WorkflowEvent]  Full execution trace
    summary : str           Human-readable outcome summary
    started_at : str
    completed_at : str
    """
    run_id:       str              = field(default_factory=lambda: str(uuid.uuid4()))
    goal_id:      str              = ""
    goal_title:   str              = ""
    domain:       str              = "general"
    status:       WorkflowStatus   = WorkflowStatus.RUNNING
    tasks_total:  int              = 0
    tasks_done:   int              = 0
    tasks_failed: int              = 0
    replan_count: int              = 0
    events:       List[WorkflowEvent] = field(default_factory=list)
    summary:      str              = ""
    started_at:   str              = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str              = ""

    def execution_log(self) -> str:
        """Full human-readable execution trace."""
        lines = [
            f"╔══ Workflow: {self.goal_title} ══╗",
            f"  Domain : {self.domain}",
            f"  Status : {self.status.value.upper()}",
            f"  Tasks  : {self.tasks_done}/{self.tasks_total} done, {self.tasks_failed} failed",
            f"  Replans: {self.replan_count}",
            "",
        ]
        for event in self.events:
            lines.append(event.to_log_line())
        lines.append(f"\n  {self.summary}")
        lines.append("╚" + "═" * (len(self.goal_title) + 14) + "╝")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "run_id":       self.run_id,
            "goal_id":      self.goal_id,
            "goal_title":   self.goal_title,
            "domain":       self.domain,
            "status":       self.status.value,
            "tasks_total":  self.tasks_total,
            "tasks_done":   self.tasks_done,
            "tasks_failed": self.tasks_failed,
            "replan_count": self.replan_count,
            "summary":      self.summary,
            "started_at":   self.started_at,
            "completed_at": self.completed_at,
        }
