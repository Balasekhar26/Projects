"""Plan Graph Builder Engine (Program 5G-3).

Converts linear plan steps into a Directed Acyclic Graph (DAG) by matching
effects to preconditions. Computes topological sorting and parallel execution layers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.planning.task import Operator, Plan

logger = logging.getLogger(__name__)


@dataclass
class PlanNode:
    """Wraps a primitive Operator step in the dependency graph."""
    node_id: str
    operator: Operator
    status: str = "Pending" # Pending, Running, Completed, Failed


@dataclass
class PlanEdge:
    """Represents a directed dependency link from parent to child."""
    parent_id: str
    child_id: str


class DependencyGraph:
    """Represents a Directed Acyclic Graph (DAG) of PlanNodes and PlanEdges."""

    def __init__(self) -> None:
        self.nodes: Dict[str, PlanNode] = {}
        # parent -> list of child IDs
        self.adjacency_list: Dict[str, List[str]] = {}
        # child -> list of parent IDs
        self.in_degree_list: Dict[str, List[str]] = {}

    def add_node(self, node: PlanNode) -> None:
        self.nodes[node.node_id] = node
        if node.node_id not in self.adjacency_list:
            self.adjacency_list[node.node_id] = []
        if node.node_id not in self.in_degree_list:
            self.in_degree_list[node.node_id] = []

    def add_edge(self, parent_id: str, child_id: str) -> None:
        if parent_id not in self.nodes or child_id not in self.nodes:
            raise ValueError("Both parent and child nodes must exist in the graph.")
        if child_id not in self.adjacency_list[parent_id]:
            self.adjacency_list[parent_id].append(child_id)
        if parent_id not in self.in_degree_list[child_id]:
            self.in_degree_list[child_id].append(parent_id)

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
        """Returns node IDs sorted topologically (parents before children)."""
        if not self.is_acyclic():
            raise ValueError("Cannot perform topological sort: Graph contains cycles.")

        visited: Set[str] = set()
        order: List[str] = []

        def visit(node_id: str):
            if node_id not in visited:
                visited.add(node_id)
                # Visit all children first (recursive post-order)
                for child in self.adjacency_list.get(node_id, []):
                    visit(child)
                order.insert(0, node_id)

        for node_id in self.nodes:
            if node_id not in visited:
                visit(node_id)

        return order

    def get_parallel_layers(self) -> List[List[str]]:
        """Groups node IDs into parallel layers that can be executed concurrently.

        Layer 0 nodes have no dependencies. Layer 1 nodes only depend on Layer 0 nodes, etc.
        """
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

    def to_json(self) -> Dict[str, Any]:
        """Serializes the graph structure to a JSON compatible dictionary."""
        return {
            "nodes": [
                {
                    "node_id": n.node_id,
                    "operator_name": n.operator.name,
                    "status": n.status,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {"parent_id": parent, "child_id": child}
                for parent, children in self.adjacency_list.items()
                for child in children
            ]
        }

    def to_graphviz(self) -> str:
        """Generates Graphviz DOT visualization layout."""
        lines = ["digraph PlanGraph {", "  node [shape=box, style=filled, fillcolor=lightblue];"]
        for node in self.nodes.values():
            lines.append(f'  "{node.node_id}" [label="{node.operator.name} ({node.status})"];')
        for parent, children in self.adjacency_list.items():
            for child in children:
                lines.append(f'  "{parent}" -> "{child}";')
        lines.append("}")
        return "\n".join(lines)


class PlanCompiler:
    """Compiles linear sequence plans into execution DependencyGraphs."""

    @staticmethod
    def compile_plan_to_graph(plan: Plan) -> DependencyGraph:
        """Builds a DependencyGraph by mapping preconditions of steps to prior effects."""
        graph = DependencyGraph()

        # 1. Add all steps as nodes
        for idx, op in enumerate(plan.steps):
            # Create a unique node ID combining operator name and index to prevent collisions
            node_id = f"{op.name}_{idx}"
            node = PlanNode(node_id=node_id, operator=op)
            graph.add_node(node)

        # 2. Draw edges by matching preconditions to the most recent producer effect
        # Walk forward through steps
        nodes_list = list(graph.nodes.values())
        for idx, current_node in enumerate(nodes_list):
            current_op = current_node.operator
            
            # For each precondition, find the most recent prior step that produces this effect
            for pre_key, pre_val in current_op.preconditions.items():
                producer_found = False
                for j in range(idx - 1, -1, -1):
                    prior_node = nodes_list[j]
                    prior_op = prior_node.operator

                    # If prior step effects contain the target key and match value
                    if prior_op.effects.get(pre_key) == pre_val:
                        graph.add_edge(prior_node.node_id, current_node.node_id)
                        producer_found = True
                        break  # Found the most recent producer, stop searching backward

        return graph
