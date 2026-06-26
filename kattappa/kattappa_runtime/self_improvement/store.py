"""
Goal Store — JSONL persistence for ImprovementGoals.

Supports:
  - Append new goals
  - In-place status/effectiveness updates (full rewrite)
  - Query by domain, status, priority
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List, Optional

from kattappa_runtime.self_improvement.schema import (
    ImprovementGoal, GoalStatus, ImprovementPriority
)

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "improvement_goals.jsonl")


class GoalStore:
    """Thread-safe JSONL persistence for ImprovementGoals."""

    def __init__(self, path: str = _DEFAULT_PATH):
        self._path  = path
        self._lock  = Lock()
        self._index: Dict[str, ImprovementGoal] = {}
        self._load()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, goal: ImprovementGoal) -> None:
        with self._lock:
            is_new = goal.goal_id not in self._index
            self._index[goal.goal_id] = goal
            if is_new:
                self._append(goal)
            else:
                self._rewrite_all()

    def mark_in_progress(self, goal_id: str) -> Optional[ImprovementGoal]:
        return self._set_status(goal_id, GoalStatus.IN_PROGRESS)

    def mark_completed(self, goal_id: str, effectiveness: float = -1.0) -> Optional[ImprovementGoal]:
        with self._lock:
            goal = self._index.get(goal_id)
            if not goal:
                return None
            goal.status       = GoalStatus.COMPLETED
            goal.completed_at = datetime.now(timezone.utc).isoformat()
            goal.effectiveness = max(-1.0, min(1.0, effectiveness))
            self._rewrite_all()
            return goal

    def mark_stale(self, goal_id: str) -> Optional[ImprovementGoal]:
        return self._set_status(goal_id, GoalStatus.STALE)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_by_domain(self, domain: str) -> List[ImprovementGoal]:
        with self._lock:
            return [g for g in self._index.values() if g.domain == domain]

    def get_by_status(self, status: GoalStatus) -> List[ImprovementGoal]:
        with self._lock:
            return [g for g in self._index.values() if g.status == status]

    def get_open(self) -> List[ImprovementGoal]:
        return self.get_by_status(GoalStatus.OPEN)

    def get_priority_queue(self) -> List[ImprovementGoal]:
        """Return all open/in-progress goals sorted by priority (critical first)."""
        _rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        with self._lock:
            active = [
                g for g in self._index.values()
                if g.status in (GoalStatus.OPEN, GoalStatus.IN_PROGRESS)
            ]
        return sorted(active, key=lambda g: _rank[g.priority.value])

    def get_all(self) -> List[ImprovementGoal]:
        with self._lock:
            return list(self._index.values())

    def count(self) -> int:
        with self._lock:
            return len(self._index)

    def exists_for_domain(self, domain: str) -> bool:
        """True if an OPEN or IN_PROGRESS goal already exists for domain."""
        with self._lock:
            return any(
                g.domain == domain
                and g.status in (GoalStatus.OPEN, GoalStatus.IN_PROGRESS)
                for g in self._index.values()
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _set_status(self, goal_id: str, status: GoalStatus) -> Optional[ImprovementGoal]:
        with self._lock:
            goal = self._index.get(goal_id)
            if not goal:
                return None
            goal.status = status
            self._rewrite_all()
            return goal

    def _append(self, goal: ImprovementGoal) -> None:
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
                    g = ImprovementGoal.from_dict(json.loads(line))
                    self._index[g.goal_id] = g
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue
