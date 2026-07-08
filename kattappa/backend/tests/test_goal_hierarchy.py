"""Tests for Phase K11: Goal Hierarchy (5 levels)."""
from __future__ import annotations

import pytest
from backend.core.goal_hierarchy import GoalHierarchy, HierarchyLevel, HierarchyNode


@pytest.fixture(autouse=True)
def clean_hierarchy():
    GoalHierarchy.reset()
    yield
    GoalHierarchy.reset()


def test_add_nodes_all_levels():
    # 1. Goal
    g = GoalHierarchy.add_node(
        node_id="goal_1",
        parent_id=None,
        level=HierarchyLevel.GOAL,
        title="Develop Radar DSP Processor",
        description="Core signal processing unit",
    )
    assert g.id == "goal_1"
    assert g.parent_id is None
    assert g.level == HierarchyLevel.GOAL

    # 2. Subgoal
    sg = GoalHierarchy.add_node(
        node_id="subgoal_1",
        parent_id="goal_1",
        level=HierarchyLevel.SUBGOAL,
        title="Implement FMCW Range-Doppler processing",
    )
    assert sg.parent_id == "goal_1"
    assert sg.level == HierarchyLevel.SUBGOAL

    # 3. Task
    t = GoalHierarchy.add_node(
        node_id="task_1",
        parent_id="subgoal_1",
        level=HierarchyLevel.TASK,
        title="Write 2D FFT logic",
    )
    assert t.parent_id == "subgoal_1"
    assert t.level == HierarchyLevel.TASK

    # 4. Action
    a = GoalHierarchy.add_node(
        node_id="action_1",
        parent_id="task_1",
        level=HierarchyLevel.ACTION,
        title="Coder writes fft2d.py",
    )
    assert a.parent_id == "task_1"
    assert a.level == HierarchyLevel.ACTION

    # 5. Tool Call
    tc = GoalHierarchy.add_node(
        node_id="tool_1",
        parent_id="action_1",
        level=HierarchyLevel.TOOL_CALL,
        title="Run WRITE_FILE tool",
        metadata={"target": "fft2d.py"},
    )
    assert tc.parent_id == "action_1"
    assert tc.level == HierarchyLevel.TOOL_CALL
    assert tc.metadata["target"] == "fft2d.py"


def test_progress_upward_propagation():
    # Setup a simple 3-level tree: Goal -> Task -> Tool Call
    GoalHierarchy.add_node("g_root", None, HierarchyLevel.GOAL, "Root Goal")
    GoalHierarchy.add_node("t1", "g_root", HierarchyLevel.TASK, "Task 1")
    GoalHierarchy.add_node("t2", "g_root", HierarchyLevel.TASK, "Task 2")
    
    GoalHierarchy.add_node("tc1", "t1", HierarchyLevel.TOOL_CALL, "Tool 1 under Task 1")
    GoalHierarchy.add_node("tc2", "t1", HierarchyLevel.TOOL_CALL, "Tool 2 under Task 1")

    # Initial state should be 0.0 progress
    assert GoalHierarchy.get_node("g_root").progress == 0.0
    assert GoalHierarchy.get_node("t1").progress == 0.0

    # 1. Complete Tool 1 (tc1)
    GoalHierarchy.update_node("tc1", status="COMPLETED", progress=1.0)
    
    # Task 1 (t1) should have average of (1.0 + 0.0) = 0.5 progress, status = ACTIVE
    t1_node = GoalHierarchy.get_node("t1")
    assert t1_node.progress == 0.5
    assert t1_node.status == "ACTIVE"

    # Root Goal (g_root) should have average of t1 and t2: (0.5 + 0.0) / 2 = 0.25 progress, status = ACTIVE
    root_node = GoalHierarchy.get_node("g_root")
    assert root_node.progress == 0.25
    assert root_node.status == "ACTIVE"

    # 2. Complete Tool 2 (tc2)
    GoalHierarchy.update_node("tc2", status="COMPLETED", progress=1.0)
    
    # Task 1 should now be 1.0 progress and COMPLETED (since all children are complete)
    t1_node = GoalHierarchy.get_node("t1")
    assert t1_node.progress == 1.0
    assert t1_node.status == "COMPLETED"
    assert t1_node.completed_at is not None

    # Root Goal should be (1.0 + 0.0) / 2 = 0.5 progress
    assert GoalHierarchy.get_node("g_root").progress == 0.5


def test_get_active_tree():
    GoalHierarchy.add_node("g1", None, HierarchyLevel.GOAL, "Goal 1")
    GoalHierarchy.add_node("g2", None, HierarchyLevel.GOAL, "Goal 2")
    GoalHierarchy.add_node("sg1", "g1", HierarchyLevel.SUBGOAL, "Subgoal 1.1")
    
    # Complete Goal 2 so it is excluded from active tree
    GoalHierarchy.update_node("g2", status="COMPLETED", progress=1.0)

    tree = GoalHierarchy.get_active_tree()
    assert len(tree["roots"]) == 1
    assert tree["roots"][0]["id"] == "g1"
    assert len(tree["roots"][0]["children"]) == 1
    assert tree["roots"][0]["children"][0]["id"] == "sg1"
