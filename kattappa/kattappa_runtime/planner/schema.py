"""
Planner Evolution Schema — Step 27
====================================

The Planner turns goals into executable task trees.

Goal
  └── Plan
        ├── Task 1
        │     ├── estimated_cost
        │     ├── risk_level
        │     └── dependencies[]
        ├── Task 2
        └── ...

Key design decisions:
  - A Goal is what Kattappa wants to achieve
  - A Plan is ONE proposed decomposition of that goal
  - Multiple Plans can exist for a Goal (alternative strategies)
  - Each Task has a cost estimate, risk level, status, and result
  - Plans are scored by total_cost × max_risk for triage

Plan selection logic: lowest (cost × risk) wins unless the user
has a preference.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class TaskStatus(str, Enum):
    PENDING    = "pending"
    IN_PROGRESS = "in_progress"
    DONE       = "done"
    FAILED     = "failed"
    SKIPPED    = "skipped"


class RiskLevel(str, Enum):
    LOW      = "low"       # Routine, well-understood action
    MEDIUM   = "medium"    # Some uncertainty; reversible
    HIGH     = "high"      # Significant uncertainty; hard to reverse
    CRITICAL = "critical"  # Could cause serious side effects


class PlanStatus(str, Enum):
    DRAFT      = "draft"       # Not yet approved for execution
    ACTIVE     = "active"      # Currently executing
    COMPLETED  = "completed"   # All tasks done
    FAILED     = "failed"      # One or more tasks failed critically
    ABANDONED  = "abandoned"   # User or engine discarded this plan


@dataclass
class Task:
    """
    One atomic step in a Plan.

    Fields
    ------
    task_id : str
        UUID4 identifier.
    title : str
        Short imperative description. e.g. "Research impedance matching"
    description : str
        Detailed action description.
    tool_hint : str
        Suggested tool or engine to use. e.g. "research_engine", "code_runner"
    estimated_cost : float
        Abstract cost unit [0.0 – 10.0]. Higher = more expensive/time-consuming.
    risk_level : RiskLevel
        How risky is this step?
    dependencies : List[str]
        task_ids that must be DONE before this task can start.
    status : TaskStatus
        Current execution state.
    result : str
        Output or result after execution (filled by the Workflow Engine).
    error : str
        Error message if task failed.
    started_at : str
        ISO-8601 UTC timestamp when execution began.
    completed_at : str
        ISO-8601 UTC timestamp when execution finished.
    """
    task_id:        str        = field(default_factory=lambda: str(uuid.uuid4()))
    title:          str        = ""
    description:    str        = ""
    tool_hint:      str        = ""
    estimated_cost: float      = 1.0
    risk_level:     RiskLevel  = RiskLevel.LOW
    dependencies:   List[str]  = field(default_factory=list)
    status:         TaskStatus = TaskStatus.PENDING
    result:         str        = ""
    error:          str        = ""
    started_at:     str        = ""
    completed_at:   str        = ""

    @property
    def is_ready(self) -> bool:
        """A task is ready to execute when all dependencies are DONE."""
        # Note: dependency completion is checked by the Plan, not here,
        # since we need access to the full task map.
        return self.status == TaskStatus.PENDING

    @property
    def risk_score(self) -> float:
        return {"low": 1.0, "medium": 2.0, "high": 3.5, "critical": 5.0}[self.risk_level.value]

    def to_dict(self) -> dict:
        return {
            "task_id":        self.task_id,
            "title":          self.title,
            "description":    self.description,
            "tool_hint":      self.tool_hint,
            "estimated_cost": self.estimated_cost,
            "risk_level":     self.risk_level.value,
            "dependencies":   self.dependencies,
            "status":         self.status.value,
            "result":         self.result,
            "error":          self.error,
            "started_at":     self.started_at,
            "completed_at":   self.completed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        d = dict(d)
        d["risk_level"] = RiskLevel(d.get("risk_level", "low"))
        d["status"]     = TaskStatus(d.get("status", "pending"))
        return cls(**d)


@dataclass
class Plan:
    """
    One proposed decomposition strategy for a Goal.

    Fields
    ------
    plan_id : str
        UUID4 identifier.
    goal_id : str
        The Goal this plan belongs to.
    title : str
        Short name for this plan variant. e.g. "Research-first approach"
    tasks : List[Task]
        Ordered list of tasks (may have dependency links for parallelism).
    status : PlanStatus
        Lifecycle state.
    total_cost : float
        Sum of estimated_cost across all tasks.
    max_risk : RiskLevel
        Highest risk level among tasks.
    plan_score : float
        total_cost × max_risk_score. Lower is better.
    created_at : str
        ISO-8601 UTC creation timestamp.
    notes : str
        Optional rationale for this decomposition.
    """
    plan_id:    str        = field(default_factory=lambda: str(uuid.uuid4()))
    goal_id:    str        = ""
    title:      str        = ""
    tasks:      List[Task] = field(default_factory=list)
    status:     PlanStatus = PlanStatus.DRAFT
    created_at: str        = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    notes:      str        = ""

    @property
    def total_cost(self) -> float:
        return sum(t.estimated_cost for t in self.tasks)

    @property
    def max_risk(self) -> RiskLevel:
        if not self.tasks:
            return RiskLevel.LOW
        scores = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        worst  = max(self.tasks, key=lambda t: scores[t.risk_level.value])
        return worst.risk_level

    @property
    def plan_score(self) -> float:
        """Lower = better plan (lower cost and risk)."""
        risk_weight = {"low": 1.0, "medium": 2.0, "high": 3.5, "critical": 5.0}
        return round(self.total_cost * risk_weight[self.max_risk.value], 3)

    @property
    def pending_tasks(self) -> List[Task]:
        return [t for t in self.tasks if t.status == TaskStatus.PENDING]

    @property
    def done_task_ids(self) -> set:
        return {t.task_id for t in self.tasks if t.status == TaskStatus.DONE}

    def ready_tasks(self) -> List[Task]:
        """Return tasks whose dependencies are all DONE."""
        done = self.done_task_ids
        return [
            t for t in self.tasks
            if t.status == TaskStatus.PENDING
            and all(dep in done for dep in t.dependencies)
        ]

    def is_complete(self) -> bool:
        return all(t.status in (TaskStatus.DONE, TaskStatus.SKIPPED) for t in self.tasks)

    def has_critical_failure(self) -> bool:
        return any(
            t.status == TaskStatus.FAILED and t.risk_level == RiskLevel.CRITICAL
            for t in self.tasks
        )

    def progress_pct(self) -> float:
        if not self.tasks:
            return 0.0
        done = sum(1 for t in self.tasks
                   if t.status in (TaskStatus.DONE, TaskStatus.SKIPPED, TaskStatus.FAILED))
        return round(done / len(self.tasks) * 100, 1)

    def to_dict(self) -> dict:
        return {
            "plan_id":    self.plan_id,
            "goal_id":    self.goal_id,
            "title":      self.title,
            "tasks":      [t.to_dict() for t in self.tasks],
            "status":     self.status.value,
            "total_cost": self.total_cost,
            "max_risk":   self.max_risk.value,
            "plan_score": self.plan_score,
            "created_at": self.created_at,
            "notes":      self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Plan":
        d = dict(d)
        tasks_raw = d.pop("tasks", [])
        # Remove computed properties
        for k in ("total_cost", "max_risk", "plan_score"):
            d.pop(k, None)
        d["status"] = PlanStatus(d.get("status", "draft"))
        plan = cls(**d)
        plan.tasks = [Task.from_dict(t) for t in tasks_raw]
        return plan


@dataclass
class Goal:
    """
    A high-level objective submitted to the Planner.

    One Goal can have multiple Plans (alternative strategies).
    The Planner selects the best Plan for execution.

    Fields
    ------
    goal_id : str
        UUID4 identifier.
    title : str
        Short imperative description. e.g. "Build an RF simulator"
    description : str
        Full context and success criteria.
    domain : str
        Primary skill domain involved.
    plans : List[Plan]
        All generated plan alternatives.
    selected_plan_id : str
        The plan chosen for execution.
    created_at : str
        ISO-8601 UTC creation timestamp.
    notes : str
        Extra context.
    """
    goal_id:          str        = field(default_factory=lambda: str(uuid.uuid4()))
    title:            str        = ""
    description:      str        = ""
    domain:           str        = "general"
    plans:            List[Plan] = field(default_factory=list)
    selected_plan_id: str        = ""
    created_at:       str        = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    notes:            str        = ""

    @property
    def selected_plan(self) -> Optional[Plan]:
        for p in self.plans:
            if p.plan_id == self.selected_plan_id:
                return p
        return self.plans[0] if self.plans else None

    def best_plan(self) -> Optional[Plan]:
        """Return the plan with the lowest plan_score (lowest cost × risk)."""
        if not self.plans:
            return None
        return min(self.plans, key=lambda p: p.plan_score)

    def to_dict(self) -> dict:
        return {
            "goal_id":          self.goal_id,
            "title":            self.title,
            "description":      self.description,
            "domain":           self.domain,
            "plans":            [p.to_dict() for p in self.plans],
            "selected_plan_id": self.selected_plan_id,
            "created_at":       self.created_at,
            "notes":            self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Goal":
        d = dict(d)
        plans_raw = d.pop("plans", [])
        goal = cls(**d)
        goal.plans = [Plan.from_dict(p) for p in plans_raw]
        return goal
