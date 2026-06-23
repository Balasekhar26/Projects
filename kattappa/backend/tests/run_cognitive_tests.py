from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

# Adjust path to import backend modules
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.core.config import BackendConfig

# Set up test workspace paths
TEST_DIR = ROOT / "test_run_workspace"
TEST_DIR.mkdir(parents=True, exist_ok=True)
TEST_DB = TEST_DIR / "kattappa_test.db"
TEST_WEIGHTS = TEST_DIR / "simulation_calibration_weights.json"

# Create test config directly to avoid calling load_config() and executing sysctl hardware profiling
test_config = BackendConfig(
    root=ROOT,
    backend_root=ROOT / "backend",
    ollama_host="http://127.0.0.1:11434",
    model_map={
        "fast": "qwen2.5:0.5b",
        "general": "qwen3:4b",
        "coder": "qwen2.5-coder:3b",
        "power": "qwen3:4b",
        "vision": "disabled",
        "reasoning": "disabled",
    },
    chroma_path=TEST_DIR / "chroma",
    sqlite_path=TEST_DB,
    memory_collection="kattappa_memory",
    shell_enabled=False,
    desktop_enabled=True,
    screen_capture_enabled=False,
    guidance_overlay_enabled=True,
    teach_mode_enabled=True,
    screenshots_dir=TEST_DIR / "screenshots",
    audio_dir=TEST_DIR / "audio",
    logs_dir=TEST_DIR / "logs",
    workspace_dir=ROOT / "workspace",
    hardware_profile="BALANCED",
    context_budget=4096,
)

# Apply global monkeypatches BEFORE importing any other modules
import backend.core.config
backend.core.config.load_config = lambda: test_config

# Now import the modules safely
from backend.core.workflow_memory import WorkflowMemory
from backend.core.simulation_calibration import SimulationCalibrator
from backend.core.knowledge_graph import KnowledgeGraph
from backend.core.skill_graph import SkillGraph
from backend.core.curriculum_engine import CurriculumEngine
from backend.core.project_manager import ProjectManager
from backend.core.long_term_goal_engine import LongTermGoalEngine
from backend.core.simulation_engine import SimulationEngine, PlanStep

# Mock weights path
backend.core.simulation_calibration.runtime_data_root = lambda: TEST_DIR


# Helper to clean up database
def clean_db():
    if TEST_DB.exists():
        try:
            TEST_DB.unlink()
        except Exception:
            pass
    if TEST_WEIGHTS.exists():
        try:
            TEST_WEIGHTS.unlink()
        except Exception:
            pass
    
    # Reset schema caching flags
    WorkflowMemory._schema_ensured = False
    SimulationCalibrator._schema_ensured = False
    KnowledgeGraph._schema_ensured = False
    SkillGraph._schema_ensured = False
    CurriculumEngine._schema_ensured = False
    ProjectManager._schema_ensured = False
    LongTermGoalEngine._schema_ensured = False


def test_workflow_memory():
    clean_db()
    
    # 1. save and retrieve
    steps = [
        {"agent": "coder", "action": "WRITE_FILE", "success": True, "duration_ms": 1200},
        {"agent": "coder", "action": "RUN_TESTS", "success": False, "duration_ms": 5000, "rollback_executed": True, "rollback_success": True},
    ]
    WorkflowMemory.save_workflow_run(
        workflow_id="wf_123",
        goal="Compile the code",
        status="completed",
        success=True,
        total_duration_ms=6200,
        steps=steps,
    )
    
    run = WorkflowMemory.get_workflow_run("wf_123")
    assert run is not None
    assert run["goal"] == "Compile the code"
    assert run["success"] is True
    assert len(run["steps"]) == 2
    assert run["steps"][1]["rollback_success"] is True

    # 2. nonexistent
    assert WorkflowMemory.get_workflow_run("wf_nonexistent") is None

    # 3. search
    WorkflowMemory.save_workflow_run(
        workflow_id="wf_search_1",
        goal="Deploy static website",
        status="completed",
        success=True,
        total_duration_ms=100,
        steps=[],
    )
    results = WorkflowMemory.search_workflows_by_goal("static")
    assert len(results) == 1
    assert results[0]["workflow_id"] == "wf_search_1"

    # 4. recent
    recent = WorkflowMemory.get_recent_workflow_runs(limit=5)
    assert len(recent) > 0


def test_simulation_calibration():
    clean_db()
    SimulationCalibrator._cached_weights = {}

    # Record calibration records
    SimulationCalibrator.record_prediction_outcome(
        agent="coder",
        action="RUN_TESTS",
        predicted_success=0.8,
        actual_success=False,
        predicted_duration_ms=1000,
        actual_duration_ms=2000,
        predicted_rollback=0.1,
        actual_rollback=True,
    )
    SimulationCalibrator.record_prediction_outcome(
        agent="coder",
        action="RUN_TESTS",
        predicted_success=0.8,
        actual_success=True,
        predicted_duration_ms=1000,
        actual_duration_ms=2000,
        predicted_rollback=0.1,
        actual_rollback=False,
    )

    report = SimulationCalibrator.recalibrate()
    assert report["status"] == "success"
    assert report["count"] == 2
    
    weights = SimulationCalibrator.get_all_weights()
    assert "coder:RUN_TESTS" in weights
    assert weights["coder:RUN_TESTS"]["success_factor"] == 0.625

    # Test integration in SimulationEngine
    step = PlanStep(step_id="step_test", agent="coder", action="RUN_TESTS")
    prediction, _, _ = SimulationEngine._predict_step(
        step,
        active_policies=[],
        reflection_agent_stats={},
        reflection_recommendations=[],
        context={},
    )
    # Scaled duration should be 10000ms (5000ms default * 2.0 duration_factor)
    assert prediction.expected_duration_ms == 10000


