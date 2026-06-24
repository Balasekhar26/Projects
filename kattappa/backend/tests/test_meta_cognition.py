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


# ===========================================================================
# MRAL (Step 8.6) Integration Tests
# ===========================================================================

@pytest.fixture(autouse=True)
def clean_db():
    from backend.core.meta_cognition import MRALAuditor
    conn = MRALAuditor._get_sqlite_conn()
    try:
        conn.execute("DELETE FROM mral_contradictions")
        conn.execute("DELETE FROM mral_assumptions")
        conn.execute("DELETE FROM mral_decision_traces")
        conn.commit()
    finally:
        conn.close()
    yield
    conn = MRALAuditor._get_sqlite_conn()
    try:
        conn.execute("DELETE FROM mral_contradictions")
        conn.execute("DELETE FROM mral_assumptions")
        conn.execute("DELETE FROM mral_decision_traces")
        conn.commit()
    finally:
        conn.close()


def test_mral_tables_exist():
    from backend.core.meta_cognition import MRALAuditor
    conn = MRALAuditor._get_sqlite_conn()
    try:
        tables = ["mral_decision_traces", "mral_assumptions", "mral_contradictions"]
        for t in tables:
            row = conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{t}'").fetchone()
            assert row is not None, f"Table {t} does not exist!"
    finally:
        conn.close()


def test_detect_assumptions():
    from backend.core.meta_cognition import MRALAuditor
    
    asm = MRALAuditor.detect_assumptions("Build a drone delivery system", "Deliver payloads automatically", [])
    assert len(asm) > 0
    categories = [a["category"] for a in asm]
    assert "REGULATIONS" in categories
    assert "HARDWARE" in categories

    asm = MRALAuditor.detect_assumptions("Deploy application to AWS", "Set up database connection", [])
    categories = [a["category"] for a in asm]
    assert "NETWORK" in categories
    assert "DEPLOYMENT" in categories

    asm = MRALAuditor.detect_assumptions("simple calculation", "no special keywords", [])
    categories = [a["category"] for a in asm]
    assert "OPERATIONS" in categories


def test_detect_contradictions():
    from backend.core.meta_cognition import MRALAuditor
    
    goal_desc = "Drone battery range is 15 km"
    plan_steps = [{"action": "Plan flight path", "description": "Delivery distance is 25 km"}]
    ctr = MRALAuditor.detect_contradictions("Drone Delivery", goal_desc, plan_steps, {}, {}, {})
    assert len(ctr) == 1
    assert ctr[0]["severity"] == "BLOCKING"
    assert "battery range" in ctr[0]["description"]

    ctr = MRALAuditor.detect_contradictions("Plan Drone delivery", "battery range 30 km", [{"action": "Fly", "description": "distance 10 km"}], {}, {}, {})
    assert len(ctr) == 0


def test_calculate_confidence_tree():
    from backend.core.meta_cognition import MRALAuditor
    
    tree = MRALAuditor.calculate_confidence_tree(
        research_topics=[{"domain": "RF", "contradictions": 1, "questions": 2}],
        sandbox_report={"validation_score": 90.0},
        verification_prediction={"status": "APPROVED"},
        consensus_decision={"approve_mass": 3.0, "reject_mass": 1.0}
    )
    assert tree["research"] == 90.0 - 5.0 - 4.0
    assert tree["simulation"] == 90.0
    assert tree["verification"] == 92.0
    assert tree["consensus"] == 75.0


def test_record_and_replay_trace():
    from backend.core.meta_cognition import MRALAuditor
    
    mral_res = MRALAuditor.record_decision_trace(
        goal_id="g123",
        goal_title="Test Drone battery range 15 km",
        goal_description="Route distance 25 km",
        plan_steps=[],
        consensus_decision={"status": "approved", "requires_human_approval": False, "approve_mass": 2.5, "reject_mass": 0.0},
        sandbox_report={"validation_score": 95.0},
        verification_prediction={"status": "APPROVED"},
        research_topics=[],
        lis_profile={"composite_health_score": 92.0},
        lis_alarms={},
        role_weights={"TEACHER": 25, "ENGINEER": 25, "SCIENTIST": 25, "BUILDER": 25}
    )
    
    assert mral_res["decision_id"] is not None
    assert len(mral_res["contradictions"]) == 1

    replay = MRALAuditor.get_decision_replay(mral_res["decision_id"])
    assert replay is not None
    assert replay["goal_title"] == "Test Drone battery range 15 km"
    assert replay["final_decision"] == "approved"
    assert len(replay["assumptions"]) > 0
    assert len(replay["contradictions"]) == 1

    all_traces = MRALAuditor.get_all_traces()
    assert len(all_traces) == 1
    assert all_traces[0]["decision_id"] == mral_res["decision_id"]


def test_api_mral_endpoints():
    from backend.core.meta_cognition import MRALAuditor
    
    mral_res = MRALAuditor.record_decision_trace(
        goal_id="g123",
        goal_title="Test Goal",
        goal_description="Test Desc",
        plan_steps=[],
        consensus_decision={"status": "approved", "requires_human_approval": False, "approve_mass": 2.5, "reject_mass": 0.0},
        sandbox_report={"validation_score": 95.0},
        verification_prediction={"status": "APPROVED"},
        research_topics=[],
        lis_profile={"composite_health_score": 92.0},
        lis_alarms={},
        role_weights={"TEACHER": 25, "ENGINEER": 25, "SCIENTIST": 25, "BUILDER": 25}
    )

    client = TestClient(app)
    
    resp = client.get("/dashboard/cognitive/mral/traces")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["traces"]) == 1

    resp = client.get(f"/dashboard/cognitive/mral/traces/{mral_res['decision_id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["trace"]["goal_title"] == "Test Goal"

    resp = client.post(
        "/dashboard/cognitive/mral/traces/test-run",
        json={
            "goal_title": "Build battery range 15 km",
            "goal_description": "route distance 25 km",
            "plan_steps": []
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["data"]["mral_audit"]["decision_id"] is not None
