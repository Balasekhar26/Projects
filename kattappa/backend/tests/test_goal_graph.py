"""Unit tests for Program 12.0 Goal Graph Foundation.
"""
from __future__ import annotations

import pytest
from backend.core.planning.planner_types import GoalPriority, GoalStatus
from backend.core.planning.plan_node import PlanNode
from backend.core.planning.goal_graph import GoalGraph


def test_goal_graph_cycle_detection():
    """Verifies that GoalGraph DAG prevents self-loops and circular dependencies."""
    graph = GoalGraph()

    # Create nodes
    node_a = PlanNode(goal_id="A", title="Goal A")
    node_b = PlanNode(goal_id="B", title="Goal B")
    node_c = PlanNode(goal_id="C", title="Goal C")

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(node_c)

    # A depends on B
    graph.add_dependency("A", "B")
    # B depends on C
    graph.add_dependency("B", "C")

    # Trying to make C depend on A should trigger a circular dependency check failure
    with pytest.raises(ValueError) as excinfo:
        graph.add_dependency("C", "A")
    assert "would cause a circular cycle" in str(excinfo.value)

    # Trying to make A depend on itself should fail
    with pytest.raises(ValueError) as excinfo:
        graph.add_dependency("A", "A")
    assert "Self-loop detected" in str(excinfo.value)


def test_goal_graph_topological_sort():
    """Verifies that topological sorting returns dependencies before dependents."""
    graph = GoalGraph()

    node_a = PlanNode(goal_id="A", title="Deploy App")
    node_b = PlanNode(goal_id="B", title="Build Frontend")
    node_c = PlanNode(goal_id="C", title="Build Backend")
    node_d = PlanNode(goal_id="D", title="Install DB")

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(node_c)
    graph.add_node(node_d)

    # Dependency layout:
    # A depends on B and C
    # B depends on D
    # C depends on D
    graph.add_dependency("A", "B")
    graph.add_dependency("A", "C")
    graph.add_dependency("B", "D")
    graph.add_dependency("C", "D")

    sort_order = graph.get_topological_sort()

    # D must precede B and C, and both B and C must precede A
    assert sort_order.index("D") < sort_order.index("B")
    assert sort_order.index("D") < sort_order.index("C")
    assert sort_order.index("B") < sort_order.index("A")
    assert sort_order.index("C") < sort_order.index("A")


def test_goal_graph_critical_path():
    """Verifies Critical Path Method longest-path duration logic."""
    graph = GoalGraph()

    # D (duration 5s) -> B (duration 3s) \
    #                                   -> A (duration 2s)
    # D (duration 5s) -> C (duration 8s) /
    node_a = PlanNode(goal_id="A", title="A", estimated_duration=2.0)
    node_b = PlanNode(goal_id="B", title="B", estimated_duration=3.0)
    node_c = PlanNode(goal_id="C", title="C", estimated_duration=8.0)
    node_d = PlanNode(goal_id="D", title="D", estimated_duration=5.0)

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(node_c)
    graph.add_node(node_d)

    graph.add_dependency("A", "B")
    graph.add_dependency("A", "C")
    graph.add_dependency("B", "D")
    graph.add_dependency("C", "D")

    path, total_duration = graph.calculate_critical_path()

    # Longest path must be D -> C -> A (duration 5 + 8 + 2 = 15s)
    assert path == ["D", "C", "A"]
    assert total_duration == 15.0


def test_goal_graph_unblocked_nodes():
    """Verifies retrieval of proposed/waiting nodes whose dependencies are completed."""
    graph = GoalGraph()

    node_a = PlanNode(goal_id="A", title="A", status=GoalStatus.PROPOSED)
    node_b = PlanNode(goal_id="B", title="B", status=GoalStatus.COMPLETED)
    node_c = PlanNode(goal_id="C", title="C", status=GoalStatus.PROPOSED)

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(node_c)

    # A depends on B (which is completed) -> Unblocked
    graph.add_dependency("A", "B")
    # C depends on A (which is proposed) -> Blocked
    graph.add_dependency("C", "A")

    unblocked = graph.get_unblocked_nodes()
    unblocked_ids = {n.goal_id for n in unblocked}

    assert "A" in unblocked_ids
    assert "C" not in unblocked_ids


def test_goal_graph_serialization_roundtrip():
    """Verifies that serialization/deserialization retains full nodes and edges topology."""
    graph = GoalGraph()

    node_a = PlanNode(goal_id="A", title="A", priority=GoalPriority.CRITICAL)
    node_b = PlanNode(goal_id="B", title="B", estimated_duration=4.5)

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_dependency("B", "A")

    # Serialize
    serialized = graph.to_dict()

    # Deserialize
    restored = GoalGraph.from_dict(serialized)

    assert "A" in restored.nodes
    assert restored.nodes["A"].priority == GoalPriority.CRITICAL
    assert restored.nodes["B"].estimated_duration == 4.5
    assert restored.adjacency_list["A"] == ["B"]


def test_goal_graph_set_status_ledger_emission(monkeypatch):
    """Verifies that setting node status triggers ledger events."""
    import sys
    from unittest.mock import MagicMock
    
    # 1. Create a mocked Kernel module and instance
    mock_kernel_module = MagicMock()
    mock_kernel_instance = MagicMock()
    mock_kernel_module.KERNEL = mock_kernel_instance
    
    # Record events appended to the mock ledger
    emitted_events = []
    mock_kernel_instance.ledger.append.side_effect = emitted_events.append
    
    # 2. Patch sys.modules
    monkeypatch.setitem(sys.modules, "backend.core.cos.kernel", mock_kernel_module)
    
    # 3. Create graph and transition statuses
    graph = GoalGraph()
    node = PlanNode(goal_id="A", title="Task A")
    graph.add_node(node)
    
    graph.set_status("A", GoalStatus.ACTIVE)
    assert node.status == GoalStatus.ACTIVE
    
    graph.set_status("A", GoalStatus.COMPLETED)
    assert node.status == GoalStatus.COMPLETED
    
    # Ensure ledger events were created (at least GoalCreated + StateTransitioned + ExecutionCompleted)
    assert len(emitted_events) >= 3
