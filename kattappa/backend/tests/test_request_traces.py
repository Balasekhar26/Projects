from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.governance.request_tracer import RequestTracer, GLOBAL_TRACES, TRACES_LOCK
from backend.core.failure_codes import FailureReason

client = TestClient(app)

@pytest.fixture(autouse=True)
def clear_global_traces():
    with TRACES_LOCK:
        GLOBAL_TRACES.clear()
    yield
    with TRACES_LOCK:
        GLOBAL_TRACES.clear()


class TestRequestTracerObservability:
    def test_finalize_saves_trace(self):
        tracer = RequestTracer("test request", mode="ASSISTANT")
        tracer.record_stage(router="file_agent", capability="CAP_FILE_READ", tool="list_directory")
        tracer.finalize(result="Successfully read directory")

        with TRACES_LOCK:
            assert len(GLOBAL_TRACES) == 1
            trace = GLOBAL_TRACES[0]
            assert trace["input"] == "test request"
            assert trace["mode"] == "ASSISTANT"
            assert trace["router"] == "file_agent"
            assert "CAP_FILE_READ" in trace["capabilities"]
            assert "list_directory" in trace["tools"]
            assert trace["result"] == "Successfully read directory"
            assert trace["failure_reason"] == "OK"
            assert trace["latency_ms"] >= 0.0

    def test_finalize_failure_saves_trace(self):
        tracer = RequestTracer("blocked input", mode="CHAT")
        tracer.finalize_failure(FailureReason.SAFETY_BLOCKED, detail="Blocked keyword detected", result="Policy block")

        with TRACES_LOCK:
            assert len(GLOBAL_TRACES) == 1
            trace = GLOBAL_TRACES[0]
            assert trace["input"] == "blocked input"
            assert trace["mode"] == "CHAT"
            assert trace["failure_reason"] == "SAFETY_BLOCKED"
            assert trace["failure_detail"] == "Blocked keyword detected"
            assert trace["result"] == "Policy block"

    def test_eviction_under_max_traces(self):
        # Temporarily adjust MAX_TRACES limit in module
        from backend.core.governance import request_tracer
        original_max = request_tracer.MAX_TRACES
        request_tracer.MAX_TRACES = 3

        try:
            for i in range(5):
                tracer = RequestTracer(f"request {i}", mode="CHAT")
                tracer.finalize(result="done")

            with TRACES_LOCK:
                assert len(GLOBAL_TRACES) == 3
                # Should contain last 3: request 2, request 3, request 4
                inputs = [t["input"] for t in GLOBAL_TRACES]
                assert inputs == ["request 2", "request 3", "request 4"]
        finally:
            request_tracer.MAX_TRACES = original_max


class TestTelemetryTracesEndpoint:
    def test_get_telemetry_traces_empty(self):
        response = client.get("/telemetry/traces")
        assert response.status_code == 200
        data = response.json()
        assert "traces" in data
        assert len(data["traces"]) == 0

    def test_get_telemetry_traces_ordered(self):
        # Create some traces
        t1 = RequestTracer("first", mode="CHAT")
        t1.finalize(result="1")

        t2 = RequestTracer("second", mode="CHAT")
        t2.finalize(result="2")

        response = client.get("/telemetry/traces")
        assert response.status_code == 200
        data = response.json()
        assert "traces" in data
        assert len(data["traces"]) == 2
        # Should be reverse chronological order (newest/second first)
        assert data["traces"][0]["input"] == "second"
        assert data["traces"][1]["input"] == "first"
        # Check prefix-based routing too
        resp_prefix = client.get("/api/v1/telemetry/traces")
        assert resp_prefix.status_code == 200
        assert len(resp_prefix.json()["traces"]) == 2
