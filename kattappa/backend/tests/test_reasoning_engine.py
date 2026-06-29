"""Tests for backend/core/reasoning_engine.py — ReasoningKernel."""
from __future__ import annotations

import time
import pytest

from backend.core.reasoning_engine import ReasoningEngine, ReasoningTrace
from backend.core.event_bus import EventBus, EventName


@pytest.fixture(autouse=True)
def clean():
    EventBus.reset()
    yield
    EventBus.reset()


# ---------------------------------------------------------------------------
# analyze() — backward-compatible interface
# ---------------------------------------------------------------------------

def test_analyze_software_dev_domain():
    result = ReasoningEngine.analyze("Build Python module", "Compile and run python script file")
    assert result["domain"] == "Software Development"
    assert "assumptions" in result
    assert "risks" in result
    assert result["status"] in ("READY_TO_PLAN", "REQUIRES_CLARIFICATION")


def test_analyze_devops_domain():
    result = ReasoningEngine.analyze("Deploy to server", "Deploy to port 8000 on host production")
    assert result["domain"] == "DevOps/Infrastructure"


def test_analyze_missing_port_triggers_clarification():
    result = ReasoningEngine.analyze("Deploy backend service", "Push changes to cloud server")
    # No port/host/url → should require clarification
    assert result["status"] == "REQUIRES_CLARIFICATION"
    assert len(result["clarification_questions"]) > 0


def test_analyze_destructive_triggers_risk():
    result = ReasoningEngine.analyze("Clean old data", "Delete all old records from database")
    risk_categories = [r["category"] for r in result["risks"]]
    assert "REVERSIBILITY_RISK" in risk_categories


def test_analyze_sudo_triggers_privilege_risk():
    result = ReasoningEngine.analyze("Install package", "Run sudo apt install tool")
    risk_categories = [r["category"] for r in result["risks"]]
    assert "PRIVILEGE_RISK" in risk_categories


def test_analyze_returns_analyzed_at():
    result = ReasoningEngine.analyze("Test goal", "Some description")
    assert result["analyzed_at"] > 0


# ---------------------------------------------------------------------------
# reason() — full Reasoning Kernel
# ---------------------------------------------------------------------------

def test_reason_returns_reasoning_trace():
    trace = ReasoningEngine.reason("Build backend module", "Create a Python FastAPI module")
    assert isinstance(trace, ReasoningTrace)
    assert trace.trace_id != ""
    assert len(trace.trace_id) == 16


def test_reason_trace_serializable():
    trace = ReasoningEngine.reason("Deploy API", "Deploy to port 8080 on host staging")
    d = trace.to_dict()
    assert isinstance(d, dict)
    assert "trace_id" in d
    assert "domain" in d
    assert "status" in d
    assert "blackboard_entries" in d


def test_reason_classifies_domain():
    trace = ReasoningEngine.reason("Compile Rust binary", "Build rust code into binary")
    assert trace.domain == "Software Development"


def test_reason_devops_domain():
    trace = ReasoningEngine.reason("Deploy Docker container", "Deploy to kubernetes cluster on port 443")
    assert trace.domain == "DevOps/Infrastructure"


def test_reason_ai_cognitive_domain():
    trace = ReasoningEngine.reason("Upgrade memory recall", "Improve cognitive memory retrieval via blackboard")
    assert trace.domain == "AI/Cognitive Systems"


def test_reason_extracts_intent():
    assert ReasoningEngine.reason("Build data pipeline", "").intent == "BUILD"
    assert ReasoningEngine.reason("Deploy to production", "").intent == "DEPLOY"
    assert ReasoningEngine.reason("Fix memory leak", "").intent == "FIX"
    assert ReasoningEngine.reason("Refactor planner module", "").intent == "REFACTOR"
    assert ReasoningEngine.reason("Test reasoning engine", "").intent == "VERIFY"


def test_reason_extracts_assumptions():
    trace = ReasoningEngine.reason("Build Python API", "Create FastAPI python module")
    assert len(trace.assumptions) > 0
    # Should mention compiler/interpreter
    all_text = " ".join(trace.assumptions).lower()
    assert "compiler" in all_text or "interpreter" in all_text


