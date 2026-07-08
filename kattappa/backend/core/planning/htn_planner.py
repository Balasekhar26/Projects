"""Deterministic HTN Decomposition Planner with Partial Order Dependency Matching (Program 12.1).
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Set

from backend.core.planning.planner_types import GoalPriority, GoalStatus
from backend.core.planning.plan_node import PlanNode
from backend.core.planning.goal_graph import GoalGraph
from backend.core.planning.plan import Plan
from backend.core.planning.task_library import TaskLibrary, TaskDefinition
from backend.core.execution.typed_errors import ValidationError

PLANNER_VERSION = "1.1.0"


class HTNPlanner:
    """Manages deterministic Hierarchical Task Network expansion with preconditions & effects matching."""

    def __init__(self, library: Optional[TaskLibrary] = None) -> None:
        self.library = library or TaskLibrary()

    def generate_plan(
        self,
        goal_id: str,
        root_task_name: str,
        initial_state: Optional[List[str]] = None,
        parent_plan_id: Optional[str] = None,
        generation: int = 1,
        created_from_failure_event: Optional[str] = None,
        planner_budget: float = 100.0,
        max_depth: int = 5,
    ) -> Plan:
        """Decomposes a root task into a versioned execution Plan containing a DAG GoalGraph."""
        graph = GoalGraph()
        
        # Keep track of generated primitive tasks in order of expansion
        primitive_steps: List[PlanNode] = []
        
        # Track multidimensional costs
        accumulated_costs: Dict[str, float] = {
            "cpu_seconds": 0.0,
            "api_tokens": 0.0,
            "dollars": 0.0,
            "time": 0.0,
        }

        # Step 1: Recursively decompose compound tasks into primitive steps
        def recurse_decompose(task_name: str, depth: int, parent_node_id: Optional[str] = None) -> None:
            if depth > max_depth:
                raise ValidationError(
                    f"Planning aborted: Maximum recursion depth ({max_depth}) exceeded during HTN expansion."
                )

            task_def = self.library.get_task(task_name)
            if not task_def:
                raise ValidationError(f"Planning aborted: Task definition '{task_name}' not found in TaskLibrary.")

            if task_def.is_primitive:
                # Accumulate multidimensional costs
                for cost_key, val in task_def.cost_vector.items():
                    accumulated_costs[cost_key] = accumulated_costs.get(cost_key, 0.0) + val
                
                # Estimated duration counts as time cost
                accumulated_costs["time"] += task_def.estimated_duration

                # Check budget limits (against scalar planner_budget checking total time or dollars)
                if accumulated_costs["time"] > planner_budget or accumulated_costs["dollars"] > planner_budget:
                    raise ValidationError(
                        f"Planning aborted: Exceeded planner budget limit ({planner_budget}) "
                        f"with current accumulated costs: {accumulated_costs}."
                    )

                # Instantiate new PlanNode
                node = PlanNode(
                    goal_id=f"task-{uuid.uuid4().hex[:6]}",
                    title=task_def.name,
                    parent_goal_id=parent_node_id,
                    status=GoalStatus.PROPOSED,
                    priority=GoalPriority.MEDIUM,
                    estimated_duration=task_def.estimated_duration,
                    duration_variance=task_def.duration_variance,
                    success_probability=task_def.success_probability,
                    resource_cost=task_def.cost_vector.get("dollars", 0.0),
                    preconditions=list(task_def.preconditions),
                    effects=list(task_def.effects),
                    negative_effects=list(task_def.negative_effects),
                    cost_vector=dict(task_def.cost_vector),
                    rule_id=task_def.rule_id,
                    metadata={
                        "planner_version": PLANNER_VERSION,
                        "planning_timestamp": time.time(),
                    }
                )
                primitive_steps.append(node)
            else:
                compound_node_id = f"cmp-{uuid.uuid4().hex[:6]}"
                for subtask in task_def.subtasks:
                    recurse_decompose(subtask, depth + 1, parent_node_id=compound_node_id)

        # Decompose the tree
        recurse_decompose(root_task_name, depth=1)

        # Step 2: Add all primitive nodes to the DAG GoalGraph
        for node in primitive_steps:
            graph.add_node(node)

        # Step 3: Dynamic dependency matching using preconditions and effects (Causal Links)
        # We simulate the state progression forward
        current_state: Set[str] = set(initial_state or [])

        for idx, current_node in enumerate(primitive_steps):
            # Verify preconditions are met
            for pre in current_node.preconditions:
                if pre not in current_state:
                    raise ValidationError(
                        f"Planning aborted: Unmet precondition '{pre}' for task '{current_node.title}'."
                    )

                # Find the most recent prior task that produced this precondition effect
                for j in range(idx - 1, -1, -1):
                    prior_node = primitive_steps[j]
                    if pre in prior_node.effects:
                        graph.add_dependency(current_node.goal_id, prior_node.goal_id)
                        break

            # Propagate effects to the current state
            for effect in current_node.effects:
                current_state.add(effect)
            for neg_effect in current_node.negative_effects:
                current_state.discard(neg_effect)

        # Step 4: Wrap in versioned Plan model
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        return Plan(
            plan_id=plan_id,
            goal_id=goal_id,
            parent_plan_id=parent_plan_id,
            generation=generation,
            created_from_failure_event=created_from_failure_event,
            graph=graph,
            metadata={
                "root_task": root_task_name,
                "planner_version": PLANNER_VERSION,
                "planning_timestamp": time.time(),
                "accumulated_costs": accumulated_costs,
                "final_state": list(current_state),
            }
        )
