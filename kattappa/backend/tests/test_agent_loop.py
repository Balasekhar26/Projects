import pytest
import os
import tempfile
from backend.core.memory.memory_store import MemoryStore
from backend.core.agent.observe import Observer
from backend.core.agent.reflector import Reflector
from backend.core.agent.learner import Learner
from backend.core.agent.coordinator import AgentLoopCoordinator
from backend.core.skills_runtime.skills_runtime_engine import SkillsRuntimeEngine

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_agent_loop_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    MemoryStore.clear_database()
    yield temp_dir
    MemoryStore.clear_database()

def test_observer_capturing() -> None:
    observer = Observer()
    state = observer.capture_world_state()
    
    assert "focused_application" in state
    assert state["active_elements_count"] == 2
    assert len(state["elements"]) == 2

def test_reflector_database_logging(test_db_setup) -> None:
    Reflector.reflect_on_outcome("goal_test", success=True, duration=1.5)
    
    # Assert database outcomes entry exists
    conn = MemoryStore._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM execution_outcomes WHERE task_id = ?", ("goal_test",))
    row = cursor.fetchone()
    
    assert row is not None
    assert row["success"] == 1
    assert row["actual_duration"] == 1.5

def test_learner_skill_extraction() -> None:
    engine = SkillsRuntimeEngine()
    learner = Learner(engine)
    
    sequence = [
        {"cmd": "click", "x": 10, "y": 10},
        {"cmd": "click", "x": 10, "y": 10}, # Redundant step to clean
        {"cmd": "type", "x": 50, "y": 50}
    ]
    
    skill = learner.learn_new_skill("open_notepad", sequence)
    assert skill is not None
    # Deduplicated sequence size should be 2
    assert len(skill.steps) == 2
    assert skill.steps[0]["cmd"] == "click"
    assert skill.steps[1]["cmd"] == "type"

def test_coordinator_execution_cycle(test_db_setup) -> None:
    coordinator = AgentLoopCoordinator()
    
    # Success steps
    steps_ok = [
        {"cmd": "echo done", "x": 100, "y": 100, "pre_snap": b"pre", "post_snap": b"post"}
    ]
    res_ok = coordinator.execute_goal_cycle("goal_1", "print text", steps_ok)
    assert res_ok == "SUCCESS"
    
    # Check that skill was registered dynamically
    learned = coordinator.skills_engine.registry.get_skill("print text")
    assert learned is not None
    
    # Failed step
    steps_fail = [
        {"cmd": "echo same", "x": 100, "y": 100, "pre_snap": b"pre", "post_snap": b"pre"} # Verification fails
    ]
    res_fail = coordinator.execute_goal_cycle("goal_2", "fail print", steps_fail)
    assert "FAILED" in res_fail