def test_reason_detects_missing_info_without_path():
    trace = ReasoningEngine.reason("Build module", "Create a python module with no target specified")
    assert any("path" in m.lower() or "filename" in m.lower() for m in trace.missing_information)


def test_reason_detects_reversibility_risk():
    trace = ReasoningEngine.reason("Cleanup old data", "Delete all temporary files and clean database")
    risk_cats = [r["category"] for r in trace.risks]
    assert "REVERSIBILITY_RISK" in risk_cats


def test_reason_detects_credential_risk():
    trace = ReasoningEngine.reason("API integration", "Set api_key and password in config file")
    risk_cats = [r["category"] for r in trace.risks]
    assert "CREDENTIAL_RISK" in risk_cats


def test_reason_detects_production_risk():
    trace = ReasoningEngine.reason("Deploy to production", "Roll out update to production environment")
    risk_cats = [r["category"] for r in trace.risks]
    assert "PRODUCTION_RISK" in risk_cats


def test_reason_ready_to_plan_when_no_gaps():
    # Full info supplied: domain=DevOps, port and host present
    trace = ReasoningEngine.reason(
        "Deploy to server",
        "Deploy service to port 8080 on host 192.168.1.1"
    )
    # No missing info → should be READY_TO_PLAN (unless capability gaps)
    if not trace.capability_gaps:
        assert trace.status == "READY_TO_PLAN"


def test_reason_blocked_on_capability_when_gap():
    # Pass an explicitly required capability that doesn't exist in the graph
    trace = ReasoningEngine.reason(
        "Launch quantum processor",
        "Use quantum computing chip for inference",
        required_capabilities=["quantum_compute_unit_v9_nonexistent"],
    )
    # Should detect a capability gap for the missing cap
    assert any(
        "quantum_compute_unit_v9_nonexistent" in g["capability"]
        for g in trace.capability_gaps
    ), f"Expected capability gap, got: {trace.capability_gaps}"
    assert trace.status == "BLOCKED_ON_CAPABILITY"


def test_reason_blackboard_entries_populated():
    trace = ReasoningEngine.reason("Build Python module", "Write a python file")
    assert len(trace.blackboard_entries) >= 2  # at least: goal fact + assumption + verdict
    kinds = [e["kind"] for e in trace.blackboard_entries]
    assert "fact" in kinds
    assert "assumption" in kinds
    assert "agent_output" in kinds


def test_reason_blackboard_verdict_entry():
    trace = ReasoningEngine.reason("Deploy service", "Deploy to port 9000 on host staging")
    verdict_entries = [
        e for e in trace.blackboard_entries
        if "VERDICT" in str(e.get("content", ""))
    ]
    assert len(verdict_entries) >= 1


# ---------------------------------------------------------------------------
# EventBus integration
# ---------------------------------------------------------------------------

def test_capability_assessed_event_emitted():
    events: list = []
    EventBus.subscribe(EventName.CAPABILITY_ASSESSED, events.append)

    ReasoningEngine.reason("Build Python API", "Write python module for FastAPI")
    time.sleep(0.15)  # async handlers

    # Should emit at least one CapabilityAssessed event
    assert len(events) >= 1
    assert events[0].name == EventName.CAPABILITY_ASSESSED


def test_belief_updated_event_emitted_on_risk():
    events: list = []
    EventBus.subscribe(EventName.BELIEF_UPDATED, events.append)

    ReasoningEngine.reason("Delete all records", "Run delete all from database")
    time.sleep(0.15)

    assert len(events) >= 1
    assert events[0].name == EventName.BELIEF_UPDATED


# ---------------------------------------------------------------------------
# Infer capabilities
# ---------------------------------------------------------------------------

def test_infer_capabilities_software():
    caps = ReasoningEngine._infer_capabilities("Software Development", "build python test with git commit")
    assert "code_execution" in caps
    assert "test_runner" in caps
    assert "git_operations" in caps


def test_infer_capabilities_devops():
    caps = ReasoningEngine._infer_capabilities("DevOps/Infrastructure", "deploy docker container")
    assert "shell_execution" in caps
    assert "docker" in caps
    assert "deployment" in caps
