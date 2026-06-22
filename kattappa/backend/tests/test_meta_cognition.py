from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.meta_cognition import MetaCognitionEngine, CognitiveMode, SupervisionAction
from backend.core.capability_graph import CapabilityGraph, CapabilityKind

@pytest.fixture(autouse=True)
def clean_capabilities():
    CapabilityGraph.reset()
    yield
    CapabilityGraph.reset()


def test_select_cognitive_mode():
    # DIRECT mode tests
    assert MetaCognitionEngine.select_cognitive_mode("2 + 2")["mode"] == CognitiveMode.DIRECT.value
    assert MetaCognitionEngine.select_cognitive_mode("hello")["mode"] == CognitiveMode.DIRECT.value
    assert MetaCognitionEngine.select_cognitive_mode("status")["mode"] == CognitiveMode.DIRECT.value

    # HIGH_ASSURANCE mode triggers
    assert MetaCognitionEngine.select_cognitive_mode("deploy to k8s cluster")["mode"] == CognitiveMode.HIGH_ASSURANCE.value
    assert MetaCognitionEngine.select_cognitive_mode("some task", is_production=True)["mode"] == CognitiveMode.HIGH_ASSURANCE.value
    assert MetaCognitionEngine.select_cognitive_mode("some task", is_code_change=True)["mode"] == CognitiveMode.HIGH_ASSURANCE.value
    assert MetaCognitionEngine.select_cognitive_mode("update system credentials")["mode"] == CognitiveMode.HIGH_ASSURANCE.value

    # DEEP_ANALYSIS mode triggers
    long_prompt = "explain the system topology and design constraints for our new microservices framework layout"
    assert MetaCognitionEngine.select_cognitive_mode(long_prompt)["mode"] == CognitiveMode.DEEP_ANALYSIS.value
    assert MetaCognitionEngine.select_cognitive_mode("design topology for dews system")["mode"] == CognitiveMode.DEEP_ANALYSIS.value


def test_detect_uncertainty():
    # High confidence/evidence
    res = MetaCognitionEngine.detect_uncertainty("prompt", routing_confidence=0.8, evidence_count=2, missing_validators=False)
    assert res["certainty"] == "HIGH"
    assert res["action"] == SupervisionAction.ALLOW.value

    # Low routing confidence
    res = MetaCognitionEngine.detect_uncertainty("prompt", routing_confidence=0.4, evidence_count=2, missing_validators=False)
    assert res["certainty"] == "LOW"
    assert res["action"] == SupervisionAction.REQUEST_MORE_EVIDENCE.value

    # No evidence
    res = MetaCognitionEngine.detect_uncertainty("prompt", routing_confidence=0.8, evidence_count=0, missing_validators=False)
    assert res["certainty"] == "LOW"
    assert res["action"] == SupervisionAction.REQUEST_MORE_EVIDENCE.value

    # Missing validators
    res = MetaCognitionEngine.detect_uncertainty("prompt", routing_confidence=0.8, evidence_count=2, missing_validators=True)
    assert res["certainty"] == "LOW"
    assert res["action"] == SupervisionAction.REQUEST_MORE_EVIDENCE.value


def test_detect_conflicts():
    # Allow cases
    res = MetaCognitionEngine.detect_conflicts(vetoes=[], blocking_findings=[], consensus_status="approved", simulation_success_rate=0.8)
    assert res["high_conflict"] is False
    assert res["action"] == SupervisionAction.ALLOW.value

    # Veto failure (dict representation)
    veto_failed = [{"passed": False, "source": "security_check"}]
    res = MetaCognitionEngine.detect_conflicts(vetoes=veto_failed, blocking_findings=[], consensus_status="approved")
    assert res["high_conflict"] is True
    assert res["action"] == SupervisionAction.ESCALATE.value

    # Veto failure (object representation)
    class MockVeto:
        def __init__(self, passed, source):
            self.passed = passed
            self.source = source
    res = MetaCognitionEngine.detect_conflicts(vetoes=[MockVeto(False, "safety")], blocking_findings=[], consensus_status="approved")
    assert res["high_conflict"] is True
    assert res["action"] == SupervisionAction.ESCALATE.value

    # Blocking findings
    res = MetaCognitionEngine.detect_conflicts(vetoes=[], blocking_findings=[{"issue": "critical error"}], consensus_status="approved")
    assert res["high_conflict"] is True
    assert res["action"] == SupervisionAction.ESCALATE.value

    # Consensus status rejected or escalate
    res = MetaCognitionEngine.detect_conflicts(vetoes=[], blocking_findings=[], consensus_status="escalate")
    assert res["high_conflict"] is True
    assert res["action"] == SupervisionAction.ESCALATE.value

    # Simulation success rate < 0.5
    res = MetaCognitionEngine.detect_conflicts(vetoes=[], blocking_findings=[], consensus_status="approved", simulation_success_rate=0.45)
    assert res["high_conflict"] is True
    assert res["action"] == SupervisionAction.ESCALATE.value


