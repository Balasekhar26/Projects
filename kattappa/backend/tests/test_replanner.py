"""Unit and integration tests for Program 12.4 Replanner and Recovery Engine.
"""
from __future__ import annotations

import socket
import pytest
from backend.core.planning.task_library import TaskLibrary
from backend.core.planning.planner_types import GoalPriority, GoalStatus
from backend.core.planning.plan_node import PlanNode
from backend.core.planning.plan import Plan
from backend.core.planning.htn_planner import HTNPlanner
from backend.core.planning.replanner import Replanner
from backend.core.planning.failure_classifier import FailureClassifier, FailureCategory
from backend.core.execution.typed_errors import ValidationError, PermissionDenied



def test_failure_classifier():
    """Verifies exception mappings to FailureCategory enums."""
    classifier = FailureClassifier()

    assert classifier.classify(socket.timeout("Connection lost")) == FailureCategory.NETWORK_TIMEOUT
    assert classifier.classify(PermissionDenied("Invalid API Key")) == FailureCategory.PERMISSION_DENIED

    assert classifier.classify(ValidationError("Exceeded cost budget")) == FailureCategory.INSUFFICIENT_BUDGET
    assert classifier.classify(ValidationError("Policy blocked task")) == FailureCategory.POLICY_VIOLATION
    assert classifier.classify(Exception("Database connection rate limit")) == FailureCategory.API_RATE_LIMIT
    assert classifier.classify(Exception("Disk exhaustion trigger")) == FailureCategory.RESOURCE_EXHAUSTION


def test_replanner_retry_strategy():
    """Verifies retry policy resets node status to PROPOSED and increments plan generation."""
    planner = HTNPlanner()
    replanner = Replanner(planner, max_attempts=2)

    plan = planner.generate_plan(
        goal_id="g1",
        root_task_name="PrepareDemoSystem",
        initial_state=["internet_available"]
    )

    # Set one node as failed (e.g. DownloadBinary)
    node_id = None
    for nid, node in plan.graph.nodes.items():
        if node.title == "DownloadBinary":
            node_id = nid
            node.status = GoalStatus.FAILED
            break

    # Run replanner on timeout error -> should retry
    repaired_plan = replanner.handle_failure(
        plan=plan,
        failed_node_id=node_id,
        error=socket.timeout("Temporary glitch"),
        world_state={"final_state": ["internet_available"]}
    )

    assert repaired_plan.plan_id != plan.plan_id
    assert repaired_plan.parent_plan_id == plan.plan_id
    assert repaired_plan.generation == 2
    
    # Target node should be reset back to PROPOSED
    repaired_node = repaired_plan.graph.nodes[node_id]
    assert repaired_node.status == GoalStatus.PROPOSED
    assert repaired_node.retry_count == 1


def test_replanner_budget_exhaustion_escalation():
    """Verifies that exceeding node recovery retry budgets triggers escalation."""
    planner = HTNPlanner()
    replanner = Replanner(planner, max_attempts=2)

    plan = planner.generate_plan(
        goal_id="g1",
        root_task_name="PrepareDemoSystem",
        initial_state=["internet_available"]
    )

    node_id = None
    for nid, node in plan.graph.nodes.items():
        if node.title == "DownloadBinary":
            node_id = nid
            break

    # First attempt: Retry
    plan_1 = replanner.handle_failure(plan, node_id, socket.timeout("glitch"), {})
    # Second attempt: Retry
    plan_2 = replanner.handle_failure(plan_1, node_id, socket.timeout("glitch"), {})
    # Third attempt: Exceeds max_attempts=2 -> should ESCALATE
    plan_escaped = replanner.handle_failure(plan_2, node_id, socket.timeout("glitch"), {})

    assert plan_escaped.metadata.get("requires_human_approval") is True
    assert "ESCALATE" in plan_escaped.metadata.get("escalation_reason", "")



def test_replanner_partial_subtree_repair():
    """Verifies partial plan repair: completed tasks are kept, downstream subtree is replaced."""
    planner = HTNPlanner()
    replanner = Replanner(planner)

    plan = planner.generate_plan(
        goal_id="g1",
        root_task_name="PrepareDemoSystem",
        initial_state=["internet_available"]
    )

    # Pre-complete:
    # VerifyHardware (2.0s) -> set to COMPLETED
    # DownloadBinary -> set to FAILED
    # Dependents (ConfigureSettings, RunDiagnostics, GenerateReport) must be removed and replaced!
    verify_hw_id = None
    download_bin_id = None
    for nid, node in plan.graph.nodes.items():
        if node.title == "VerifyHardware":
            verify_hw_id = nid
            node.status = GoalStatus.COMPLETED
        elif node.title == "DownloadBinary":
            download_bin_id = nid
            node.status = GoalStatus.FAILED

    world_state = {
        "final_state": ["internet_available", "hardware_verified", "binary_downloaded"],
    }


    # Trigger repair under dependency failure exception
    repaired_plan = replanner.handle_failure(
        plan=plan,
        failed_node_id=download_bin_id,
        error=Exception("generic error on download source"),

        world_state=world_state
    )

    # 1. Lineage checks
    assert repaired_plan.generation == 2
    assert repaired_plan.parent_plan_id == plan.plan_id

    # 2. Subgraph checks
    # VerifyHardware must still exist with COMPLETED status
    assert verify_hw_id in repaired_plan.graph.nodes
    assert repaired_plan.graph.nodes[verify_hw_id].status == GoalStatus.COMPLETED

    # The failed DownloadBinary ID must NOT exist in repaired plan
    assert download_bin_id not in repaired_plan.graph.nodes

    # The rule (DownloadBinary) was marked as tabu
    assert replanner.policy_engine.is_tabu("DownloadBinary")

    # Entry nodes of repaired subtree should depend on VerifyHardware (preserved parent dependency)
    # The substitute task here was DownloadBinary -> tool substitution to ConfigureSettings!
    # ConfigureSettings requires binary_downloaded, so to check the graft:
    # Let's ensure the grafted nodes are in the graph.
    grafted_titles = {n.title for n in repaired_plan.graph.nodes.values() if n.status == GoalStatus.PROPOSED}
    assert "ConfigureSettings" in grafted_titles
    assert "RunDiagnostics" in grafted_titles
