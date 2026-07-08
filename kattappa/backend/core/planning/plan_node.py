"""Planning Node representation (Program 12.0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.core.planning.planner_types import GoalPriority, GoalStatus


@dataclass
class PlanNode:
    """Canonical planning model describing dependencies, status, state transitions, and costs."""
    goal_id: str
    title: str
    description: Optional[str] = None
    parent_goal_id: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    status: GoalStatus = GoalStatus.PROPOSED
    priority: GoalPriority = GoalPriority.MEDIUM
    deadline: Optional[float] = None
    budget: float = 0.0
    risk_score: float = 0.0
    utility_score: float = 0.0
    estimated_duration: float = 0.0  # Duration for CPM/longest-path calculations
    duration_variance: float = 0.0
    success_probability: float = 1.0
    resource_cost: float = 0.0
    confidence: float = 1.0
    preconditions: List[str] = field(default_factory=list)
    effects: List[str] = field(default_factory=list)
    negative_effects: List[str] = field(default_factory=list)
    cost_vector: Dict[str, float] = field(default_factory=dict)
    rule_id: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes node attributes for database or ledger logging."""
        return {
            "goal_id": self.goal_id,
            "title": self.title,
            "description": self.description,
            "parent_goal_id": self.parent_goal_id,
            "dependencies": self.dependencies,
            "status": self.status.value if isinstance(self.status, GoalStatus) else self.status,
            "priority": self.priority.value if isinstance(self.priority, GoalPriority) else self.priority,
            "deadline": self.deadline,
            "budget": self.budget,
            "risk_score": self.risk_score,
            "utility_score": self.utility_score,
            "estimated_duration": self.estimated_duration,
            "duration_variance": self.duration_variance,
            "success_probability": self.success_probability,
            "resource_cost": self.resource_cost,
            "confidence": self.confidence,
            "preconditions": self.preconditions,
            "effects": self.effects,
            "negative_effects": self.negative_effects,
            "cost_vector": self.cost_vector,
            "rule_id": self.rule_id,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PlanNode:
        """Restores a node from a dictionary representation."""
        status_val = data.get("status", GoalStatus.PROPOSED)
        if isinstance(status_val, str):
            status_val = GoalStatus(status_val)
        
        priority_val = data.get("priority", GoalPriority.MEDIUM)
        if isinstance(priority_val, str):
            priority_val = GoalPriority(priority_val)

        return cls(
            goal_id=data["goal_id"],
            title=data["title"],
            description=data.get("description"),
            parent_goal_id=data.get("parent_goal_id"),
            dependencies=data.get("dependencies", []),
            status=status_val,
            priority=priority_val,
            deadline=data.get("deadline"),
            budget=data.get("budget", 0.0),
            risk_score=data.get("risk_score", 0.0),
            utility_score=data.get("utility_score", 0.0),
            estimated_duration=data.get("estimated_duration", 0.0),
            duration_variance=data.get("duration_variance", 0.0),
            success_probability=data.get("success_probability", 1.0),
            resource_cost=data.get("resource_cost", 0.0),
            confidence=data.get("confidence", 1.0),
            preconditions=data.get("preconditions", []),
            effects=data.get("effects", []),
            negative_effects=data.get("negative_effects", []),
            cost_vector=data.get("cost_vector", {}),
            rule_id=data.get("rule_id"),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 2),
            metadata=data.get("metadata", {}),
        )
