"""
Planner Store — JSONL persistence for Goals (with embedded Plans + Tasks).

Goals are the top-level unit of persistence. Plans and Tasks are stored
inline within each Goal record.

Operations:
  - save_goal(goal)         — append new or update existing
  - get_goal(goal_id)       — retrieve by id
  - get_active()            — Goals with an ACTIVE plan
  - get_all()               — full dump
  - update_task(...)        — update a single task's status/result
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List, Optional

from kattappa_runtime.planner.schema import Goal, Plan, Task, TaskStatus, PlanStatus

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "planner_goals.jsonl")


class PlannerStore:
    """Thread-safe JSONL persistence for Goals."""

    def __init__(self, path: str = _DEFAULT_PATH):
        self._path  = path
        self._lock  = Lock()
        self._index: Dict[str, Goal] = {}
        self._load()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_goal(self, goal: Goal) -> None:
        with self._lock:
            is_new = goal.goal_id not in self._index
            self._index[goal.goal_id] = goal
            if is_new:
                self._append_goal(goal)
            else:
                self._rewrite_all()

    def update_task(
        self,
        goal_id:  str,
        plan_id:  str,
        task_id:  str,
        status:   TaskStatus,
        result:   str = "",
        error:    str = "",
    ) -> Optional[Task]:
        """Update a single Task in place and persist."""
        with self._lock:
            goal = self._index.get(goal_id)
            if not goal:
                return None
            for plan in goal.plans:
                if plan.plan_id != plan_id:
                    continue
                for task in plan.tasks:
                    if task.task_id != task_id:
                        continue
                    task.status = status
                    task.result = result
                    task.error  = error
                    now = datetime.now(timezone.utc).isoformat()
                    if status == TaskStatus.IN_PROGRESS and not task.started_at:
                        task.started_at = now
                    if status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.SKIPPED):
                        task.completed_at = now
                    self._rewrite_all()
                    return task
        return None

    def activate_plan(self, goal_id: str, plan_id: str) -> Optional[Plan]:
        """Mark one plan as ACTIVE (others remain DRAFT)."""
        with self._lock:
            goal = self._index.get(goal_id)
            if not goal:
                return None
            for plan in goal.plans:
                if plan.plan_id == plan_id:
                    plan.status = PlanStatus.ACTIVE
                    goal.selected_plan_id = plan_id
                    self._rewrite_all()
                    return plan
        return None

    def complete_plan(self, goal_id: str, plan_id: str) -> Optional[Plan]:
        return self._set_plan_status(goal_id, plan_id, PlanStatus.COMPLETED)

    def fail_plan(self, goal_id: str, plan_id: str) -> Optional[Plan]:
        return self._set_plan_status(goal_id, plan_id, PlanStatus.FAILED)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        with self._lock:
            return self._index.get(goal_id)

    def get_active(self) -> List[Goal]:
        """Goals that have at least one ACTIVE plan."""
        with self._lock:
            return [
                g for g in self._index.values()
                if any(p.status == PlanStatus.ACTIVE for p in g.plans)
            ]

    def get_all(self) -> List[Goal]:
        with self._lock:
            return list(self._index.values())

    def count(self) -> int:
        with self._lock:
            return len(self._index)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _set_plan_status(self, goal_id: str, plan_id: str, status: PlanStatus) -> Optional[Plan]:
        with self._lock:
            goal = self._index.get(goal_id)
            if not goal:
                return None
            for plan in goal.plans:
                if plan.plan_id == plan_id:
                    plan.status = status
                    self._rewrite_all()
                    return plan
        return None

    def _append_goal(self, goal: Goal) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(goal.to_dict(), ensure_ascii=False) + "\n")

    def _rewrite_all(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            for g in self._index.values():
                f.write(json.dumps(g.to_dict(), ensure_ascii=False) + "\n")

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    g = Goal.from_dict(json.loads(line))
                    self._index[g.goal_id] = g
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue
