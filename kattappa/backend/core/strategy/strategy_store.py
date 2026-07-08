"""Strategy Store: Context-Decision-Outcome Registry (Program 15.0).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StrategyDecision:
    """Records a single routing decision along with its context and outcome."""
    goal_id: str
    planner: str
    model: str
    tool: str
    context: Dict[str, Any]
    success: Optional[bool] = None
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "planner": self.planner,
            "model": self.model,
            "tool": self.tool,
            "context": self.context,
            "success": self.success,
            "score": self.score,
        }


class StrategyStore:
    """Thread-safe registry storing strategy routing decisions and outcomes for offline analysis."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._decisions: List[StrategyDecision] = []

    def record(self, decision: StrategyDecision) -> None:
        """Appends a new strategy decision to the store."""
        with self._lock:
            self._decisions.append(decision)

    def update_outcome(self, goal_id: str, success: bool, score: float) -> None:
        """Backfills the outcome for an existing decision record when execution completes."""
        with self._lock:
            for d in reversed(self._decisions):
                if d.goal_id == goal_id and d.success is None:
                    d.success = success
                    d.score = score
                    break

    def get_all(self) -> List[StrategyDecision]:
        with self._lock:
            return list(self._decisions)

    def get_planner_success_rates(self) -> Dict[str, float]:
        """Aggregates success rates per planner variant across completed decisions."""
        with self._lock:
            counts: Dict[str, int] = {}
            successes: Dict[str, int] = {}
            for d in self._decisions:
                if d.success is None:
                    continue
                counts[d.planner] = counts.get(d.planner, 0) + 1
                if d.success:
                    successes[d.planner] = successes.get(d.planner, 0) + 1
            return {
                planner: round(successes.get(planner, 0) / count, 3)
                for planner, count in counts.items()
            }

    def clear(self) -> None:
        with self._lock:
            self._decisions.clear()
