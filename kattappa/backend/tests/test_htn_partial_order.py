"""Unit and integration tests for HTN Planner Partial Ordering, State Transitions, and Costs.
"""
from __future__ import annotations

import pytest
from backend.core.planning.task_library import TaskLibrary, TaskDefinition
from backend.core.planning.htn_planner import HTNPlanner, PLANNER_VERSION
from backend.core.planning.planner_types import GoalStatus
from backend.core.execution.typed_errors import ValidationError


def test_htn_failed_preconditions():
    """Verifies that the planner raises a ValidationError when preconditions are unmet."""
    planner = HTNPlanner()

    # "PrepareDemoSystem" includes "DownloadBinary" which requires "internet_available".
    # Passing an empty initial_state should cause it to fail.
    with pytest.raises(ValidationError) as excinfo:
        planner.generate_plan(
            goal_id="demo-goal",
            root_task_name="PrepareDemoSystem",
            initial_state=[]
        )

    assert "Unmet precondition 'internet_available'" in str(excinfo.value)


def test_htn_state_transitions_and_provenance():
    """Verifies that states propagate correctly and provenance is recorded."""
    planner = HTNPlanner()

    # Pass internet_available to satisfy all preconditions
    plan = planner.generate_plan(
        goal_id="demo-goal",
        root_task_name="PrepareDemoSystem",
        initial_state=["internet_available"]
    )

    # Prove version provenance is set on Plan Node
    node = list(plan.graph.nodes.values())[0]
    assert node.metadata["planner_version"] == PLANNER_VERSION
    assert "planning_timestamp" in node.metadata

    # Check Plan-level metadata provenance
    assert plan.metadata["planner_version"] == PLANNER_VERSION
    assert "planning_timestamp" in plan.metadata
    assert "internet_available" in plan.metadata["final_state"]
    assert "report_generated" in plan.metadata["final_state"]


def test_htn_cost_vectors():
    """Verifies that cost vectors are aggregated correctly."""
    planner = HTNPlanner()

    plan = planner.generate_plan(
        goal_id="demo-goal",
        root_task_name="PrepareDemoSystem",
        initial_state=["internet_available"]
    )

    costs = plan.metadata["accumulated_costs"]
    # Verify exact multidimensional cost sums:
    # VerifyHardware: cpu=1.0, time=2.0
    # DownloadBinary: api=1000.0, dollars=1.5, time=10.0
    # ConfigureSettings: cpu=0.5, time=3.0
    # RunDiagnostics: cpu=2.0, time=5.0
    # GenerateReport: cpu=0.2, time=1.5
    # Total expected: cpu=3.7, api=1000.0, dollars=1.5, time=21.5
    assert costs["cpu_seconds"] == 3.7
    assert costs["api_tokens"] == 1000.0
    assert costs["dollars"] == 1.5
    assert costs["time"] == 21.5


def test_htn_partial_ordering_parallelism():
    """Verifies partial order execution paths. Independent tasks must be parallelizable."""
    library = TaskLibrary()

    # Define tasks:
    # VerifyDisk Space: preconditions=[], effects=["disk_verified"]
    # VerifyMemory: preconditions=[], effects=["memory_verified"]
    # RunSystemSetup: preconditions=["disk_verified", "memory_verified"], effects=["setup_done"]
    library.register_task(TaskDefinition(
        name="VerifyDisk",
        is_primitive=True,
        preconditions=[],
        effects=["disk_verified"]
    ))
    library.register_task(TaskDefinition(
        name="VerifyMemory",
        is_primitive=True,
        preconditions=[],
        effects=["memory_verified"]
    ))
    library.register_task(TaskDefinition(
        name="RunSystemSetup",
        is_primitive=True,
        preconditions=["disk_verified", "memory_verified"],
        effects=["setup_done"]
    ))
    library.register_task(TaskDefinition(
        name="SetupSystem",
        is_primitive=False,
        subtasks=["VerifyDisk", "VerifyMemory", "RunSystemSetup"]
    ))

    planner = HTNPlanner(library)
    plan = planner.generate_plan(goal_id="setup-goal", root_task_name="SetupSystem")

    # The GoalGraph DAG should:
    # 1. Place VerifyDisk and VerifyMemory in Layer 0 (both have 0 in-degree dependencies)
    # 2. Place RunSystemSetup in Layer 1 (depends on both VerifyDisk and VerifyMemory)
    
    layers = plan.graph.get_parallel_layers()
    
    assert len(layers) == 2
    
    # Layer 0 must contain both VerifyDisk and VerifyMemory
    layer_0_titles = {plan.graph.nodes[node_id].title for node_id in layers[0]}
    assert "VerifyDisk" in layer_0_titles
    assert "VerifyMemory" in layer_0_titles
    
    # Layer 1 must contain RunSystemSetup
    layer_1_titles = {plan.graph.nodes[node_id].title for node_id in layers[1]}
    assert layer_1_titles == {"RunSystemSetup"}
