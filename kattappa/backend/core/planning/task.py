"""HTN Planner Data Models (Program 5G-2).

Defines Task, Operator, Method, Plan, and PlannerState models.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Task:
    """Represents a compound or primitive task in the HTN network."""
    task_id: str
    name: str
    is_primitive: bool = False
    # Estimated execution cost metrics
    estimated_cost: float = 1.0
    estimated_time: float = 1.0
    # Simple preconditions/effects represented as dicts or functions
    preconditions: Dict[str, Any] = field(default_factory=dict)
    effects: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Operator:
    """Represents a primitive, executable tool/action step."""
    operator_id: str
    name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    preconditions: Dict[str, Any] = field(default_factory=dict)
    effects: Dict[str, Any] = field(default_factory=dict)
    estimated_cost: float = 1.0
    estimated_time: float = 1.0


@dataclass
class Method:
    """Represents a decomposition strategy mapping a compound task to subtasks."""
    method_id: str
    task_name: str                        # Target compound task name
    subtasks: List[str] = field(default_factory=list) # List of child task names/IDs
    preconditions: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    """Represents the compiled sequence of primitive operations."""
    plan_id: str
    goal_id: str
    steps: List[Operator] = field(default_factory=list)
    expected_cost: float = 0.0
    expected_duration: float = 0.0
    expected_reward: float = 0.0
    expected_risk: float = 0.0
    confidence: float = 1.0
    status: str = "Validated"


@dataclass
class PlannerState:
    """Immutable copy-on-write snapshot tracking HTN solver branches."""
    current_goal: str
    variables: Dict[str, Any] = field(default_factory=dict)
    completed_tasks: Set[str] = field(default_factory=set)
    failed_tasks: Set[str] = field(default_factory=set)
    visited_nodes: List[str] = field(default_factory=list)

    def clone_with_update(
        self,
        updates: Optional[Dict[str, Any]] = None,
        visited: Optional[str] = None,
        complete_task: Optional[str] = None,
    ) -> PlannerState:
        new_vars = dict(self.variables)
        if updates:
            new_vars.update(updates)
        new_visited = list(self.visited_nodes)
        if visited:
            new_visited.append(visited)
        new_completed = set(self.completed_tasks)
        if complete_task:
            new_completed.add(complete_task)

        return PlannerState(
            current_goal=self.current_goal,
            variables=new_vars,
            completed_tasks=new_completed,
            failed_tasks=set(self.failed_tasks),
            visited_nodes=new_visited,
        )
