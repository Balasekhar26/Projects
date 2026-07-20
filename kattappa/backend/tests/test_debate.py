import pytest
import os
from backend.agents.planner import PlannerAgent, TaskGraph, TaskStep
from backend.core.debate.debate_message import DebateMessage
from backend.core.debate.confidence_aggregator import ConfidenceAggregator
from backend.core.debate.consensus_engine import ConsensusEngine
from backend.core.debate.debate_engine import DebateEngine
from backend.core.debate.agents.critic_agent import CriticAgent
from backend.core.debate.agents.security_agent import SecurityAgent
from backend.core.debate.agents.resource_agent import ResourceAgent

@pytest.fixture(autouse=True)
def setup_test_mode(monkeypatch):
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")

def test_debate_message_creation() -> None:
    msg = DebateMessage(
        sender="TestAgent",
        message_type="CRITIQUE",
        content="Objection raised",
        confidence_score=0.75,
        suggestions=["suggestion1"]
    )
    assert msg.sender == "TestAgent"
    assert msg.confidence_score == 0.75

def test_aggregator_and_consensus() -> None:
    scores = {
        "planner": 0.90,
        "critic": 0.85,
        "security": 0.95
    }
    agg = ConfidenceAggregator.aggregate(scores)
    assert 0.80 <= agg <= 0.95
    
    decision = ConsensusEngine.resolve(agg)
    assert decision == "EXECUTE"

def test_specialist_critic_cycles() -> None:
    graph = TaskGraph("Circular Task")
    step1 = TaskStep("s1", "Step 1", "coder", "WRITE_FILE", {}, ["s2"])
    step2 = TaskStep("s2", "Step 2", "coder", "WRITE_FILE", {}, ["s1"])
    graph.add_step(step1)
    graph.add_step(step2)
    
    msg = CriticAgent.evaluate(graph)
    assert msg.confidence_score == 0.40
    assert any("circular_dependency" in s for s in msg.suggestions)

def test_specialist_resource_limits() -> None:
    graph = TaskGraph("Run Qwen 72B model")
    step = TaskStep("s1", "Start local model inference", "coder", "RUN_MODEL", {"model": "qwen-72b-instruct"}, [])
    graph.add_step(step)
    
    msg = ResourceAgent.evaluate(graph)
    assert msg.confidence_score == 0.40
    assert any("insufficient_ram" in s for s in msg.suggestions)

def test_specialist_security_checks() -> None:
    graph = TaskGraph("Wipe workspace")
    step = TaskStep("s1", "Delete code folder", "coder", "DELETE_FILE", {"path": "backend/"}, [])
    graph.add_step(step)
    
    msg = SecurityAgent.evaluate(graph)
    assert msg.confidence_score == 0.50
    assert any("high_risk_deletion" in s for s in msg.suggestions)

def test_debate_revision_integration() -> None:
    graph = TaskGraph("Circular task path")
    step1 = TaskStep("s1", "Step 1", "coder", "WRITE_FILE", {}, ["s2"])
    step2 = TaskStep("s2", "Step 2", "coder", "WRITE_FILE", {}, ["s1"])
    graph.add_step(step1)
    graph.add_step(step2)
    
    debated_graph, confidence, decision = DebateEngine.run_debate(graph, mode="Standard")
    assert decision == "EXECUTE"
    assert len(debated_graph.steps["s1"].dependencies) == 0
