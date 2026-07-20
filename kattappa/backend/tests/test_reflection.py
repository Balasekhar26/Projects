import pytest
import os
import tempfile
from backend.agents.planner import TaskGraph, TaskStep
from backend.core.memory.memory_store import MemoryStore
from backend.core.reflection.reflection_engine import ReflectionEngine

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_reflection_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    MemoryStore.clear_database()
    yield temp_dir
    MemoryStore.clear_database()

def test_reflection_table_storage() -> None:
    MemoryStore.add_reflection(
        goal="Test manual goals",
        task_id="g-101",
        task_type="local_agent",
        outcome="FAILED",
        success=0,
        retries=1,
        confidence_score=0.85,
        failure_reason="Step s1 failed",
        recovery_strategy="FAILSAFE",
        lesson_learned="Avoid unverified dependency upgrades.",
        execution_time_ms=500
    )
    
    reflections = MemoryStore.get_all_reflections()
    assert len(reflections) == 1
    assert reflections[0]["goal"] == "Test manual goals"
    assert reflections[0]["outcome"] == "FAILED"
    assert reflections[0]["success"] == 0
    assert reflections[0]["confidence_score"] == 0.85

def test_reflection_successful_task() -> None:
    graph = TaskGraph("Clean database workspace")
    step = TaskStep(
        step_id="clean_step",
        description="Run clean script",
        agent="coder",
        action="RUN_SHELL",
        params={"command": "python clean.py"},
        dependencies=[]
    )
    graph.add_step(step)
    
    result = ReflectionEngine.reflect_on_task(graph)
    assert result["status"] == "COMPLETED"
    assert result["confidence_rating"] == 1.0  # Base 1.0 + Ver auto 0.05 = 1.05, clamped to 1.0
    assert "verified successfully" in result["lessons_learned"]

def test_reflection_failed_task_and_score() -> None:
    graph = TaskGraph("Upgrade virtual env dependencies")
    step = TaskStep(
        step_id="pip_step",
        description="Run pip upgrade",
        agent="coder",
        action="RUN_SHELL",
        params={"command": "pip install --upgrade scipy", "simulated_failure": True},
        dependencies=[]
    )
    graph.add_step(step)
    
    result = ReflectionEngine.reflect_on_task(graph)
    assert result["status"] == "FAILED"
    # Base 0.10 + Risk Low 0.00 + Ver auto 0.05 = 0.15
    assert result["confidence_rating"] == 0.15
    assert len(result["failures_observed"]) == 1

def test_procedural_memory_promotion_threshold() -> None:
    goal = "Deploy FastAPI web app"
    
    # Execution 1
    g1 = TaskGraph(goal)
    g1.add_step(TaskStep("s1", "Init server", "coder", "RUN_SHELL", {}, []))
    res1 = ReflectionEngine.reflect_on_task(g1)
    assert res1["confidence_rating"] == 1.0
    
    # Execution 2
    g2 = TaskGraph(goal)
    g2.add_step(TaskStep("s1", "Init server", "coder", "RUN_SHELL", {}, []))
    ReflectionEngine.reflect_on_task(g2)
    
    # Execution 3 (This third execution hits success_count >= 3 threshold)
    g3 = TaskGraph(goal)
    g3.add_step(TaskStep("s1", "Init server", "coder", "RUN_SHELL", {}, []))
    res3 = ReflectionEngine.reflect_on_task(g3)
    
    # Verify procedural memory is promoted
    memories = MemoryStore.get_all_memories()
    procedural = [m for m in memories if m["type"] == "procedural"]
    assert len(procedural) == 1
    assert "Procedural Lesson (Verified Habit):" in procedural[0]["content"]
