import pytest
import tempfile
import shutil
import time
from pathlib import Path

from backend.core.goal_memory import GoalMemory
from backend.core.goal_manager import GoalManager
from backend.core.project_memory import ProjectMemory
from backend.core.personal_project_manager import PersonalProjectManager


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Sets a temporary folder for files and databases to isolate tests."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_ppm_tests_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", temp_dir)

    GoalMemory._schema_ensured = False
    ProjectMemory._schema_ensured = False
    GoalMemory.reset()
    ProjectMemory.reset()

    yield Path(temp_dir)

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_goal_coupling_and_creation_safety():
    # 1. Create originating goal
    goal = GoalManager.add_goal(
        title="PPM Goal",
        importance_score=80.0,
        current_state="IDEA"
    )
    g_id = goal["goal_id"]

    # 2. Create project linked to goal -> should succeed
    proj = PersonalProjectManager.create_project(
        linked_goal_id=g_id,
        title="Execution of PPM Goal",
        description="PPM container test",
        target_finish_date=time.time() + 86400,
        original_scope="Complete PPM Integration Task"
    )
    assert proj["title"] == "Execution of PPM Goal"
    assert proj["linked_goal_id"] == g_id
    assert proj["health_status"] in {"GOOD", "EXCELLENT"}
    assert proj["status"] == "PROPOSED"
    assert proj["scope"]["original_scope"] == "Complete PPM Integration Task"

    # 3. Create second project linked to same goal -> should fail (coupling constraint)
    with pytest.raises(ValueError, match="already linked"):
        PersonalProjectManager.create_project(linked_goal_id=g_id)

    # 4. Create project with invalid goal -> should fail (Zero self-creation)
    with pytest.raises(ValueError, match="does not exist"):
        PersonalProjectManager.create_project(linked_goal_id="invalid_id")


def test_zombie_project_state_sync():
    # Create goal & project
    goal = GoalManager.add_goal(title="Neglected Goal", current_state="IDEA")
    g_id = goal["goal_id"]
    proj = PersonalProjectManager.create_project(linked_goal_id=g_id)
    p_id = proj["project_id"]

    # Retrieve project initially -> status matches
    assert proj["status"] == "PROPOSED"

    # Transition goal to DORMANT
    GoalMemory.update_goal_status(g_id, "DORMANT", "Neglect decay")

    # Get project -> should automatically synchronize zombie state to DORMANT
    retrieved = PersonalProjectManager.get_project(p_id)
    assert retrieved["status"] == "DORMANT"


def test_endless_replanning_limit():
    # Create goal & project
    goal = GoalManager.add_goal(title="Fickle Initiative", current_state="IDEA")
    proj = PersonalProjectManager.create_project(linked_goal_id=goal["goal_id"])
    p_id = proj["project_id"]

    # Replan 1 -> OK
    PersonalProjectManager.log_revision(p_id, "Developer", "Changed scope slightly")
    p1 = PersonalProjectManager.get_project(p_id)
    assert p1["status"] == "PROPOSED"
    assert len(p1["revisions"]) == 1

    # Replan 2 -> OK
    PersonalProjectManager.log_revision(p_id, "Developer", "Changed scope again")
    
    # Replan 3 -> Limit hit (limit is 3), transitions to STUCK
    PersonalProjectManager.log_revision(p_id, "Developer", "Constant scope shifting")
    p3 = PersonalProjectManager.get_project(p_id)
    assert p3["status"] == "STUCK"
    assert p3["health_status"] == "CRITICAL"


def test_completion_validation_gate():
    # Create goal & project
    goal = GoalManager.add_goal(title="Verifiable Goal", current_state="ACTIVE")
    proj = PersonalProjectManager.create_project(linked_goal_id=goal["goal_id"], status="ACTIVE")
    p_id = proj["project_id"]

    # Try to complete project without validator or user confirmation -> should raise ValueError
    with pytest.raises(ValueError, match="independent validator or user confirmation"):
        PersonalProjectManager.complete_project(p_id)

    # Complete with independent validator -> should succeed
    res = PersonalProjectManager.complete_project(p_id, validator="PPM Integration Pytest Suite")
    assert res["status"] == "COMPLETED"

    # Verify that completion propagated to the linked goal system
    linked_goal = GoalManager.get(goal["goal_id"])
    assert linked_goal["status"] == "COMPLETED"


def test_resource_engine_limits():
    # Create goal & project
    goal = GoalManager.add_goal(title="Heavy Compute Goal", current_state="IDEA")
    proj = PersonalProjectManager.create_project(linked_goal_id=goal["goal_id"])
    p_id = proj["project_id"]

    # Allocate computecores
    PersonalProjectManager.allocate_resource(p_id, "COMPUTE_CORES", 10.0)
    
    # Consume 4 cores -> should pass
    c1 = PersonalProjectManager.consume_resource(p_id, "COMPUTE_CORES", 4.0)
    assert c1["remaining_amount"] == 6.0

    # Consume 7 cores -> should raise ValueError (resource exhaustion validation)
    with pytest.raises(ValueError, match="Resource exhaustion"):
        PersonalProjectManager.consume_resource(p_id, "COMPUTE_CORES", 7.0)


def test_health_evaluation_and_blockers():
    # Create goal & project
    goal = GoalManager.add_goal(title="Blocked Project Goal", current_state="IDEA")
    proj = PersonalProjectManager.create_project(linked_goal_id=goal["goal_id"])
    p_id = proj["project_id"]

    # Initial health -> should be GOOD or EXCELLENT
    p1 = PersonalProjectManager.get_project(p_id)
    assert p1["health_status"] in {"GOOD", "EXCELLENT"}

    # Raise active BLOCKING blocker
    blocker = PersonalProjectManager.add_blocker(p_id, severity="BLOCKING", source="Missing compiler toolchain")
    
    # Retrieve project -> health should degrade to CRITICAL
    p2 = PersonalProjectManager.get_project(p_id)
    assert p2["health_status"] == "CRITICAL"

    # Resolve blocker
    PersonalProjectManager.resolve_blocker(blocker["blocker_id"])
    
    # Health should restore
    p3 = PersonalProjectManager.get_project(p_id)
    assert p3["health_status"] in {"GOOD", "EXCELLENT"}


def test_reflection_and_memory_logging():
    # Create goal & project
    goal = GoalManager.add_goal(title="Reflective Goal", current_state="IDEA")
    proj = PersonalProjectManager.create_project(linked_goal_id=goal["goal_id"])
    p_id = proj["project_id"]

    # Log choices & lessons
    PersonalProjectManager.log_decision(p_id, "SQLite for local memory store", "Low concurrency, simple file management is optimal.")
    PersonalProjectManager.log_lesson(p_id, "Verify schema constraints on startup.")

    # Run reflection report
    report = PersonalProjectManager.reflect_on_project(p_id)
    assert "insights" in report
    assert len(report["insights"]) > 0

    # Verify memory contains logs
    retrieved = PersonalProjectManager.get_project(p_id)
    assert len(retrieved["memory"]) == 3 # Decision, Lesson, Reflection report
