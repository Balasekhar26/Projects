"""Goal Representation Framework (Program 5G-1).

Defines structures for Goal modeling and GoalRegistry management,
supporting dependency checks, topological sorting, and metadata constraints.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class Goal:
    """Represents a rich target goal for the planner."""
    goal_id: str
    name: str
    priority: str = "Medium"               # e.g., Critical, High, Medium, Low
    deadline: Optional[float] = None       # Epoch timestamp
    importance: float = 1.0                # Relative weight multiplier
    constraints: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list) # Parent goal IDs
    owner: Optional[str] = None
    status: str = "Pending"                # Pending, InProgress, Completed, Failed
    reward: float = 100.0                  # Utility payoff for success
    failure_cost: float = -50.0            # Utility penalty for failure


class GoalRegistry:
    """Manages structural goal lists, updates, and dependency paths in memory."""

    def __init__(self) -> None:
        self._goals: Dict[str, Goal] = {}

    def register_goal(self, goal: Goal) -> None:
        """Registers a goal in the registry, validating parents and cycles."""
        # 1. Validate dependencies exist (or will exist)
        for dep in goal.dependencies:
            if dep == goal.goal_id:
                raise ValueError(f"Goal '{goal.goal_id}' cannot depend on itself.")

        # 2. Check for cycles
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
        self._goals[goal_id].status = status

    def clear(self) -> None:
        self._goals.clear()

    def get_topological_order(self) -> List[str]:
        """Resolves dependencies and returns Goal IDs topologically sorted.

        Parents (dependencies) must be executed before children.
        """
        visited: Set[str] = set()
        temp: Set[str] = set()
        order: List[str] = []

        def visit(node_id: str):
            if node_id in temp:
                raise ValueError("Goal cycle detected during sorting!")
            if node_id not in visited:
                temp.add(node_id)
                # Visit dependencies first
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
            lines.append(
                f"- **Goal**: `{goal.name}` (`{goal.goal_id}`)\n"
                f"  - Status: `{goal.status}` | Priority: `{goal.priority}`\n"
                f"  - Dependencies: `{deps_str}` | Reward: `{goal.reward}`"
            )
            
        return "\n".join(lines)
