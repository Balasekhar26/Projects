import pytest
import tempfile
import shutil
from pathlib import Path
from backend.core.goal_memory import GoalMemory
from backend.core.goal_manager import GoalManager
from backend.agents.executive import ExecutiveAgent, executive_node
from backend.core.state import AgentState

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Sets a temporary folder for files and databases to isolate tests."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_priority_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", temp_dir)

    GoalMemory._schema_ensured = False
    GoalMemory.reset()

    yield Path(temp_dir)

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_priority_score_math():
    # Formula: Score = (I * U * A * Success_Prob) / Cost
    # Goal 1: I=8, U=7, A=9, Cost=4 -> (8 * 7 * 9 * 1.0) / 4 = 126.0
    g1 = GoalMemory.create_goal(
        title="High Priority Goal",
        importance=8.0,
        urgency=7.0,
        strategic_alignment=9.0,
        resource_cost=4.0
    )
    assert g1["priority_score"] == 126.0

    # Goal 2: I=2, U=2, A=2, Cost=8 -> (2 * 2 * 2 * 1.0) / 8 = 1.0
    g2 = GoalMemory.create_goal(
        title="Low Priority Goal",
        importance=2.0,
        urgency=2.0,
        strategic_alignment=2.0,
        resource_cost=8.0
    )
    assert g2["priority_score"] == 1.0


def test_milestone_success_prob_affects_priority():
    # Goal: I=10, U=10, A=10, Cost=2 -> Initial (10 * 10 * 10 * 1.0) / 2 = 500.0
    goal = GoalMemory.create_goal(
        title="Simulation Goal",
        importance=10.0,
        urgency=10.0,
        strategic_alignment=10.0,
        resource_cost=2.0
    )
    g_id = goal["goal_id"]
    assert goal["priority_score"] == 500.0

    # Add milestones
    m_list = [
        {"title": "M1", "milestone_id": f"{g_id}_m1"},
        {"title": "M2", "milestone_id": f"{g_id}_m2"},
    ]
    GoalMemory.add_milestones(g_id, m_list)
    
    # Success probability defaults to 1.0 initially
    assert GoalMemory.get_goal(g_id)["priority_score"] == 500.0

    # Update milestone 1 to 0.8 and milestone 2 to 0.6 success probability (Average = 0.7)
    # Score should become: (10 * 10 * 10 * 0.7) / 2 = 350.0
    GoalMemory.update_milestone(f"{g_id}_m1", success_probability=0.8)
    GoalMemory.update_milestone(f"{g_id}_m2", success_probability=0.6)

    updated = GoalMemory.get_goal(g_id)
    assert updated["priority_score"] == 350.0


def test_list_goals_sorted_by_priority():
    GoalMemory.create_goal("Medium Goal", importance=5, urgency=5, strategic_alignment=5, resource_cost=5) # Score = 25
    GoalMemory.create_goal("High Goal", importance=8, urgency=8, strategic_alignment=8, resource_cost=2)   # Score = 256
    GoalMemory.create_goal("Low Goal", importance=2, urgency=2, strategic_alignment=2, resource_cost=8)    # Score = 1

    sorted_list = GoalManager.list_goals()
    assert len(sorted_list) == 3
    assert sorted_list[0]["title"] == "High Goal"
    assert sorted_list[1]["title"] == "Medium Goal"
    assert sorted_list[2]["title"] == "Low Goal"


def test_executive_node_priority_milestone_selection():
    # 1. Create a high priority goal (Score = 200)
    g_high = GoalManager.add_goal("Build Drone Jammer", importance=10, urgency=10, strategic_alignment=4, resource_cost=2)
    GoalMemory.add_milestones(g_high["goal_id"], [{"title": "Setup chip", "milestone_id": f"{g_high['goal_id']}_m1"}])
    GoalManager.start(g_high["goal_id"])

    # 2. Create a lower priority goal (Score = 2.5)
    g_low = GoalManager.add_goal("Format system logs", importance=2, urgency=2, strategic_alignment=2, resource_cost=3.2)
    GoalMemory.add_milestones(g_low["goal_id"], [{"title": "Regex search logs", "milestone_id": f"{g_low['goal_id']}_m1"}])
    GoalManager.start(g_low["goal_id"])

    # Trigger next milestone execution query
    state: AgentState = {
        "user_input": "execute next milestone",
        "plan": None,
        "selected_agent": None,
        "logs": [],
        "result": None,
    }

    res = executive_node(state)
    
    # It must select the milestone of "Build Drone Jammer" (highest priority) over "Format system logs"
    assert res["selected_agent"] == "planner"
    assert res["user_input"] == "Setup chip"
    assert any("Build Drone Jammer" in log for log in res["logs"])
