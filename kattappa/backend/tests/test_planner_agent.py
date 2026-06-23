import os
import shutil
import tempfile
import json
import pytest
from pathlib import Path

from backend.agents.planner import TaskStep, TaskGraph, PlannerAgent, planner_node
from backend.core.resource_governor import ResourceGovernor
from backend.core.action_broker import ActionBroker
from backend.core.memory_service import MemoryService
from backend.core.human_memory import HumanMemory


@pytest.fixture
def clean_planner_env(monkeypatch):
    """Sets a temporary folder for memory/governor data and resets systems."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_planner_test_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    
    HumanMemory.reset()
    ResourceGovernor.reset()
    
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_goal_decomposition(clean_planner_env):
    agent = PlannerAgent()
    graph = agent.decompose("Write code in sample.py and run tests")
    assert "step1" in graph.steps
    assert "step2" in graph.steps
    
    step1 = graph.get_step("step1")
    assert step1.agent == "coder"
    assert step1.action == "WRITE_FILE"
    assert step1.params["target"] == "backend/core/sample.py"
    
    step2 = graph.get_step("step2")
    assert step2.agent == "coder"
    assert step2.action == "RUN_TESTS"
    assert step2.dependencies == ["step1"]


def test_dependency_ordering(clean_planner_env):
    graph = TaskGraph("Test Goal")
    step1 = TaskStep(step_id="step1", description="s1", agent="coder", action="CREATE_FILE", params={}, dependencies=[])
    step2 = TaskStep(step_id="step2", description="s2", agent="coder", action="RUN_TESTS", params={}, dependencies=["step1"])
    step3 = TaskStep(step_id="step3", description="s3", agent="coder", action="DEPLOY", params={}, dependencies=["step2"])
    
    graph.add_step(step1)
    graph.add_step(step2)
    graph.add_step(step3)
    
    order = graph.topological_sort()
    assert order == ["step1", "step2", "step3"]


def test_circular_dependency_detection(clean_planner_env):
    graph = TaskGraph("Test Circular")
    step1 = TaskStep(step_id="step1", description="s1", agent="coder", action="CREATE_FILE", params={}, dependencies=["step2"])
    step2 = TaskStep(step_id="step2", description="s2", agent="coder", action="RUN_TESTS", params={}, dependencies=["step1"])
    
    graph.add_step(step1)
    graph.add_step(step2)
    
    assert graph.has_cycle() is True
    with pytest.raises(ValueError, match="Circular dependency detected"):
        graph.topological_sort()


def test_resource_estimation(clean_planner_env):
    agent = PlannerAgent()
    step = TaskStep(
        step_id="step1",
        description="Write code",
        agent="coder",
        action="WRITE_FILE",
        params={"target": "sample.py", "content": "print('hello world')"},
        dependencies=[]
    )
    est = agent.estimate_resources(step)
    assert est["disk_bytes"] == len("print('hello world')")
    assert est["tokens"] == 3000
    assert est["concurrent_tasks"] == 1
    assert est["valid"] is True


def test_approval_insertion(clean_planner_env):
    agent = PlannerAgent()
    
    # High risk action requires approval
    step_high = TaskStep(
        step_id="s_high",
        description="delete memory",
        agent="memory_service",
        action="DELETE_MEMORY",
        params={"memory_id": "123"},
        dependencies=[]
    )
    agent.insert_approval_gates(step_high)
    assert step_high.risk_level == "HIGH"
    assert step_high.approval_required is True

    # Low risk action does not require approval
    step_low = TaskStep(
        step_id="s_low",
        description="recall memory",
        agent="memory_service",
        action="RECALL_MEMORY",
        params={"query": "test"},
        dependencies=[]
    )
    agent.insert_approval_gates(step_low)
    assert step_low.risk_level == "LOW"
    assert step_low.approval_required is False


def test_rollback_generation(clean_planner_env):
    agent = PlannerAgent()
    
    # WRITE_FILE rollback is DELETE_FILE
    step1 = TaskStep(
        step_id="s1",
        description="write code",
        agent="coder",
        action="WRITE_FILE",
        params={"target": "path/to/file.py", "content": "code"},
        dependencies=[]
    )
    rb1 = agent.generate_rollback_step(step1)
    assert rb1 is not None
    assert rb1["action"] == "DELETE_FILE"
    assert rb1["params"]["target"] == "path/to/file.py"

    # PIN_MEMORY rollback is UNPIN_MEMORY
    step2 = TaskStep(
        step_id="s2",
        description="pin memory",
        agent="coder",
        action="PIN_MEMORY",
        params={"memory_id": "mem123"},
        dependencies=[]
    )
    rb2 = agent.generate_rollback_step(step2)
    assert rb2 is not None
    assert rb2["action"] == "UNPIN_MEMORY"
    assert rb2["params"]["memory_id"] == "mem123"


def test_failure_recovery_generation(clean_planner_env):
    agent = PlannerAgent()
    step1 = TaskStep(
        step_id="s1",
        description="run tests",
        agent="coder",
        action="RUN_TESTS",
        params={},
        dependencies=[]
    )
    rec1 = agent.generate_failure_recovery(step1)
    assert rec1["strategy"] == "debug_and_retry"
    assert rec1["max_attempts"] == 2
    assert rec1["fallback_action"] == "ANALYZE_CODE"

    step2 = TaskStep(
        step_id="s2",
        description="unsupported",
        agent="coder",
        action="OTHER_ACTION",
        params={},
        dependencies=[]
    )
    rec2 = agent.generate_failure_recovery(step2)
    assert rec2["strategy"] == "abort"


def test_planner_node_integration(clean_planner_env):
    state = {
        "user_input": "Write helper code and run tests",
        "plan": None,
        "selected_agent": None,
        "logs": [],
        "result": None,
        "memory_context": None,
        "task_graph": None
    }
    res_plan = planner_node(state)
    assert "task_graph" in res_plan
    assert "step1" in res_plan["task_graph"]
    assert "step2" in res_plan["task_graph"]
    
    # Verify logged to memory database
    recall_res = MemoryService.recall(agent="coder", query="execution plan")
    assert len(recall_res) > 0
    assert "Write the implementation file" in recall_res[0]["content"]
