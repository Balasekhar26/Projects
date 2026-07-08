"""Unit and integration tests for Program 5G-3: Plan Graph Builder.
"""
from __future__ import annotations

import pytest

from backend.core.planning.task import Operator, Plan
from backend.core.planning.plan_graph import PlanNode, DependencyGraph, PlanCompiler


def test_dependency_graph_cycle_detection():
    """Verifies that DependencyGraph identifies cycles."""
    graph = DependencyGraph()

    op1 = Operator("op1", "A")
    op2 = Operator("op2", "B")

    n1 = PlanNode("A_0", op1)
    n2 = PlanNode("B_1", op2)

    graph.add_node(n1)
    graph.add_node(n2)

    graph.add_edge("A_0", "B_1")
    assert graph.is_acyclic() is True

    # Add cycle B_1 -> A_0
    graph.add_edge("B_1", "A_0")
    assert graph.is_acyclic() is False


def test_topological_sorting():
    """Verifies topological sorting works on acyclic graphs."""
    graph = DependencyGraph()

    n1 = PlanNode("n1", Operator("op1", "Step 1"))
    n2 = PlanNode("n2", Operator("op2", "Step 2"))
    n3 = PlanNode("n3", Operator("op3", "Step 3"))

    graph.add_node(n1)
    graph.add_node(n2)
    graph.add_node(n3)

    graph.add_edge("n1", "n2")
    graph.add_edge("n2", "n3")

    order = graph.get_topological_sort()
    assert order == ["n1", "n2", "n3"]


def test_parallel_layers_calculation():
    """Tests that independent nodes are grouped into parallel execution layers."""
    graph = DependencyGraph()

    # Graph structure:
    #     n1
    #    /  \
    #  n2    n3
    #    \  /
    #     n4
    n1 = PlanNode("n1", Operator("op1", "S1"))
    n2 = PlanNode("n2", Operator("op2", "S2"))
    n3 = PlanNode("n3", Operator("op3", "S3"))
    n4 = PlanNode("n4", Operator("op4", "S4"))

    for node in [n1, n2, n3, n4]:
        graph.add_node(node)

    graph.add_edge("n1", "n2")
    graph.add_edge("n1", "n3")
    graph.add_edge("n2", "n4")
    graph.add_edge("n3", "n4")

    layers = graph.get_parallel_layers()
    # Layer 0: n1 (no dependencies)
    # Layer 1: n2, n3 (only depend on n1)
    # Layer 2: n4 (depends on n2, n3)
    assert len(layers) == 3
    assert layers[0] == ["n1"]
    assert set(layers[1]) == {"n2", "n3"}
    assert layers[2] == ["n4"]


def test_plan_compiler_effect_precondition_matching():
    """Verifies that PlanCompiler correctly draws edges between precondition consumers and effect producers."""
    # Step 0 produces "has_backup"
    op_backup = Operator(
        operator_id="backup",
        name="BackupAction",
        preconditions={},
        effects={"has_backup": True},
    )
    # Step 1 produces "has_checksum"
    op_checksum = Operator(
        operator_id="checksum",
        name="ChecksumAction",
        preconditions={},
        effects={"has_checksum": True},
    )
    # Step 2 requires both
    op_deploy = Operator(
        operator_id="deploy",
        name="DeployAction",
        preconditions={"has_backup": True, "has_checksum": True},
        effects={"done": True},
    )

    plan = Plan("p1", "g1", steps=[op_backup, op_checksum, op_deploy])
    graph = PlanCompiler.compile_plan_to_graph(plan)

    # We expect edges:
    # BackupAction_0 -> DeployAction_2
    # ChecksumAction_1 -> DeployAction_2
    assert "DeployAction_2" in graph.adjacency_list["BackupAction_0"]
    assert "DeployAction_2" in graph.adjacency_list["ChecksumAction_1"]

    # Verify parallel layers: BackupAction_0 and ChecksumAction_1 can run in parallel!
    layers = graph.get_parallel_layers()
    assert len(layers) == 2
    assert set(layers[0]) == {"BackupAction_0", "ChecksumAction_1"}
    assert layers[1] == ["DeployAction_2"]


def test_graphviz_dot_export():
    """Verifies Graphviz export contains basic DOT commands."""
    graph = DependencyGraph()
    graph.add_node(PlanNode("A", Operator("opA", "Action A")))

    dot = graph.to_graphviz()
    assert "digraph PlanGraph" in dot
    assert '"A"' in dot