def test_knowledge_graph():
    clean_db()

    KnowledgeGraph.add_node("agent_coder", "agent", {"name": "Kattappa Coder"})
    KnowledgeGraph.add_node("tool_write", "tool", {"name": "Write File"})
    
    node = KnowledgeGraph.get_node("agent_coder")
    assert node is not None
    assert node["properties"]["name"] == "Kattappa Coder"

    KnowledgeGraph.add_edge("agent_coder", "tool_write", "USES")
    neighbors = KnowledgeGraph.query_neighbors("agent_coder", direction="out")
    assert len(neighbors) == 1
    assert neighbors[0]["node_id"] == "tool_write"

    # BFS pathfinding
    KnowledgeGraph.add_node("A", "concept")
    KnowledgeGraph.add_node("B", "concept")
    KnowledgeGraph.add_node("C", "concept")
    KnowledgeGraph.add_edge("A", "B", "LINK")
    KnowledgeGraph.add_edge("B", "C", "LINK")
    
    path = KnowledgeGraph.find_shortest_path("A", "C")
    assert path == ["A", "B", "C"]


def test_skill_graph():
    clean_db()

    SkillGraph.register_skill(
        skill_id="setup_env",
        name="Setup Env",
        description="Prepares virtual env",
        tools=["create_directory", "write_file"],
        agents=["coder"],
    )
    SkillGraph.register_skill(
        skill_id="run_test",
        name="Run Tests",
        description="Executes test runner",
        tools=["execute_command"],
        agents=["coder"],
        prerequisites=["setup_env"],
    )

    details = SkillGraph.get_skill_details("run_test")
    assert details is not None
    assert "execute_command" in details["tools"]

    deps = SkillGraph.get_skill_dependencies("run_test")
    assert deps == ["setup_env", "run_test"]


def test_curriculum_engine():
    clean_db()

    CurriculumEngine.add_challenge(
        challenge_id="ch_code_1",
        category="coding",
        title="Speed Compile",
        description="Compile within 2 seconds",
        success_criteria={"max_duration_ms": 2000, "min_success_rate": 0.8},
    )

    challenges = CurriculumEngine.list_challenges(category="coding")
    assert len(challenges) == 1
    assert challenges[0]["status"] == "pending"

    status = CurriculumEngine.update_challenge_attempt(
        challenge_id="ch_code_1",
        run_success=True,
        metrics={"duration_ms": 1500, "success_rate": 0.85},
    )
    assert status == "passed"


def test_project_manager():
    clean_db()

    ProjectManager.create_project_task(
        task_id="task_parent",
        project_name="suit_upgrade",
        title="Analyze thrusters",
        assigned_agent="researcher",
        dependencies=[],
    )
    ProjectManager.create_project_task(
        task_id="task_child",
        project_name="suit_upgrade",
        title="Calibrate alignment",
        assigned_agent="coder",
        dependencies=["task_parent"],
    )

    tasks = ProjectManager.get_project_tasks("suit_upgrade")
    by_id = {t["task_id"]: t for t in tasks}
    assert by_id["task_parent"]["status"] == "ready"
    assert by_id["task_child"]["status"] == "blocked"

    ProjectManager.update_task_state("task_parent", "completed")
    
    tasks_after = ProjectManager.get_project_tasks("suit_upgrade")
    by_id_after = {t["task_id"]: t for t in tasks_after}
    assert by_id_after["task_child"]["status"] == "ready"

    # Blackboard check
    ProjectManager.write_to_blackboard("suit_upgrade", "thruster_level", 95.5)
    assert ProjectManager.read_from_blackboard("suit_upgrade", "thruster_level") == 95.5


def test_long_term_goal_engine():
    clean_db()

    LongTermGoalEngine.register_goal(
        goal_id="goal_parent",
        title="Establish Colony",
        description="Establish baseline colony",
        preconditions={"colony_ready": True},
        success_criteria={"file_exists": "colony_config.json"},
    )
    LongTermGoalEngine.register_goal(
        goal_id="goal_child",
        title="Setup Communications",
        description="Configure radio satellites",
        parent_id="goal_parent",
    )

    tree = LongTermGoalEngine.get_goal_hierarchy()
    assert len(tree) == 1
    assert tree[0]["children"][0]["goal_id"] == "goal_child"

    assert LongTermGoalEngine.evaluate_preconditions("goal_parent", {"colony_ready": True}) is True
    assert LongTermGoalEngine.evaluate_preconditions("goal_parent", {"colony_ready": False}) is False


if __name__ == "__main__":
    tests = [
        ("Workflow Memory", test_workflow_memory),
        ("Simulation Calibration", test_simulation_calibration),
        ("Knowledge Graph", test_knowledge_graph),
        ("Skill Graph", test_skill_graph),
        ("Curriculum Engine", test_curriculum_engine),
        ("Project Manager", test_project_manager),
        ("Long-Term Goal Engine", test_long_term_goal_engine),
    ]

    passed_count = 0
    for name, test_func in tests:
        print(f"Running {name} unit test... ", end="", flush=True)
        try:
            test_func()
            print("PASSED")
            passed_count += 1
        except Exception as e:
            print("FAILED")
            import traceback
            traceback.print_exc()

    # Clean up test directories
    clean_db()
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR, ignore_errors=True)

    print(f"\nTest Result: {passed_count}/{len(tests)} tests passed.")
    if passed_count == len(tests):
        sys.exit(0)
    else:
        sys.exit(1)
