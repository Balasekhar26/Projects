import pytest
from backend.core.skills_runtime.skill_registry import Skill
from backend.core.skills_runtime.skills_runtime_engine import SkillsRuntimeEngine

def test_skill_registry_and_prerequisites() -> None:
    engine = SkillsRuntimeEngine()
    
    skill = Skill(
        name="run_tests",
        prerequisites=["python_installed", "pytest_installed"],
        steps=[{"cmd": "pytest", "x": 10, "y": 10}]
    )
    engine.register_skill(skill)
    
    # Prerequisites match
    assert engine.registry.validate_prerequisites("run_tests", ["python_installed", "pytest_installed", "git_installed"])
    
    # Prerequisites missing
    assert not engine.registry.validate_prerequisites("run_tests", ["python_installed"])

def test_skills_composition() -> None:
    engine = SkillsRuntimeEngine()
    
    # Sub-skill 1
    s1 = Skill("git_pull", ["git_installed"], [{"cmd": "git pull", "x": 0, "y": 0}], ["repo_pulled"])
    # Sub-skill 2
    s2 = Skill("pytest_run", ["python_installed"], [{"cmd": "pytest", "x": 20, "y": 20}], ["tests_passed"])
    
    engine.register_skill(s1)
    engine.register_skill(s2)
    
    # Compose composite DAG skill
    ok = engine.compose_skill("update_and_test", ["git_pull", "pytest_run"])
    assert ok
    
    composite = engine.registry.get_skill("update_and_test")
    assert composite is not None
    assert len(composite.steps) == 2
    # Combined prerequisites
    assert "git_installed" in composite.prerequisites
    assert "python_installed" in composite.prerequisites
    # Combined postconditions
    assert "repo_pulled" in composite.post_conditions
    assert "tests_passed" in composite.post_conditions

def test_skill_executor_status_routing() -> None:
    engine = SkillsRuntimeEngine()
    
    # 1. Blocked step safety validation
    bad_skill = Skill("dangerous", [], [{"cmd": "rm -rf /", "x": 0, "y": 0}])
    engine.register_skill(bad_skill)
    res_blocked = engine.execute("dangerous", [])
    assert res_blocked == "STEP_FAILED_BLOCKED"
    
    # 2. Prerequisites failed
    req_skill = Skill("run_rust", ["rustc_installed"], [{"cmd": "cargo build", "x": 0, "y": 0}])
    engine.register_skill(req_skill)
    res_prereq = engine.execute("run_rust", [])
    assert res_prereq == "PREREQUISITE_FAILED"
    
    # 3. Successful skill run
    good_skill = Skill("status_check", [], [{"cmd": "echo ready", "x": 50, "y": 50, "pre_snap": b"pre", "post_snap": b"post"}])
    engine.register_skill(good_skill)
    res_ok = engine.execute("status_check", [])
    assert res_ok == "SUCCESS"
    assert engine.executor.action_executor.controller.mouse_x == 50
