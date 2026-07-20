"""Unit tests for Phase K22+ Introspection and Reputation upgrades."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Mock cognitive_kernel to avoid microkernel service initialization during unit test run
sys.modules["backend.core.cognitive_kernel"] = MagicMock()

import pytest
from backend.core.self_model import SelfModel
from backend.core.tool_reliability import ToolReliabilityTracker
from backend.core.agent_reputation import AgentReputationTracker
from backend.core.meta_executive import MetaExecutive


def test_self_model_state_fields():
    # Fetch dynamic self-model state
    state = SelfModel.get_self_model_state()
    
    # Verify Capabilities block
    assert "capabilities" in state
    assert "browser_control" in state["capabilities"]
    assert "desktop_control" in state["capabilities"]
    assert "shell_execution" in state["capabilities"]
    assert "code_generation" in state["capabilities"]
    assert "vision" in state["capabilities"]
    assert "voice" in state["capabilities"]
    
    # Verify Limitations block
    assert "limitations" in state
    assert "cannot_access_internet" in state["limitations"]
    assert "insufficient_permissions" in state["limitations"]
    assert "memory_limit" in state["limitations"]
    
    # Verify Resources block
    assert "resources" in state
    assert "cpu_usage" in state["resources"]
    assert "ram_usage" in state["resources"]
    assert "token_budget" in state["resources"]
    assert "battery_state" in state["resources"]
    
    # Verify Confidence block
    assert "confidence" in state
    assert "planning_confidence" in state["confidence"]
    assert "execution_confidence" in state["confidence"]
    assert "memory_confidence" in state["confidence"]
    assert "world_model_confidence" in state["confidence"]


def test_tool_utility_scoring():
    ToolReliabilityTracker.reset()
    
    # Check default score for unrecorded tool
    default_rel = ToolReliabilityTracker.get_reliability("terminal")
    assert "utility_score" in default_rel
    assert "security_risk" in default_rel
    assert default_rel["security_risk"] == 1.0
    
    # Record a mix of successes and failures
    ToolReliabilityTracker.record_invocation("terminal", success=True, latency=0.1)
    ToolReliabilityTracker.record_invocation("terminal", success=True, latency=0.2)
    ToolReliabilityTracker.record_invocation("terminal", success=False, latency=1.5, error="Timeout")
    
    rel = ToolReliabilityTracker.get_reliability("terminal")
    assert rel["success_rate"] == 0.667
    assert rel["utility_score"] >= 0.0
    assert rel["utility_score"] <= 1.0


def test_agent_trust_scoring():
    AgentReputationTracker.reset()
    
    # Check default trust score
    default_rep = AgentReputationTracker.get_reputation("coder")
    assert "trust_score" in default_rep
    assert default_rep["trust_score"] == 0.95
    
    # Record successes and failures
    AgentReputationTracker.record_execution("coder", success=True, latency=0.2)
    AgentReputationTracker.record_execution("coder", success=False, latency=0.9, hallucination=True)
    
    rep = AgentReputationTracker.get_reputation("coder")
    assert rep["success_rate"] == 0.5
    assert rep["failure_rate"] == 0.5
    assert "trust_score" in rep
    assert rep["trust_score"] < 0.95


def test_workspace_2_0_recursive_loop():
    from backend.core.cognitive_memory_bus import MEMORY_BUS, ReadResult
    from backend.core.self_model import SelfModel
    
    # Direct assignment mocking
    original_read = MEMORY_BUS.read
    original_eval = SelfModel.evaluate_capability
    called = []
    
    def mock_read(query, memory_types=None, session_id=None, limit=10):
        called.append(query)
        return [ReadResult(memory_type="working", records=[{"content": "mock memory"}])]
        
    def mock_evaluate(capability_phrase: str):
        return True, 0.95, "Allowed"
        
    MEMORY_BUS.read = mock_read
    SelfModel.evaluate_capability = mock_evaluate
    
    try:
        # Trigger prefrontal loop with simulated very low confidence
        exec_service = MetaExecutive(kernel_ref=None)
        
        # Query something complex to trigger prefrontal loop routing
        res = exec_service.run_prefrontal_loop("compile complex code and check compiler configurations", complexity=6.0)
        
        assert "re_search_attempts" in res
        assert res["re_search_attempts"] >= 0
    finally:
        MEMORY_BUS.read = original_read
        SelfModel.evaluate_capability = original_eval


