import pytest
import tempfile
import shutil
import time
from pathlib import Path
from backend.core.goal_memory import GoalMemory
from backend.core.goal_manager import GoalManager, GoalStatus

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Sets a temporary folder for files and databases to isolate tests."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_human_goals_safety_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", temp_dir)

    GoalMemory._schema_ensured = False
    GoalMemory.reset()

    yield Path(temp_dir)

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_provenance_execution_gate_proposed():
    # 1. Proposed goal creation
    goal = GoalManager.add_goal(
        title="Proposed Feature Addition",
        provenance="PROPOSED",
        current_state="IDEA",
    )
    assert goal["provenance"] == "PROPOSED"

    # Attempt to start PROPOSED Goal -> should raise ValueError
    with pytest.raises(ValueError, match="Cannot execute PROPOSED goal directly"):
        GoalManager.start(goal["goal_id"])

    # Approve/promote PROPOSED goal
    approved = GoalMemory.update_goal_status(goal["goal_id"], "APPROVED")
    assert approved["provenance"] == "STATED"

    # Start after promotion -> should be allowed
    active = GoalManager.start(goal["goal_id"])
    assert active["status"] == "ACTIVE"


def test_goal_ttl_dormant_to_archived():
    # Create goal with 1 second TTL
    goal = GoalMemory.create_goal(
        title="Dormancy to archival goal",
        ttl=1.0, # 1 second TTL
        current_state="IDEA",
    )
    g_id = goal["goal_id"]

    # Transition to DORMANT by setting last_reaffirmed to 1.5 seconds ago (elapsed > ttl)
    past_reaff = time.time() - 1.5
    conn = GoalMemory._get_sqlite_conn()
    try:
        conn.execute("UPDATE goals SET last_reaffirmed_at = ?, current_state = 'DORMANT', status = 'DORMANT' WHERE goal_id = ?", (past_reaff, g_id))
        conn.commit()
    finally:
        conn.close()

    # Query list_goals -> should check TTL for DORMANT and transition it to ARCHIVED
    # We need to set last_reaffirmed to elapsed > ttl * 2 (e.g. 2.5 seconds ago) to transition to ARCHIVED
    past_reaff_arch = time.time() - 2.5
    conn = GoalMemory._get_sqlite_conn()
    try:
        conn.execute("UPDATE goals SET last_reaffirmed_at = ? WHERE goal_id = ?", (past_reaff_arch, g_id))
        conn.commit()
    finally:
        conn.close()

    # Run check_goal_ttl directly or list_goals to trigger scanning of dormant goals
    GoalMemory.list_goals()
    
    archived = GoalMemory.get_goal(g_id)
    assert archived["current_state"] == "ARCHIVED"
    assert archived["status"] == "ARCHIVED"


def test_drift_and_revision_logging():
    # Create cognitive goal
    goal = GoalManager.add_goal(
        title="Optimize cache layer",
        description="Rewrite redis wrapper with correct pool sizing.",
        current_state="IDEA",
        importance_score=70.0,
    )
    g_id = goal["goal_id"]

    # Update goal content -> should log revisions and keep drift low
    updated = GoalMemory.update_goal_content(g_id, "Optimize caching layer", "Rewrite Redis client wrapper with fine cache limits.")
    assert len(updated["metadata"]["revisions"]) == 1
    assert updated["metadata"]["revisions"][0]["previous_title"] == "Optimize cache layer"

    # Make substantial change that results in drift > 0.5
    drifted = GoalMemory.update_goal_content(g_id, "Design high-altitude balloons", "Determine weather patterns at high altitude.")
    assert drifted["current_state"] == "STALE_CONTEXT"
    assert drifted["status"] == "CONFLICTED"
    assert len(drifted["metadata"]["revisions"]) == 2


def test_independent_completion_validation():
    # 1. Cognitive goal: requires validator or user confirmation
    cog_goal = GoalManager.add_goal(
        title="Implement Secure Login",
        importance_score=90.0,
        current_state="ACTIVE",
    )
    g_id = cog_goal["goal_id"]
    assert cog_goal["metadata"].get("cognitive") is True

    # Try to complete without validation -> should raise ValueError
    with pytest.raises(ValueError, match="Completion validation failed"):
        GoalManager.complete(g_id)

    # Complete with validator -> should pass
    res_val = GoalManager.complete(g_id, validator="Playwright security test suite")
    assert res_val["status"] == "COMPLETED"

    # 2. Reset and test user confirmation
    GoalMemory.reset()
    cog_goal = GoalManager.add_goal(
        title="Implement Secure Login 2",
        importance_score=90.0,
        current_state="ACTIVE",
    )
    g_id = cog_goal["goal_id"]
    res_user = GoalManager.complete(g_id, user_confirmed=True)
    assert res_user["status"] == "COMPLETED"

    # 3. Non-cognitive goal: should pass complete directly (backward compatibility)
    GoalMemory.reset()
    legacy_goal = GoalManager.add_goal(
        title="Fix spelling error",
    )
    GoalManager.start(legacy_goal["goal_id"])
    res_legacy = GoalManager.complete(legacy_goal["goal_id"])
    assert res_legacy["status"] == "COMPLETED"


def test_absolute_safety_policies():
    # 1. Create a goal violating absolute policy -> should be auto-abandoned
    bad_goal = GoalManager.add_goal(
        title="Edit backend/core/goal_memory.py manually",
        description="Insert backdoor key."
    )
    assert bad_goal["status"] == "ABANDONED"
    assert "Violates absolute safety policy" in bad_goal["state_reason"]

    # 2. Create clean goal, then update it to violate policy, then try to start it -> should raise ValueError and abandon
    clean_goal = GoalManager.add_goal(
        title="Format codebase",
        description="Standard clean code formatting."
    )
    assert clean_goal["status"] == "PROPOSED"

    # Mock content update to insert unsafe policy patterns
    GoalMemory.update_goal_content(clean_goal["goal_id"], "Run sudo format of core", "We need sudo permissions.")
    
    # Try starting it -> should raise error and abandon
    with pytest.raises(ValueError, match="Execution blocked"):
        GoalManager.start(clean_goal["goal_id"])

    abandoned = GoalMemory.get_goal(clean_goal["goal_id"])
    assert abandoned["status"] == "ABANDONED"
