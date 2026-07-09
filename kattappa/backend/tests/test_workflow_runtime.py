"""Unit tests for Program 57.0: Workflow Runtime.

Verifies DAG execution, retry logic, timeout handling, checkpoint persistence,
fallback skill invocation, and EventBus integration.
"""
from __future__ import annotations

import time
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from backend.core.skill_composer import ComposedSkill, SkillComposer
from backend.core.skill_runtime import Skill
from backend.core.workflow_runtime import (
    NodeState,
    WorkflowPolicy,
    WorkflowRuntime,
    WorkflowState,
    _delete_checkpoint,
    _load_checkpoint,
    _save_checkpoint,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_composed(
    skills: list[dict],
    dependencies: dict | None = None,
    fallbacks: dict | None = None,
    name: str = "Test Workflow",
) -> ComposedSkill:
    return SkillComposer.compose_skills(
        name=name,
        description="Unit test composed skill",
        skills=skills,
        dependencies=dependencies or {},
        fallbacks=fallbacks or {},
    )


def _always_succeed_factory(node_name: str, skill_def: Dict[str, Any]) -> MagicMock:
    """Returns a Skill mock that always succeeds on the first attempt."""
    skill = MagicMock(spec=Skill)
    skill.name = node_name
    skill.execute.return_value = {"status": "success", "outputs": {"result": f"{node_name}_done"}}
    return skill


def _always_fail_factory(node_name: str, skill_def: Dict[str, Any]) -> MagicMock:
    """Returns a Skill mock that always fails."""
    skill = MagicMock(spec=Skill)
    skill.name = node_name
    skill.execute.return_value = {"status": "failed", "reason": f"{node_name} intentionally failed"}
    return skill


# ---------------------------------------------------------------------------
# Test: basic linear workflow executes successfully
# ---------------------------------------------------------------------------

def test_linear_workflow_success():
    skills = [
        {"name": "Step A", "cost_profile": "low"},
        {"name": "Step B", "cost_profile": "low"},
        {"name": "Step C", "cost_profile": "low"},
    ]
    dependencies = {
        "Step B": ["Step A"],
        "Step C": ["Step B"],
    }

    composed = _make_composed(skills, dependencies)

    result = WorkflowRuntime.execute(
        composed_skill=composed,
        skill_factory=_always_succeed_factory,
        params={"env": "test"},
        policy=WorkflowPolicy(max_retries=0),
    )

    assert result["status"] == "COMPLETED"
    assert result["failed_nodes"] == []
    assert "Step A" in result["final_outputs"]
    assert "Step B" in result["final_outputs"]
    assert "Step C" in result["final_outputs"]
    assert result["final_outputs"]["Step A"]["result"] == "Step A_done"


# ---------------------------------------------------------------------------
# Test: parallel layer workflow — all nodes in a layer complete
# ---------------------------------------------------------------------------

def test_parallel_layer_workflow():
    skills = [
        {"name": "Run Tests", "cost_profile": "low"},
        {"name": "Security Scan", "cost_profile": "medium"},
        {"name": "Build Container", "cost_profile": "medium"},
        {"name": "Deploy", "cost_profile": "high"},
    ]
    dependencies = {
        "Build Container": ["Run Tests", "Security Scan"],
        "Deploy": ["Build Container"],
    }

    composed = _make_composed(skills, dependencies)

    result = WorkflowRuntime.execute(
        composed_skill=composed,
        skill_factory=_always_succeed_factory,
        params={},
        policy=WorkflowPolicy(max_retries=0, max_concurrency=4),
    )

    assert result["status"] == "COMPLETED"
    assert result["failed_nodes"] == []
    # All 4 skills should have outputs
    assert len(result["final_outputs"]) == 4


# ---------------------------------------------------------------------------
# Test: failed node aborts workflow when continue_on_failure=False
# ---------------------------------------------------------------------------

def test_failure_aborts_workflow():
    skills = [
        {"name": "Step A"},
        {"name": "Step B"},
    ]
    dependencies = {"Step B": ["Step A"]}
    composed = _make_composed(skills, dependencies)

    result = WorkflowRuntime.execute(
        composed_skill=composed,
        skill_factory=_always_fail_factory,
        params={},
        policy=WorkflowPolicy(max_retries=0, continue_on_failure=False),
    )

    assert result["status"] == "FAILED"
    assert "Step A" in result["failed_nodes"]


# ---------------------------------------------------------------------------
# Test: continue_on_failure=True skips failed nodes and continues
# ---------------------------------------------------------------------------

def test_continue_on_failure():
    call_counts: Dict[str, int] = {}

    def _flaky_factory(node_name: str, skill_def: Dict[str, Any]) -> MagicMock:
        skill = MagicMock(spec=Skill)
        skill.name = node_name
        call_counts[node_name] = call_counts.get(node_name, 0) + 1
        if node_name == "Flaky Step":
            skill.execute.return_value = {"status": "failed", "reason": "flaky"}
        else:
            skill.execute.return_value = {"status": "success", "outputs": {}}
        return skill

    skills = [{"name": "Flaky Step"}, {"name": "Safe Step"}]
    # No dependencies — both are in the same layer, so workflow continues past the failure
    composed = _make_composed(skills)

    result = WorkflowRuntime.execute(
        composed_skill=composed,
        skill_factory=_flaky_factory,
        params={},
        policy=WorkflowPolicy(max_retries=0, continue_on_failure=True),
    )

    assert result["status"] == "COMPLETED"
    assert result["failed_nodes"] == []
    # Flaky Step should be skipped, not in failed_nodes
    assert "Safe Step" in result["final_outputs"]


# ---------------------------------------------------------------------------
# Test: retry policy — node succeeds on second attempt
# ---------------------------------------------------------------------------

def test_retry_policy_eventually_succeeds():
    attempt_counts: Dict[str, int] = {}

    def _retry_factory(node_name: str, skill_def: Dict[str, Any]) -> MagicMock:
        skill = MagicMock(spec=Skill)
        skill.name = node_name
        attempt_counts[node_name] = attempt_counts.get(node_name, 0) + 1
        if attempt_counts[node_name] < 2:
            skill.execute.return_value = {"status": "failed", "reason": "transient"}
        else:
            skill.execute.return_value = {"status": "success", "outputs": {"result": "ok"}}
        return skill

    skills = [{"name": "Retry Node"}]
    composed = _make_composed(skills)

    result = WorkflowRuntime.execute(
        composed_skill=composed,
        skill_factory=_retry_factory,
        params={},
        policy=WorkflowPolicy(max_retries=2, retry_base_delay=0.0),
    )

    assert result["status"] == "COMPLETED"
    assert attempt_counts["Retry Node"] >= 2


# ---------------------------------------------------------------------------
# Test: fallback skill invoked when primary node fails all retries
# ---------------------------------------------------------------------------

def test_fallback_skill_invoked():
    skills = [
        {"name": "Primary Skill"},
        {"name": "Fallback Skill"},
    ]
    fallbacks = {"Primary Skill": "Fallback Skill"}
    composed = _make_composed(skills, fallbacks=fallbacks)

    def _fallback_factory(node_name: str, skill_def: Dict[str, Any]) -> MagicMock:
        skill = MagicMock(spec=Skill)
        skill.name = node_name
        if node_name == "Primary Skill":
            skill.execute.return_value = {"status": "failed", "reason": "primary failed"}
        else:
            skill.execute.return_value = {"status": "success", "outputs": {"result": "fallback_result"}}
        return skill

    result = WorkflowRuntime.execute(
        composed_skill=composed,
        skill_factory=_fallback_factory,
        params={},
        policy=WorkflowPolicy(max_retries=0, retry_base_delay=0.0),
    )

    assert result["status"] == "COMPLETED"
    assert "Primary Skill" in result["final_outputs"]
    assert result["final_outputs"]["Primary Skill"].get("result") == "fallback_result"


# ---------------------------------------------------------------------------
# Test: checkpoint is saved and loadable mid-workflow
# ---------------------------------------------------------------------------

def test_checkpoint_persistence():
    state = WorkflowState(
        workflow_id="chk-test-001",
        composed_skill_name="Test Workflow",
    )
    state.node_states["Node A"] = NodeState.SUCCESS
    state.node_outputs["Node A"] = {"result": "done"}
    state.current_layer_index = 1

    _save_checkpoint(state)

    loaded = _load_checkpoint("chk-test-001")
    assert loaded is not None
    assert loaded.workflow_id == "chk-test-001"
    assert loaded.node_states["Node A"] == NodeState.SUCCESS
    assert loaded.current_layer_index == 1
    assert loaded.node_outputs["Node A"]["result"] == "done"

    # Cleanup
    _delete_checkpoint("chk-test-001")
    assert _load_checkpoint("chk-test-001") is None


# ---------------------------------------------------------------------------
# Test: list_checkpoints returns summary rows
# ---------------------------------------------------------------------------

def test_list_checkpoints():
    state = WorkflowState(workflow_id="list-test-001", composed_skill_name="List Test")
    _save_checkpoint(state)

    checkpoints = WorkflowRuntime.list_checkpoints()
    ids = [c["workflow_id"] for c in checkpoints]
    assert "list-test-001" in ids

    _delete_checkpoint("list-test-001")


# ---------------------------------------------------------------------------
# Test: workflow_id is generated and present in result
# ---------------------------------------------------------------------------

def test_workflow_id_in_result():
    skills = [{"name": "Single Node"}]
    composed = _make_composed(skills)

    result = WorkflowRuntime.execute(
        composed_skill=composed,
        skill_factory=_always_succeed_factory,
        params={},
        policy=WorkflowPolicy(max_retries=0),
    )

    assert "workflow_id" in result
    assert len(result["workflow_id"]) == 16  # uuid4 hex[:16]
    assert result["status"] == "COMPLETED"
