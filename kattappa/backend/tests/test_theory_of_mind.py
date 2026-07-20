import pytest
from backend.core.theory_of_mind.belief_tracker import BeliefTracker
from backend.core.theory_of_mind.knowledge_asymmetry import KnowledgeAsymmetry
from backend.core.theory_of_mind.perspective_engine import PerspectiveEngine
from backend.core.theory_of_mind.theory_of_mind_engine import TheoryOfMindEngine


def test_belief_tracker_records_and_updates() -> None:
    tracker = BeliefTracker()
    tracker.update_belief("python_version", "3.10", confidence=0.90)
    
    belief = tracker.get_belief("python_version")
    assert belief is not None
    assert belief["belief"] == "3.10"
    assert belief["confidence"] == 0.90

    # Update with new evidence — Bayesian consolidation
    tracker.update_belief("python_version", "3.12", confidence=1.0)
    updated = tracker.get_belief("python_version")
    # 0.90 * 0.7 + 1.0 * 0.3 = 0.93
    assert updated["belief"] == "3.12"
    assert pytest.approx(updated["confidence"], abs=0.01) == 0.93


def test_knowledge_asymmetry_detection() -> None:
    system_facts = {"python_installed", "git_configured", "vscode_available"}
    user_beliefs = {"python_installed", "docker_available"}

    gaps = KnowledgeAsymmetry.detect_gaps(system_facts, user_beliefs)
    assert "git_configured" in gaps["system_knows_user_doesnt"]
    assert "vscode_available" in gaps["system_knows_user_doesnt"]
    assert "docker_available" in gaps["user_believes_system_doesnt"]
    assert "python_installed" in gaps["shared_knowledge"]
    assert gaps["asymmetry_ratio"] == pytest.approx(2 / 3, abs=0.01)


def test_perspective_expertise_inference() -> None:
    assert PerspectiveEngine.infer_expertise(1, 0) == "beginner"
    assert PerspectiveEngine.infer_expertise(10, 5) == "intermediate"
    assert PerspectiveEngine.infer_expertise(50, 15) == "expert"

    style = PerspectiveEngine.get_communication_style("expert")
    assert style["detail"] == "low"
    assert style["jargon"] is True


def test_theory_of_mind_engine_orchestration() -> None:
    engine = TheoryOfMindEngine()

    # Record beliefs
    engine.update_user_belief("os", "Windows 11", confidence=0.95)
    engine.update_user_belief("editor", "VSCode", confidence=0.99)

    # Detect knowledge gaps
    system_facts = {"os", "editor", "python_path", "gpu_available"}
    gaps = engine.detect_knowledge_gaps(system_facts)
    assert "python_path" in gaps["system_knows_user_doesnt"]
    assert "gpu_available" in gaps["system_knows_user_doesnt"]

    # Adapt communication style
    style = engine.get_adapted_style(interaction_count=30, technical_terms=12)
    assert style["expertise_level"] == "expert"
    assert style["jargon"] is True
