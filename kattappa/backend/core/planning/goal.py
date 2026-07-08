"""Goal Representation Framework (Program 12.1).

Defines stable user objectives independent of temporary, disposable execution Plans.
Supports GoalRegistry management with dependency checks, topological sorting, and metadata constraints.
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from backend.core.planning.planner_types import GoalPriority, GoalStatus

logger = logging.getLogger(__name__)


@dataclass
class Goal:
    """Represents a stable user intent or objective."""
    goal_id: str
    name: str
    description: Optional[str] = None
    priority: GoalPriority = GoalPriority.MEDIUM
    status: GoalStatus = GoalStatus.PROPOSED
    deadline: Optional[float] = None
    budget_limit: float = 0.0
    reward: float = 100.0          # Utility payoff for success
    failure_cost: float = -50.0    # Utility penalty for failure
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Restored fields for compatibility with planning API and test suites
    constraints: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    owner: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes goal attributes for storage."""
        return {
            "goal_id": self.goal_id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority.value if isinstance(self.priority, GoalPriority) else self.priority,
            "status": self.status.value if isinstance(self.status, GoalStatus) else self.status,
            "deadline": self.deadline,
            "budget_limit": self.budget_limit,
            "reward": self.reward,
            "failure_cost": self.failure_cost,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "constraints": self.constraints,
            "dependencies": self.dependencies,
            "owner": self.owner,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Goal:
        """Restores a Goal object from dictionary storage."""
        status_val = data.get("status", GoalStatus.PROPOSED)
        if isinstance(status_val, str):
            status_val = GoalStatus(status_val)

        priority_val = data.get("priority", GoalPriority.MEDIUM)
        if isinstance(priority_val, str):
            priority_val = GoalPriority(priority_val)

        return cls(
            goal_id=data["goal_id"],
            name=data["name"],
            description=data.get("description"),
            priority=priority_val,
            status=status_val,
            deadline=data.get("deadline"),
            budget_limit=data.get("budget_limit", 0.0),
            reward=data.get("reward", 100.0),
            failure_cost=data.get("failure_cost", -50.0),
            created_at=data.get("created_at", time.time()),
            metadata=data.get("metadata", {}),
            constraints=data.get("constraints", []),
            dependencies=data.get("dependencies", []),
            owner=data.get("owner"),
        )


class GoalRegistry:
    """Manages structural goal lists, updates, and dependency paths in memory."""

    def __init__(self) -> None:
        self._goals: Dict[str, Goal] = {}

    def register_goal(self, goal: Goal) -> None:
        """Registers a goal in the registry, validating parents and cycles."""
        for dep in goal.dependencies:
            if dep == goal.goal_id:
                raise ValueError(f"Goal '{goal.goal_id}' cannot depend on itself.")

        if self._would_cause_cycle(goal.goal_id, goal.dependencies):
            raise ValueError(f"Registering goal '{goal.goal_id}' would introduce a dependency cycle.")

        self._goals[goal.goal_id] = goal

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        return self._goals.get(goal_id)

    def list_goals(self) -> List[Goal]:
        return list(self._goals.values())

    def update_goal_status(self, goal_id: str, status: str) -> None:
        if goal_id not in self._goals:
            raise KeyError(f"Goal '{goal_id}' not found.")
        try:
            self._goals[goal_id].status = GoalStatus(status)
        except Exception:
            self._goals[goal_id].status = status

    def clear(self) -> None:
        self._goals.clear()

    def get_topological_order(self) -> List[str]:
        """Resolves dependencies and returns Goal IDs topologically sorted."""
        visited: Set[str] = set()
        temp: Set[str] = set()
        order: List[str] = []

        def visit(node_id: str):
            if node_id in temp:
                raise ValueError("Goal cycle detected during sorting!")
            if node_id not in visited:
                temp.add(node_id)
                goal = self._goals.get(node_id)
                if goal:
                    for dep in goal.dependencies:
                        if dep in self._goals:
                            visit(dep)
                temp.remove(node_id)
                visited.add(node_id)
                order.append(node_id)

        for g_id in self._goals:
            if g_id not in visited:
                visit(g_id)

        return order

    def _would_cause_cycle(self, name: str, dependencies: List[str]) -> bool:
        """Helper to verify if adding dependencies to name creates a cycle."""
        visited: Set[str] = set()

        def dfs(curr: str) -> bool:
            if curr == name:
                return True
            if curr in visited:
                return False
            visited.add(curr)
            goal = self._goals.get(curr)
            if goal:
                for dep in goal.dependencies:
                    if dfs(dep):
                        return True
            return False

        for dep in dependencies:
            if dfs(dep):
                return True
        return False

    def generate_dependency_trace(self) -> str:
        """Generates a human-readable markdown trace of the goal dependencies."""
        lines = ["### Goal Dependency Diagram Trace"]
        order = self.get_topological_order()
        
        for g_id in order:
            goal = self._goals[g_id]
            deps_str = ", ".join(goal.dependencies) if goal.dependencies else "None"
            status_val = goal.status.value if hasattr(goal.status, "value") else str(goal.status)
            priority_val = goal.priority.value if hasattr(goal.priority, "value") else str(goal.priority)
            lines.append(
                f"- **Goal**: `{goal.name}` (`{goal.goal_id}`)\n"
                f"  - Status: `{status_val}` | Priority: `{priority_val}`\n"
                f"  - Dependencies: `{deps_str}` | Reward: `{goal.reward}`"
            )
            
        return "\n".join(lines)
