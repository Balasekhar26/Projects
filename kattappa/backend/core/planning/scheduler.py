"""Temporal & Resource Scheduler (Program 5G-5).

Implements Critical Path Method (CPM), forward/backward passes, slack time,
and resource-constrained parallel scheduling.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from backend.core.planning.plan_graph import DependencyGraph

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    """Contains timing, slack metrics, and resource allocations for a node."""
    node_id: str
    earliest_start: float = 0.0
    earliest_finish: float = 0.0
    latest_start: float = 0.0
    latest_finish: float = 0.0
    slack: float = 0.0
    allocated_resources: List[str] = field(default_factory=list)
    is_critical: bool = False


class CriticalPathAnalyzer:
    """Computes earliest/latest start times and slack using Critical Path Method (CPM)."""

    @staticmethod
    def analyze(graph: DependencyGraph) -> Dict[str, ScheduledTask]:
        """Calculates CPM metrics for all nodes in the plan graph."""
        try:
            order = graph.get_topological_sort()
        except ValueError:
            # Handle cycle cases gracefully
            return {}

        scheduled_tasks: Dict[str, ScheduledTask] = {
            node_id: ScheduledTask(node_id=node_id) for node_id in graph.nodes
        }

        # 1. Forward Pass: compute earliest start (ES) and earliest finish (EF)
        for node_id in order:
            node = graph.nodes[node_id]
            task = scheduled_tasks[node_id]
            duration = getattr(node.operator, "estimated_time", 1.0)

            parents = graph.in_degree_list.get(node_id, [])
            if not parents:
                task.earliest_start = 0.0
            else:
                task.earliest_start = max(scheduled_tasks[parent_id].earliest_finish for parent_id in parents)

            task.earliest_finish = task.earliest_start + duration

        # Find project completion time
        if not scheduled_tasks:
            return {}
        max_finish = max(task.earliest_finish for task in scheduled_tasks.values())

        # 2. Backward Pass: compute latest finish (LF) and latest start (LS)
        for node_id in reversed(order):
            node = graph.nodes[node_id]
            task = scheduled_tasks[node_id]
            duration = getattr(node.operator, "estimated_time", 1.0)

            children = graph.adjacency_list.get(node_id, [])
            # Read individual deadline constraint if present
            deadline = node.operator.parameters.get("deadline", max_finish)

            if not children:
                task.latest_finish = min(max_finish, deadline)
            else:
                task.latest_finish = min(scheduled_tasks[child_id].latest_start for child_id in children)

            task.latest_start = task.latest_finish - duration
            task.slack = max(0.0, task.latest_start - task.earliest_start)
            # Critical path nodes have approximately 0 slack
            task.is_critical = task.slack < 0.001

        return scheduled_tasks


class Scheduler:
    """Schedules tasks by balancing critical path metrics with resource limits."""

    @staticmethod
    def schedule_with_resources(
        graph: DependencyGraph,
        resource_limits: Dict[str, int],
    ) -> Dict[str, ScheduledTask]:
        """Calculates a resource-constrained timeline for tasks in the plan graph.

        Shifts task execution starts forward to resolve resource capacity overlaps.
        """
        # Step 1: Perform baseline CPM analysis
        scheduled = CriticalPathAnalyzer.analyze(graph)
        if not scheduled:
            return {}

        try:
            layers = graph.get_parallel_layers()
        except ValueError:
            return scheduled

        # Keep track of active resource release events: resource_name -> List[(release_time, node_id)]
        resource_releases: Dict[str, List[tuple[float, str]]] = {}
        for res in resource_limits:
            resource_releases[res] = []

        # We will schedule layer by layer
        for layer in layers:
            # Sort layer nodes by priority or critical path (critical nodes first!)
            layer_sorted = sorted(layer, key=lambda nid: (not scheduled[nid].is_critical, nid))

            for node_id in layer_sorted:
                node = graph.nodes[node_id]
                task = scheduled[node_id]
                duration = getattr(node.operator, "estimated_time", 1.0)
                req_resources = node.operator.parameters.get("required_resources", [])

                # Start time is initially based on dependency readiness (earliest_start)
                start_time = task.earliest_start

                # Shift start_time forward if resource capacity is exceeded at start_time
                for res in req_resources:
                    limit = resource_limits.get(res, 1)
                    # Filter active reservations at our proposed start_time
                    releases = resource_releases.get(res, [])
                    
                    # Loop until we find a time slot where current concurrent usage < limit
                    while True:
                        active_users = [
                            (rel_time, nid) for rel_time, nid in releases
                            if rel_time > start_time
                        ]
                        if len(active_users) < limit:
                            break
                        # Otherwise shift start_time to the earliest release among active users
                        start_time = min(rel_time for rel_time, nid in active_users)

                # Set final schedule times
                task.earliest_start = start_time
                task.earliest_finish = start_time + duration
                task.allocated_resources = list(req_resources)

                # Record release times
                for res in req_resources:
                    if res not in resource_releases:
                        resource_releases[res] = []
                    resource_releases[res].append((task.earliest_finish, node_id))

        # Re-run backward pass to update latest times and slack based on shifted schedule
        try:
            order = graph.get_topological_sort()
        except ValueError:
            return scheduled

        if scheduled:
            max_finish = max(t.earliest_finish for t in scheduled.values())
            for node_id in reversed(order):
                node = graph.nodes[node_id]
                task = scheduled[node_id]
                duration = getattr(node.operator, "estimated_time", 1.0)
                children = graph.adjacency_list.get(node_id, [])

                if not children:
                    task.latest_finish = max_finish
                else:
                    task.latest_finish = min(scheduled[child_id].latest_start for child_id in children)

                task.latest_start = task.latest_finish - duration
                task.slack = max(0.0, task.latest_start - task.earliest_start)
                task.is_critical = task.slack < 0.001

        return scheduled
