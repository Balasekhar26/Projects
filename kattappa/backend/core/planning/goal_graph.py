"""Goal Graph Directed Acyclic Graph (DAG) (Program 12.0).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.planning.planner_types import GoalPriority, GoalStatus
from backend.core.planning.plan_node import PlanNode
from backend.core.planning.planner_events import (
    GoalCreatedEvent,
    GoalStartedEvent,
    GoalCompletedEvent,
    GoalFailedEvent,
    GoalCancelledEvent,
)

logger = logging.getLogger(__name__)


class GoalGraph:
    """Represents a Directed Acyclic Graph (DAG) of PlanNodes representing goal hierarchies."""

    def __init__(self) -> None:
        self.nodes: Dict[str, PlanNode] = {}
        # Maps goal_id -> list of child goal_ids (nodes that depend on this node)
        self.adjacency_list: Dict[str, List[str]] = {}
        # Maps goal_id -> list of parent goal_ids (nodes this node depends on)
        self.in_degree_list: Dict[str, List[str]] = {}

    def add_node(self, node: PlanNode) -> None:
        """Registers a PlanNode in the graph."""
        if node.goal_id in self.nodes:
            raise ValueError(f"PlanNode with ID '{node.goal_id}' already exists.")
        
        self.nodes[node.goal_id] = node
        if node.goal_id not in self.adjacency_list:
            self.adjacency_list[node.goal_id] = []
        if node.goal_id not in self.in_degree_list:
            self.in_degree_list[node.goal_id] = []

        # Connect initial dependencies if provided
        for dep in node.dependencies:
            self.add_dependency(node.goal_id, dep)

        # Emit GoalCreated event to ledger if KERNEL is initialized
        self._emit_event(GoalCreatedEvent.create(node))

    def add_dependency(self, goal_id: str, depends_on_id: str) -> None:
        """Adds a directed dependency link: goal_id depends on depends_on_id."""
        if goal_id not in self.nodes or depends_on_id not in self.nodes:
            raise KeyError("Both nodes must exist in the GoalGraph before creating a dependency.")
        
        if goal_id == depends_on_id:
            raise ValueError(f"Self-loop detected: '{goal_id}' cannot depend on itself.")

        # Temporarily add edge to check for cycle
        current_parents = self.in_degree_list.get(goal_id, [])
        if depends_on_id in current_parents:
            return  # Already exists

        # Check cycle
        if self._would_cause_cycle(goal_id, depends_on_id):
            raise ValueError(f"Adding dependency from '{goal_id}' to '{depends_on_id}' would cause a circular cycle.")

        # Establish link
        self.adjacency_list[depends_on_id].append(goal_id)
        self.in_degree_list[goal_id].append(depends_on_id)
        
        # Keep dependencies list in PlanNode synchronized
        node = self.nodes[goal_id]
        if depends_on_id not in node.dependencies:
            node.dependencies.append(depends_on_id)

    def remove_dependency(self, goal_id: str, depends_on_id: str) -> None:
        """Removes a dependency link between nodes."""
        if goal_id in self.in_degree_list and depends_on_id in self.in_degree_list[goal_id]:
            self.in_degree_list[goal_id].remove(depends_on_id)
        if depends_on_id in self.adjacency_list and goal_id in self.adjacency_list[depends_on_id]:
            self.adjacency_list[depends_on_id].remove(goal_id)
        
        node = self.nodes.get(goal_id)
        if node and depends_on_id in node.dependencies:
            node.dependencies.remove(depends_on_id)

    def is_acyclic(self) -> bool:
        """Returns True if there are no circular dependencies in the graph."""
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)

            for child in self.adjacency_list.get(node_id, []):
                if child not in visited:
                    if dfs(child):
                        return True
                elif child in rec_stack:
                    return True

            rec_stack.remove(node_id)
            return False

        for node_id in self.nodes:
            if node_id not in visited:
                if dfs(node_id):
                    return False
        return True

    def get_topological_sort(self) -> List[str]:
        """Returns node IDs sorted topologically (dependencies before dependents)."""
        if not self.is_acyclic():
            raise ValueError("GoalGraph contains circular cycles; cannot perform topological sorting.")

        visited: Set[str] = set()
        order: List[str] = []

        def visit(node_id: str):
            if node_id not in visited:
                visited.add(node_id)
                # Post-order: visit downstream dependents first
                for child in self.adjacency_list.get(node_id, []):
                    visit(child)
                order.insert(0, node_id)

        # Iterate in reverse key order to maintain consistent sorting
        for node_id in sorted(self.nodes.keys()):
            if node_id not in visited:
                visit(node_id)

        return order

    def get_parallel_layers(self) -> List[List[str]]:
        """Groups node IDs into parallel layers that can be executed concurrently."""
        if not self.is_acyclic():
            raise ValueError("Cannot compute parallel layers: Graph contains cycles.")

        layers: List[List[str]] = []
        # Copy in-degrees to track solved nodes
        in_degrees = {node_id: len(parents) for node_id, parents in self.in_degree_list.items()}

        while True:
            # Find all nodes with 0 in-degree in the current iteration
            current_layer = [node_id for node_id, deg in in_degrees.items() if deg == 0]
            if not current_layer:
                break

            layers.append(current_layer)

            # Remove current layer nodes from in-degree map and update children
            for node_id in current_layer:
                del in_degrees[node_id]
                for child in self.adjacency_list.get(node_id, []):
                    if child in in_degrees:
                        in_degrees[child] -= 1

        return layers

    def get_unblocked_nodes(self) -> List[PlanNode]:
        """Returns all proposed/waiting/planning nodes whose dependencies are completed."""
        unblocked = []
        for node in self.nodes.values():
            if node.status in {GoalStatus.PROPOSED, GoalStatus.WAITING, GoalStatus.PLANNING}:
                all_completed = True
                for dep_id in node.dependencies:
                    dep_node = self.nodes.get(dep_id)
                    if not dep_node or dep_node.status != GoalStatus.COMPLETED:
                        all_completed = False
                        break
                if all_completed:
                    unblocked.append(node)
        return unblocked

    def calculate_critical_path(self) -> Tuple[List[str], float]:
        """Computes the critical path (longest duration sequence) and total estimated duration."""
        if not self.nodes:
            return [], 0.0

        order = self.get_topological_sort()
        
        # u -> maximum distance from start to u
        max_dist: Dict[str, float] = {}
        # u -> parent u depends on for max distance
        predecessor: Dict[str, Optional[str]] = {}

        # Initialize distances with each node's own duration
        for node_id in self.nodes:
            max_dist[node_id] = self.nodes[node_id].estimated_duration
            predecessor[node_id] = None

        # Standard topological longest path algorithm
        for u in order:
            for v in self.adjacency_list.get(u, []):
                dist_through_u = max_dist[u] + self.nodes[v].estimated_duration
                if dist_through_u > max_dist[v]:
                    max_dist[v] = dist_through_u
                    predecessor[v] = u

        if not max_dist:
            return [], 0.0

        # Find the end node of the longest path
        end_node = max(max_dist, key=lambda k: max_dist[k])
        total_duration = max_dist[end_node]

        # Reconstruct path backwards
        path = []
        curr: Optional[str] = end_node
        while curr is not None:
            path.append(curr)
            curr = predecessor[curr]

        return path[::-1], total_duration

    def set_status(self, goal_id: str, status: GoalStatus, reason: Optional[str] = None) -> None:
        """Transitions node status and logs event to Execution Ledger."""
        if goal_id not in self.nodes:
            raise KeyError(f"PlanNode '{goal_id}' not found.")
        
        node = self.nodes[goal_id]
        old_status = node.status
        node.status = status
        logger.info("Goal '%s' transitioned status: %s -> %s", goal_id, old_status, status)

        # Emit structured ledger events based on status change
        if status == GoalStatus.ACTIVE:
            self._emit_event(GoalStartedEvent.create(goal_id))
        elif status == GoalStatus.COMPLETED:
            self._emit_event(GoalCompletedEvent.create(goal_id))
        elif status == GoalStatus.FAILED:
            self._emit_event(GoalFailedEvent.create(goal_id, reason or "Execution failed"))
        elif status == GoalStatus.CANCELLED:
            self._emit_event(GoalCancelledEvent.create(goal_id))

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the graph topology and nodes."""
        return {
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            "edges": [
                {"parent_id": parent, "child_id": child}
                for parent, children in self.adjacency_list.items()
                for child in children
            ]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GoalGraph:
        """Restores a GoalGraph from serialized state."""
        graph = cls()
        nodes_data = data.get("nodes", {})
        
        # Register nodes first
        for node_id, node_dict in nodes_data.items():
            node = PlanNode.from_dict(node_dict)
            graph.nodes[node_id] = node
            graph.adjacency_list[node_id] = []
            graph.in_degree_list[node_id] = []

        # Re-draw edges
        edges_data = data.get("edges", [])
        for edge in edges_data:
            parent = edge["parent_id"]
            child = edge["child_id"]
            if parent in graph.nodes and child in graph.nodes:
                graph.adjacency_list[parent].append(child)
                graph.in_degree_list[child].append(parent)

        return graph

    def _would_cause_cycle(self, goal_id: str, depends_on_id: str) -> bool:
        """Helper to determine if depends_on_id depends transitively on goal_id."""
        visited: Set[str] = set()

        def dfs(curr: str) -> bool:
            if curr == goal_id:
                return True
            if curr in visited:
                return False
            visited.add(curr)
            # Traverse up the dependency tree
            for parent in self.in_degree_list.get(curr, []):
                if dfs(parent):
                    return True
            return False

        return dfs(depends_on_id)

    def _emit_event(self, event: Any) -> None:
        """Appends the event to the CognitiveKernel Execution Ledger if active."""
        try:
            from backend.core.cos.kernel import KERNEL
            if KERNEL and KERNEL.ledger:
                KERNEL.ledger.append(event)
        except Exception:
            pass
