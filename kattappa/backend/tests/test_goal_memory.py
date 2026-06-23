import pytest
import tempfile
import shutil
from pathlib import Path
from backend.core.goal_memory import GoalMemory
from backend.core.goal_manager import GoalManager

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Sets a temporary folder for files and databases to isolate tests."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_goals_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", temp_dir)

    # Reset schema ensured flags to allow new sqlite dbs to initialize
    GoalMemory._schema_ensured = False
    GoalMemory.reset()

    yield Path(temp_dir)

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_create_and_get_goal():
    goal = GoalMemory.create_goal(
        title="Test Goal V1",
        description="Verify V1 goal model",
        priority="HIGH",
        target_date="2026-12-31",
        success_criteria=["Criterion 1", "Criterion 2"],
        owner="test_runner",
        metadata={"foo": "bar"}
    )
    
    assert goal is not None
    assert goal["goal_id"].startswith("goal_")
    assert goal["title"] == "Test Goal V1"
    assert goal["description"] == "Verify V1 goal model"
    assert goal["priority"] == "HIGH"
    assert goal["status"] == "PROPOSED"
    assert goal["target_date"] == "2026-12-31"
    assert goal["success_criteria"] == ["Criterion 1", "Criterion 2"]
    assert goal["owner"] == "test_runner"
    assert goal["metadata"] == {"foo": "bar"}
    assert goal["progress"] == 0.0
    assert len(goal["milestones"]) == 0
    assert len(goal["dependencies"]) == 0


def test_goal_milestones_and_derived_progress():
    goal = GoalMemory.create_goal("Test Progress Goal")
    goal_id = goal["goal_id"]

    milestones_list = [
        {"title": "M1: Setup", "weight": 1.0, "description": "First phase", "milestone_id": f"{goal_id}_m1"},
        {"title": "M2: Dev", "weight": 3.0, "description": "Second phase", "milestone_id": f"{goal_id}_m2"},
    ]
    GoalMemory.add_milestones(goal_id, milestones_list)

    # Goal should show milestones and progress=0.0
    updated = GoalMemory.get_goal(goal_id)
    assert len(updated["milestones"]) == 2
    assert updated["progress"] == 0.0

    # Complete M1
    GoalMemory.update_milestone(f"{goal_id}_m1", progress=1.0, status="COMPLETED")
    # Derived progress: (1.0 * 1.0 + 0.0 * 3.0) / 4.0 = 0.25
    updated = GoalMemory.get_goal(goal_id)
    assert updated["progress"] == 0.25

    # Complete M2
    GoalMemory.update_milestone(f"{goal_id}_m2", progress=1.0, status="COMPLETED")
    # Goal should be auto-completed to 1.0 progress and status COMPLETED (since status was PROPOSED / APPROVED / ACTIVE)
    updated = GoalMemory.get_goal(goal_id)
    # Wait, the autocomplete logic is:
    # all_milestones_done = len(mrows) > 0 and all(r["status"] == "COMPLETED" for r in mrows)
    # if all_milestones_done and current_status in {"APPROVED", "ACTIVE"}:
    # In this test, goal_status is 'PROPOSED', so it doesn't auto-complete status, but progress becomes 1.0.
    # Let's verify this.
    assert updated["progress"] == 1.0
    assert updated["status"] == "PROPOSED"

    # Now approve goal and start it, it should transition to ACTIVE
    GoalMemory.update_goal_status(goal_id, "APPROVED")
    GoalManager.start(goal_id)
    # Let's update milestone status again to trigger recalculate
    GoalMemory.update_milestone(f"{goal_id}_m2", status="COMPLETED")
    updated = GoalMemory.get_goal(goal_id)
    assert updated["status"] == "COMPLETED"


def test_goal_events_append_only():
    goal = GoalMemory.create_goal("Event Trail Goal")
    goal_id = goal["goal_id"]

    events = GoalMemory.get_events(goal_id)
    assert len(events) >= 1
    assert events[0]["event_type"] == "GOAL_CREATED"

    # Add milestones should log event
    GoalMemory.add_milestones(goal_id, [{"title": "Milestone A", "milestone_id": f"{goal_id}_ma"}])
    events = GoalMemory.get_events(goal_id)
    assert any(e["event_type"] == "MILESTONE_ADDED" for e in events)


def test_dependency_cycle_prevention():
    goal_a = GoalMemory.create_goal("Goal A")["goal_id"]
    goal_b = GoalMemory.create_goal("Goal B")["goal_id"]
    goal_c = GoalMemory.create_goal("Goal C")["goal_id"]

    # A -> B -> C
    GoalMemory.add_dependency(goal_a, goal_b)
    GoalMemory.add_dependency(goal_b, goal_c)

    # Adding C -> A should fail and raise cycle detection error
    with pytest.raises(ValueError, match="Dependency cycle detected!"):
        GoalMemory.add_dependency(goal_c, goal_a)

    # Check dependencies are recorded correctly
    assert GoalMemory.get_goal(goal_a)["dependencies"] == [goal_b]
    assert GoalMemory.get_goal(goal_b)["dependencies"] == [goal_c]
    assert GoalMemory.get_goal(goal_c)["dependencies"] == []
