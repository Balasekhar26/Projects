import pytest
import tempfile
import shutil
from pathlib import Path
from backend.core.goal_memory import GoalMemory
from backend.core.goal_manager import GoalManager, GoalStatus

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Sets a temporary folder for files and databases to isolate tests."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_goal_mgr_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", temp_dir)

    GoalMemory._schema_ensured = False
    GoalMemory.reset()

    yield Path(temp_dir)

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_goal_manager_crud_and_status():
    # 1. Create a parent goal
    parent = GoalManager.add_goal(
        title="Main Mission",
        description="Root goal",
        priority="HIGH"
    )
    p_id = parent["goal_id"]

    # 2. Create subgoals
    sub1 = GoalManager.add_goal(title="Sub-task 1", parent_id=p_id)
    sub2 = GoalManager.add_goal(title="Sub-task 2", parent_id=p_id)

    assert sub1["metadata"]["parent_id"] == p_id
    assert sub2["metadata"]["parent_id"] == p_id

    subgoals = GoalManager.subgoals(p_id)
    assert len(subgoals) == 2
    assert {s["goal_id"] for s in subgoals} == {sub1["goal_id"], sub2["goal_id"]}


def test_goal_lifecycle_blocking_by_dependencies():
    # 1. Goal A (independent)
    goal_a = GoalManager.add_goal("Independent Goal")
    a_id = goal_a["goal_id"]

    # 2. Goal B (dependent on A)
    goal_b = GoalManager.add_goal("Dependent Goal", depends_on=[a_id])
    b_id = goal_b["goal_id"]

    # Try starting B - it should become BLOCKED because A is not completed
    started_b = GoalManager.start(b_id)
    assert started_b["status"] == GoalStatus.BLOCKED.value

    # Start and complete A
    GoalManager.start(a_id)
    GoalManager.complete(a_id)

    # Start B again - it should now become ACTIVE since A is completed
    started_b_now = GoalManager.start(b_id)
    assert started_b_now["status"] == GoalStatus.ACTIVE.value


def test_goal_manager_aggregates():
    goal_a = GoalManager.add_goal("Goal A")
    goal_b = GoalManager.add_goal("Goal B")
    
    stats = GoalManager.status()
    assert stats["total_goals"] == 2
    assert stats["by_status"][GoalStatus.PROPOSED.value] == 2

    GoalManager.start(goal_a["goal_id"])
    stats = GoalManager.status()
    assert stats["by_status"][GoalStatus.ACTIVE.value] == 1
    assert stats["by_status"][GoalStatus.PROPOSED.value] == 1


def test_goal_manager_retry_and_rollback():
    # 1. Create a goal with rollback_action in metadata
    goal = GoalManager.add_goal(
        title="Flaky Operation Goal",
        description="Fails occasionally",
        priority="MEDIUM"
    )
    g_id = goal["goal_id"]
    
    # Add rollback info to metadata
    meta = goal["metadata"]
    meta["rollback_action"] = "revert_db_changes"
    GoalMemory.update_goal_metadata(g_id, meta)
    
    # 2. Trigger first step failure (Attempt 1)
    updated = GoalManager.handle_step_failure(g_id, "connection timeout", max_retries=2)
    assert updated["status"] == GoalStatus.ACTIVE.value
    assert updated["metadata"]["retry_attempts"] == 1
    
    # 3. Trigger second step failure (Attempt 2)
    updated = GoalManager.handle_step_failure(g_id, "connection timeout", max_retries=2)
    assert updated["status"] == GoalStatus.ACTIVE.value
    assert updated["metadata"]["retry_attempts"] == 2

    # 4. Trigger third step failure (Exceeds max_retries=2) -> should fail and trigger rollback
    updated = GoalManager.handle_step_failure(g_id, "connection timeout", max_retries=2)
    assert updated["status"] == GoalStatus.FAILED.value
    assert "Triggered rollback: revert_db_changes" in updated["state_reason"]
    assert updated["metadata"]["rollback_executed"] is True

