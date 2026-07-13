from fastapi.testclient import TestClient
from backend.main import app
from backend.core.cos.kernel import KERNEL
from backend.core.observability.telemetry import TelemetryCollector, trace_span
from backend.core.observability.provenance_logger import log_decision


def test_span_trace_id_propagation():
    collector = TelemetryCollector()
    collector.clear()
    
    with trace_span("root_span") as root:
        assert root.trace_id is not None
        root_trace_id = root.trace_id
        
        with trace_span("child_span") as child:
            assert child.parent_span_id == root.span_id
            assert child.trace_id == root_trace_id
            
            with trace_span("grandchild_span") as grandchild:
                assert grandchild.parent_span_id == child.span_id
                assert grandchild.trace_id == root_trace_id


def test_decision_provenance_logging():
    collector = TelemetryCollector()
    collector.clear()
    
    with trace_span("planning_phase") as span:
        trace_id = span.trace_id
        span_id = span.span_id
        
        dec_id = log_decision(
            stage="planning",
            action="choose_vector_db",
            reason="High recall matching in test settings",
            alternatives=["sqlite_fts", "chroma"],
            confidence=0.95,
            inputs={"query": "meeting notes"},
            outputs={"selected": "chroma"},
        )
        
        assert dec_id is not None
        
        # Verify in SQLite database via ledger
        decisions = KERNEL.ledger.get_decisions(trace_id)
        assert len(decisions) == 1
        
        decision = decisions[0]
        assert decision["decision_id"] == dec_id
        assert decision["span_id"] == span_id
        assert decision["stage"] == "planning"
        assert decision["action"] == "choose_vector_db"
        assert decision["reason"] == "High recall matching in test settings"
        assert decision["alternatives_considered"] == ["sqlite_fts", "chroma"]
        assert decision["confidence"] == 0.95
        assert decision["inputs"] == {"query": "meeting notes"}
        assert decision["outputs"] == {"selected": "chroma"}


def test_decision_endpoints():
    client = TestClient(app)
    
    # Record a test decision via API
    response = client.post(
        "/api/v1/telemetry/decision",
        json={
            "stage": "intent",
            "action": "route_to_obsidian",
            "reason": "Explicit user command matching",
            "alternatives": ["route_to_vscode", "route_to_notepad"],
            "confidence": 0.99,
            "inputs": {"text": "open meeting notes"},
            "outputs": {"route": "obsidian"},
        }
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    dec_id = response.json()["decision_id"]
    
    # Get decisions by stage
    response = client.get("/api/v1/telemetry/provenance/decisions/intent")
    assert response.status_code == 200
    assert len(response.json()) >= 1
    
    # Locate recorded decision
    found = False
    for dec in response.json():
        if dec["decision_id"] == dec_id:
            found = True
            assert dec["action"] == "route_to_obsidian"
            assert dec["reason"] == "Explicit user command matching"
            assert dec["confidence"] == 0.99
            break
    assert found
