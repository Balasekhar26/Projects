import json
import tempfile
import shutil
from pathlib import Path
import pytest

from backend.agents.executive import ExecutiveAgent, executive_node
from backend.core.state import AgentState
from backend.core.capability_registry import CapabilityRegistry, CAP_GOAL_MANAGE, CAP_GOAL_SCHEDULE


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Sets a temporary folder for files and databases to isolate tests."""
    import psutil
    temp_dir = tempfile.mkdtemp(prefix="kattappa_executive_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", temp_dir)
    
    # Mock psutil to make tests deterministic under heavy host CPU/RAM load
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 10.0)
    class MockVirtualMemory:
        percent = 10.0
        used = 100 * 1024 * 1024
        available = 8 * 1024 * 1024 * 1024
    monkeypatch.setattr(psutil, "virtual_memory", lambda: MockVirtualMemory())
    
    # Reset schema ensured flags to allow new sqlite dbs to initialize
    from backend.core.human_memory import HumanMemoryStore
    if HumanMemoryStore._conn is not None:
        try:
            HumanMemoryStore._conn.close()
        except Exception:
            pass
        HumanMemoryStore._conn = None
    HumanMemoryStore._path = None
    
    from backend.core.goal_memory import GoalMemory
    GoalMemory._schema_ensured = False
    
    yield Path(temp_dir)
    
    # Teardown reset to avoid leaking connection state to other tests
    if HumanMemoryStore._conn is not None:
        try:
            HumanMemoryStore._conn.close()
        except Exception:
            pass
        HumanMemoryStore._conn = None
    HumanMemoryStore._path = None
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_executive_decomposition():
    # 1. RF Engineering goal
    res = ExecutiveAgent.decompose_goal("Learn RF Engineering")
    assert res["success"] is True
    goal_data = res["goal_data"]
    assert goal_data["status"] == "IN_PROGRESS"
    assert len(goal_data["milestones"]) == 3
    assert goal_data["milestones"][0]["title"] == "Research RF engineering core concepts and fundamentals"

    # 2. Chat application goal
    res_chat = ExecutiveAgent.decompose_goal("Build a chat app")
    assert res_chat["success"] is True
    assert len(res_chat["goal_data"]["milestones"]) == 3
    assert "React frontend" in res_chat["goal_data"]["milestones"][0]["title"]

    # 3. Fallback on general text
    res_fallback = ExecutiveAgent.decompose_goal("Write a poem about kattappa")
    assert res_fallback["success"] is True
    assert len(res_fallback["goal_data"]["milestones"]) >= 2


def test_milestone_queue_and_status():
    res = ExecutiveAgent.decompose_goal("Learn RF Engineering")
    goal_data = res["goal_data"]

    # First pending milestone
    next_m = ExecutiveAgent.get_next_milestone(goal_data)
    assert next_m["id"] == "m1"

    # Complete first milestone
    update_res = ExecutiveAgent.update_milestone_status(goal_data, "m1", "COMPLETED")
    assert update_res["success"] is True
    goal_data = update_res["goal_data"]
    assert goal_data["status"] == "IN_PROGRESS"

    # Next milestone
    next_m = ExecutiveAgent.get_next_milestone(goal_data)
    assert next_m["id"] == "m2"

    # Complete rest
    goal_data = ExecutiveAgent.update_milestone_status(goal_data, "m2", "COMPLETED")["goal_data"]
    goal_data = ExecutiveAgent.update_milestone_status(goal_data, "m3", "COMPLETED")["goal_data"]
    assert goal_data["status"] == "COMPLETED"
    assert ExecutiveAgent.get_next_milestone(goal_data) is None


def test_executive_node_decomposition_workflow(mock_env):
    state: AgentState = {
        "user_input": "Learn RF Engineering",
        "plan": None,
        "selected_agent": None,
        "logs": [],
        "result": None,
    }
    
    res = executive_node(state)
    assert res["selected_agent"] == "planner"
    assert res["user_input"] == "Research RF engineering core concepts and fundamentals"
    assert any("decomposed goal" in log for log in res["logs"])


def test_executive_node_pass_through(mock_env):
    state: AgentState = {
        "user_input": "read files in workspace",
        "plan": None,
        "selected_agent": None,
        "logs": [],
        "result": None,
    }
    res = executive_node(state)
    assert res["selected_agent"] is None
    assert res["user_input"] == "read files in workspace"
    assert "pass-through" in res["logs"][-1]


def test_executive_node_status_query(mock_env):
    # 1. First trigger decomposition to save goal to memory
    state_init: AgentState = {
        "user_input": "Learn RF Engineering",
        "plan": None,
        "selected_agent": None,
        "logs": [],
        "result": None,
    }
    executive_node(state_init)

    # Debug: query SQLite memory db directly
    from backend.core.human_memory import HumanMemoryStore
    conn = HumanMemoryStore._connect()
    rows = conn.execute("SELECT id, type, content, pending_approval FROM hm_memories").fetchall()
    print("DEBUG: hm_memories records:", [dict(r) for r in rows])

    # 2. Query status
    state_query: AgentState = {
        "user_input": "check goal status",
        "plan": None,
        "selected_agent": None,
        "logs": [],
        "result": None,
    }
    res = executive_node(state_query)
    print("DEBUG: status_query result:", res.get("result"))
    assert "Goal: Learn RF Engineering" in res["result"]
    assert "Overall Status: IN_PROGRESS" in res["result"]
    assert "Research RF engineering" in res["result"]


def test_capability_enforcement(mock_env, monkeypatch):
    # 1. Deny CAP_GOAL_MANAGE and try to decompose
    original_allowed = CapabilityRegistry.is_capability_allowed
    def mock_allowed(agent, capability):
        if agent == "executive" and capability == CAP_GOAL_MANAGE:
            return False
        return original_allowed(agent, capability)
    monkeypatch.setattr(CapabilityRegistry, "is_capability_allowed", mock_allowed)

    state: AgentState = {
        "user_input": "Learn RF Engineering",
        "plan": None,
        "selected_agent": None,
        "logs": [],
        "result": None,
    }
    res = executive_node(state)
    assert "Security Error" in res["result"]

    # 2. Deny CAP_GOAL_SCHEDULE and query status
    def mock_allowed_schedule(agent, capability):
        if agent == "executive" and capability == CAP_GOAL_SCHEDULE:
            return False
        return original_allowed(agent, capability)
    monkeypatch.setattr(CapabilityRegistry, "is_capability_allowed", mock_allowed_schedule)

    state_query: AgentState = {
        "user_input": "check goal status",
        "plan": None,
        "selected_agent": None,
        "logs": [],
        "result": None,
    }
    res_query = executive_node(state_query)
    assert "Security Error" in res_query["result"]
