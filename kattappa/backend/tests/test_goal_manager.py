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


def test_goal_dependency_autounblock():
    # 1. Goal A
    goal_a = GoalManager.add_goal("Independent A")
    a_id = goal_a["goal_id"]

    # 2. Goal B depends on A
    goal_b = GoalManager.add_goal("Dependent B", depends_on=[a_id])
    b_id = goal_b["goal_id"]

    # Start B -> Blocks
    GoalManager.start(b_id)
    assert GoalManager.get(b_id)["status"] == GoalStatus.BLOCKED.value

    # Start and complete A -> Auto-unblocks B
    GoalManager.start(a_id)
    GoalManager.complete(a_id)

    # Status of B should automatically become ACTIVE
    assert GoalManager.get(b_id)["status"] == GoalStatus.ACTIVE.value


def test_goal_suspension_and_resume():
    from backend.core.executive_workspace import WORKSPACE
    # Clean workspace
    WORKSPACE.reset_workspace()

    # Create goal with snapshot capability
    goal = GoalManager.add_goal("Suspendable task")
    g_id = goal["goal_id"]

    # Write something to workspace registers and scratchpad
    WORKSPACE.write_scratchpad("curr_task", "eval_expr")
    WORKSPACE.push_reasoning("step 1: parse")
    WORKSPACE.set_register("reg_a", 42)

    # Suspend goal
    GoalManager.suspend(g_id, "Resource contention")
    
    suspended_goal = GoalManager.get(g_id)
    assert suspended_goal["status"] == GoalStatus.WAITING.value
    assert suspended_goal["workspace_snapshot_json"] is not None

    # Clear current workspace
    WORKSPACE.reset_workspace()
    assert WORKSPACE.read_scratchpad("curr_task") is None

    # Resume goal
    GoalManager.resume(g_id, "Resources free")
    assert GoalManager.get(g_id)["status"] == GoalStatus.ACTIVE.value

    # Workspace should be restored
    assert WORKSPACE.read_scratchpad("curr_task") == "eval_expr"
    assert WORKSPACE.get_register("reg_a") == 42
    assert WORKSPACE.pop_reasoning() == "step 1: parse"


def test_goal_retry_backoff():
    # Create goal with max_retries = 2
    goal = GoalManager.add_goal("Retryable Task", max_retries=2)
    g_id = goal["goal_id"]

    # Verify initial retry count
    assert goal["retry_count"] == 0
    assert goal["max_retries"] == 2

    # First Failure -> Retries not exhausted -> Transitions to WAITING (waiting for backoff)
    res = GoalManager.fail(g_id, "Network timeout")
    assert res["status"] == GoalStatus.WAITING.value
    assert res["retry_count"] == 1
    assert res["backoff_delay_sec"] == 2.0

    # Second Failure -> Retries not exhausted -> Transitions to WAITING
    res = GoalManager.fail(g_id, "DB timeout")
    assert res["status"] == GoalStatus.WAITING.value
    assert res["retry_count"] == 2
    assert res["backoff_delay_sec"] == 4.0

    # Third Failure -> Retries exhausted -> Transitions to FAILED
    res = GoalManager.fail(g_id, "Fatal crash")
    assert res["status"] == GoalStatus.FAILED.value
    assert res["retry_count"] == 2  # remains at max

