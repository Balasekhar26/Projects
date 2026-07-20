import pytest
import os
import tempfile
from backend.agents.planner import PlannerAgent, TaskGraph, TaskStep
from backend.core.memory.memory_store import MemoryStore
from backend.core.skills.skill_registry import SkillRegistry
from backend.core.skills.skill_extractor import SkillExtractor
from backend.core.skills.skill_selector import SkillSelector
from backend.core.skills.skill_executor import SkillExecutor

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_skills_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    MemoryStore.clear_database()
    yield temp_dir
    MemoryStore.clear_database()

def test_skills_table_storage() -> None:
    SkillRegistry.register_skill(
        skill_id="install_recovery_v1",
        trigger_conditions={"keywords": ["pip", "install"]},
        prerequisites={"os": "any"},
        action_sequence=[
            {"step_id": "s1", "description": "Create venv", "agent": "coder", "action": "RUN_SHELL", "params": {"command": "venv"}}
        ],
        confidence_score=0.95,
        success_count=5
    )
    
    skills = MemoryStore.get_all_skills()
    assert len(skills) == 1
    assert skills[0]["id"] == "install_recovery_v1"
    assert skills[0]["confidence_score"] == 0.95
    assert skills[0]["success_count"] == 5

def test_skill_extractor_from_reflection() -> None:
    reflection = {
        "status": "COMPLETED",
        "goal_text": "Setup local CUDA library config",
        "confidence_rating": 0.90
    }
    action_seq = [
        {"step_id": "s1", "description": "Check CUDA version", "agent": "coder", "action": "RUN_SHELL", "params": {"command": "nvcc"}}
    ]
    
    skill = SkillExtractor.extract_skill_from_reflection(reflection, action_seq)
    assert skill is not None
    assert "cuda" in skill["trigger_conditions"]["keywords"]
    assert skill["action_sequence"] == action_seq
    
    stored = SkillRegistry.get_skill(skill["skill_id"])
    assert stored is not None
    assert stored["confidence_score"] == 0.90

def test_skill_selector_confidence_threshold() -> None:
    SkillRegistry.register_skill(
        skill_id="skill_high",
        trigger_conditions={"keywords": ["compile", "java"]},
        prerequisites={},
        action_sequence=[{"step_id": "s1", "description": "Compile", "agent": "coder", "action": "COMPILE"}],
        confidence_score=0.90
    )
    
    SkillRegistry.register_skill(
        skill_id="skill_low",
        trigger_conditions={"keywords": ["compile", "java"]},
        prerequisites={},
        action_sequence=[{"step_id": "s1", "description": "Compile", "agent": "coder", "action": "COMPILE"}],
        confidence_score=0.60
    )
    
    match = SkillSelector.select_skill("compile java codebase")
    assert match is not None
    assert match["skill_id"] == "skill_high"

def test_skill_executor_taskgraph_compilation() -> None:
    skill = {
        "action_sequence": [
            {
                "step_id": "s1",
                "description": "Initialize repository",
                "agent": "coder",
                "action": "RUN_SHELL",
                "params": {"command": "git init"}
            }
        ]
    }
    
    graph = SkillExecutor.execute_skill(skill, "Initialize repository")
    assert isinstance(graph, TaskGraph)
    assert "s1" in graph.steps
    assert graph.steps["s1"].action == "RUN_SHELL"

def test_planner_agent_skills_interception_integration() -> None:
    SkillRegistry.register_skill(
        skill_id="skill_test_compile",
        trigger_conditions={"keywords": ["compile", "project"]},
        prerequisites={},
        action_sequence=[
            {"step_id": "compile_step", "description": "Build project target", "agent": "coder", "action": "RUN_SHELL", "params": {"command": "make build"}}
        ],
        confidence_score=0.95
    )
    
    agent = PlannerAgent()
    graph = agent.decompose("compile project source codes")
    
    assert "compile_step" in graph.steps
    assert graph.steps["compile_step"].action == "RUN_SHELL"
    assert graph.steps["compile_step"].params["command"] == "make build"
