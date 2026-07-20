import pytest
import os
import tempfile
from backend.agents.planner import PlannerAgent
from backend.core.planner.intent_classifier import IntentClassifier
from backend.core.planner.constraint_extractor import ConstraintExtractor
from backend.core.planner.context_builder import ContextBuilder
from backend.core.planner.dag_builder import DAGBuilder
from backend.core.planner.risk_engine import RiskEngine
from backend.core.planner.verification_engine import VerificationEngine

@pytest.fixture(autouse=True)
def test_env_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_planner_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    yield temp_dir

def test_intent_and_constraint_extraction() -> None:
    # 1. Intent classifier check
    intent1 = IntentClassifier.classify_intent("Search the web for CUDA drivers")
    assert intent1 == "research"

    intent2 = IntentClassifier.classify_intent("Write a python test script")
    assert intent2 == "coding"

    # 2. Constraint extraction check
    c1 = ConstraintExtractor.extract_constraints("Install library offline and local-only on 8GB machine")
    assert c1["offline"] is True
    assert c1["local_only"] is True
    assert c1["ram_limit"] == "8GB"

def test_risk_and_verification_rules() -> None:
    # 1. Risk checks
    r1 = RiskEngine.estimate_risk("DELETE_FILE", {"path": "main.py"})
    assert r1 == "HIGH"
    
    r2 = RiskEngine.estimate_risk("READ_FILE", {"path": "main.py"})
    assert r2 == "LOW"

    # 2. Verification checks
    v1 = VerificationEngine.get_verification_method("WRITE_FILE", {"target": "main.py"})
    assert v1["type"] == "file_exists"
    assert v1["target"] == "main.py"

def test_dag_builder_cycle_detection() -> None:
    # 1. Valid DAG
    steps = [
        {"step_id": "s1", "dependencies": []},
        {"step_id": "s2", "dependencies": ["s1"]}
    ]
    ordered = DAGBuilder.validate_and_order(steps)
    assert [s["step_id"] for s in ordered] == ["s1", "s2"]

    # 2. Circular dependencies DAG
    cyclic_steps = [
        {"step_id": "s1", "dependencies": ["s2"]},
        {"step_id": "s2", "dependencies": ["s1"]}
    ]
    with pytest.raises(ValueError, match="Cyclic dependencies detected"):
        DAGBuilder.validate_and_order(cyclic_steps)

def test_planner_agent_decomposition_integration() -> None:
    agent = PlannerAgent()
    
    # Check "write and test" goal
    graph = agent.decompose("Write a sample.py file and run the tests")
    assert "step1" in graph.steps
    assert "step2" in graph.steps
    
    step1 = graph.steps["step1"]
    assert step1.action == "WRITE_FILE"
    assert step1.dependencies == []
    
    step2 = graph.steps["step2"]
    assert step2.action == "RUN_TESTS"
    assert step2.dependencies == ["step1"]
