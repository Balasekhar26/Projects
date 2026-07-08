"""Execution Plan Model (Program 12.1).

Represents a versioned, disposable execution tree generated to satisfy a Goal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from backend.core.planning.goal_graph import GoalGraph


@dataclass
class Plan:
    """Represents a versioned execution graph derived to fulfill a specific Goal."""
    plan_id: str
    goal_id: str
    parent_plan_id: Optional[str] = None
    generation: int = 1
    created_from_failure_event: Optional[str] = None
    graph: GoalGraph = field(default_factory=GoalGraph)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the Plan structure including the graph topology."""
        return {
            "plan_id": self.plan_id,
            "goal_id": self.goal_id,
            "parent_plan_id": self.parent_plan_id,
            "generation": self.generation,
            "created_from_failure_event": self.created_from_failure_event,
            "graph": self.graph.to_dict(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Plan:
        """Restores a Plan object from dictionary storage."""
        graph_dict = data.get("graph", {})
        graph_obj = GoalGraph.from_dict(graph_dict) if graph_dict else GoalGraph()

        return cls(
            plan_id=data["plan_id"],
            goal_id=data["goal_id"],
            parent_plan_id=data.get("parent_plan_id"),
            generation=data.get("generation", 1),
            created_from_failure_event=data.get("created_from_failure_event"),
            graph=graph_obj,
            metadata=data.get("metadata", {}),
        )
