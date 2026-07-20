import pytest
from backend.core.skills_runtime.skill_registry import SkillRegistry
from backend.core.distillation.pattern_miner import PatternMiner
from backend.core.distillation.skill_generalizer import SkillGeneralizer
from backend.core.distillation.skill_optimizer import SkillOptimizer
from backend.core.distillation.skill_distillation_engine import SkillDistillationEngine

def test_pattern_miner_extraction() -> None:
    sequences = [
        ["click_a", "click_b", "click_c"],
        ["click_a", "click_b", "click_d"],
        ["click_a", "click_b", "click_e"]
    ]
    
    patterns = PatternMiner.mine_repeated_sequences(sequences, pattern_length=2, min_reps=3)
    
    assert len(patterns) == 1
    assert patterns[0][0] == ("click_a", "click_b")
    assert patterns[0][1] == 3

def test_skill_generalizer_parameters() -> None:
    commands = [
        "download file1.pdf",
        "download file2.pdf",
        "download file3.pdf"
    ]
    
    templated, variables = SkillGeneralizer.generalize_commands(commands)
    
    assert templated == "download {arg}"
    assert len(variables) == 1
    assert "file1.pdf" in variables[0]

def test_skill_optimizer_shortcut_substitution() -> None:
    steps = [
        {"cmd": "click", "x": 10, "y": 20},
        {"cmd": "click", "x": 10, "y": 20}, # Redundant click
        {"cmd": "click save", "x": 50, "y": 50} # Replaced by shortcut Ctrl+S
    ]
    
    optimized = SkillOptimizer.optimize_steps(steps)
    
    assert len(optimized) == 2
    assert optimized[0]["cmd"] == "click"
    assert optimized[1]["cmd"] == "shortcut Ctrl+S"

def test_distillation_engine_registration() -> None:
    registry = SkillRegistry()
    engine = SkillDistillationEngine(registry)
    
    sequences = [
        ["click_a", "click_b"],
        ["click_a", "click_b"],
        ["click_a", "click_b"],
        ["click_a", "click_b"],
        ["click_a", "click_b"],
        ["click_a", "click_b"],
        ["click_a", "click_b"],
        ["click_a", "click_b"],
        ["click_a", "click_b"],
        ["click_a", "click_b"]  # 10 repetitions to maximize confidence score
    ]
    
    raw_steps = [
        {"cmd": "click save", "x": 50, "y": 50}
    ]
    
    # Executing distillation
    ok = engine.distill_repeated_workflow("save_document", sequences, raw_steps, success_rate=0.98)
    assert ok
    
    skill = registry.get_skill("save_document")
    assert skill is not None
    assert skill.steps[0]["cmd"] == "shortcut Ctrl+S"