def test_detect_missing_capabilities():
    # Empty requirements
    res = MetaCognitionEngine.detect_missing_capabilities("goal", required_caps=[])
    assert res["cannot_execute"] is False
    assert res["action"] == SupervisionAction.ALLOW.value

    # Setup some capabilities
    CapabilityGraph.register("git", CapabilityKind.TOOL, available=True)
    CapabilityGraph.register("android_build", CapabilityKind.TOOL, available=False)

    # Missing capability
    res = MetaCognitionEngine.detect_missing_capabilities("Build App", required_caps=["git", "android_build"])
    assert res["cannot_execute"] is True
    assert "android_build" in res["missing"]
    assert res["action"] == SupervisionAction.ESCALATE.value

    # Make it available
    CapabilityGraph.set_available("android_build", True)
    res = MetaCognitionEngine.detect_missing_capabilities("Build App", required_caps=["git", "android_build"])
    assert res["cannot_execute"] is False
    assert res["action"] == SupervisionAction.ALLOW.value


def test_detect_reasoning_traps():
    # No traps
    res = MetaCognitionEngine.detect_reasoning_traps(chat_history=[{"role": "user", "content": "hello"}], failed_runs_count=0)
    assert not res["traps_detected"]
    assert res["action"] == SupervisionAction.ALLOW.value

    # Circular reasoning (repeated user prompt consecutively)
    history = [
        {"role": "user", "content": "how to build X?"},
        {"role": "assistant", "content": "Build it like this..."},
        {"role": "user", "content": "how to build X?"},
    ]
    res = MetaCognitionEngine.detect_reasoning_traps(chat_history=history, failed_runs_count=0)
    assert any("circular" in t.lower() for t in res["traps_detected"])
    assert res["action"] == SupervisionAction.ESCALATE.value

    # Repeated failed plans
    res = MetaCognitionEngine.detect_reasoning_traps(chat_history=[], failed_runs_count=2)
    assert any("failed" in t.lower() for t in res["traps_detected"])
    assert res["action"] == SupervisionAction.ESCALATE.value


def test_supervise_precedence():
    # Check hierarchy: ESCALATE > REQUEST_MORE_EVIDENCE > CHANGE_REASONING_MODE > ALLOW
    # Trigger both uncertainty (REQUEST_MORE_EVIDENCE) and traps (ESCALATE)
    res = MetaCognitionEngine.supervise(
        prompt="hello",
        routing_confidence=0.1,  # Uncertainty -> REQUEST_MORE_EVIDENCE
        failed_runs_count=2,    # Trap -> ESCALATE
    )
    assert res["action"] == SupervisionAction.ESCALATE.value

    # Trigger only uncertainty
    res = MetaCognitionEngine.supervise(
        prompt="hello",
        routing_confidence=0.1,  # Uncertainty -> REQUEST_MORE_EVIDENCE
        failed_runs_count=0,
    )
    assert res["action"] == SupervisionAction.REQUEST_MORE_EVIDENCE.value

    # Trigger CHANGE_REASONING_MODE: Prompt > 15 words but mode is DIRECT
    long_but_simple = "1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1"
    res = MetaCognitionEngine.supervise(
        prompt=long_but_simple,
        routing_confidence=1.0,
        evidence_count=1,
    )
    assert res["action"] == SupervisionAction.CHANGE_REASONING_MODE.value

    # Normal allowed direct
    res = MetaCognitionEngine.supervise(prompt="hello")
    assert res["action"] == SupervisionAction.ALLOW.value


def test_never_mutates_inputs():
    # Meta-Cognition should only return ALLOW, ESCALATE, REQUEST_MORE_EVIDENCE, CHANGE_REASONING_MODE
    # Confirm it does not try to mutate or alter consensus or veto arguments.
    vetoes = [{"passed": False, "source": "rule"}]
    res = MetaCognitionEngine.supervise(
        prompt="hello",
        vetoes=vetoes,
        consensus_status="approved",
    )
    assert vetoes[0]["passed"] is False  # untouched
    assert res["action"] == SupervisionAction.ESCALATE.value


# ===========================================================================
# REST API Integration Tests
# ===========================================================================

def test_api_status_endpoint():
    client = TestClient(app)
    response = client.get("/meta-cognition/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active"
    assert "rules" in data


def test_api_mode_endpoint():
    client = TestClient(app)
    response = client.post(
        "/meta-cognition/mode",
        json={"prompt": "deploy system", "is_production": True}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == CognitiveMode.HIGH_ASSURANCE.value


def test_api_supervise_endpoint():
    client = TestClient(app)
    response = client.post(
        "/meta-cognition/supervise",
        json={
            "prompt": "deploy to staging",
            "routing_confidence": 0.8,
            "evidence_count": 2,
            "missing_validators": False,
            "vetoes": [],
            "blocking_findings": [],
            "consensus_status": "approved",
            "simulation_success_rate": 0.9,
            "is_production": False,
            "is_code_change": False,
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == SupervisionAction.ALLOW.value
    assert data["mode"] == CognitiveMode.HIGH_ASSURANCE.value
