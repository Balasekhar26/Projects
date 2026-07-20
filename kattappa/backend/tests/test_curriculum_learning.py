import pytest
import tempfile
from backend.core.memory.memory_store import MemoryStore
from backend.core.curriculum.performance_analyzer import PerformanceAnalyzer
from backend.core.curriculum.curriculum_planner import CurriculumPlanner
from backend.core.curriculum.learning_scheduler import LearningScheduler
from backend.core.curriculum.curriculum_learning_engine import CurriculumLearningEngine

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_curriculum_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    MemoryStore.clear_database()
    
    # Create required execution outcomes schema manually for test mocks
    conn = MemoryStore._get_conn()
    with MemoryStore._lock:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS execution_outcomes (
                task_id TEXT,
                success INTEGER
            )
        """)
        conn.commit()
        
    yield temp_dir
    MemoryStore.clear_database()

def test_performance_analyzer_flags_weaknesses() -> None:
    conn = MemoryStore._get_conn()
    with MemoryStore._lock:
        # skill_a: 2 runs, 2 failures -> 100% failure rate
        conn.execute("INSERT INTO execution_outcomes (task_id, success) VALUES ('skill_a', 0)")
        conn.execute("INSERT INTO execution_outcomes (task_id, success) VALUES ('skill_a', 0)")
        # skill_b: 3 runs, 3 successes -> 0% failure rate
        conn.execute("INSERT INTO execution_outcomes (task_id, success) VALUES ('skill_b', 1)")
        conn.execute("INSERT INTO execution_outcomes (task_id, success) VALUES ('skill_b', 1)")
        conn.execute("INSERT INTO execution_outcomes (task_id, success) VALUES ('skill_b', 1)")
        conn.commit()
        
    weak = PerformanceAnalyzer.identify_weak_skills(failure_threshold=0.15)
    assert "skill_a" in weak
    assert "skill_b" not in weak

def test_curriculum_planner_exercise_creation() -> None:
    exercises = CurriculumPlanner.generate_curriculum(["skill_a", "skill_c"])
    assert len(exercises) == 2
    assert exercises[0]["skill_id"] == "skill_a"
    assert exercises[0]["exercise_name"] == "rehearse_skill_a"

def test_learning_scheduler_telemetry() -> None:
    # System is busy -> do not run
    assert not LearningScheduler.is_system_idle({"cpu_percent": 80.0, "memory_percent": 30.0})
    # System is idle -> run
    assert LearningScheduler.is_system_idle({"cpu_percent": 10.0, "memory_percent": 40.0})

def test_curriculum_engine_orchestration(test_db_setup) -> None:
    conn = MemoryStore._get_conn()
    with MemoryStore._lock:
        conn.execute("INSERT INTO execution_outcomes (task_id, success) VALUES ('skill_d', 0)")
        conn.commit()
        
    engine = CurriculumLearningEngine()
    
    # 1. System busy -> should return empty curriculum list
    curriculum_busy = engine.trigger_curriculum_cycles(
        system_telemetry={"cpu_percent": 90.0, "memory_percent": 40.0}
    )
    assert len(curriculum_busy) == 0
    
    # 2. System idle -> should return curriculum targeting skill_d
    curriculum_idle = engine.trigger_curriculum_cycles(
        system_telemetry={"cpu_percent": 5.0, "memory_percent": 10.0}
    )
    assert len(curriculum_idle) == 1
    assert curriculum_idle[0]["skill_id"] == "skill_d"
