"""Tests for M38: Failure Reason Codes (failure_codes.py + RequestTracer integration)."""
from __future__ import annotations

import pytest
from backend.core.failure_codes import FailureReason, infer_failure_reason
from backend.core.governance.request_tracer import RequestTracer


# ── FailureReason enum ────────────────────────────────────────────────────────

class TestFailureReasonEnum:
    def test_all_values_are_strings(self):
        for member in FailureReason:
            assert isinstance(member.value, str)

    def test_ok_exists(self):
        assert FailureReason.OK == "OK"

    def test_escalation_bypassed_exists(self):
        assert FailureReason.ESCALATION_BYPASSED == "ESCALATION_BYPASSED"

    def test_no_backend_implemented_exists(self):
        assert FailureReason.NO_BACKEND_IMPLEMENTED == "NO_BACKEND_IMPLEMENTED"

    def test_has_at_least_ten_codes(self):
        assert len(list(FailureReason)) >= 10

    def test_enum_comparable_as_string(self):
        assert FailureReason.SAFETY_BLOCKED == "SAFETY_BLOCKED"


# ── infer_failure_reason heuristic ───────────────────────────────────────────

class TestInferFailureReason:
    def test_playwright_missing_returns_dependency_missing(self):
        result = infer_failure_reason(
            "Playwright is not available in this runtime.", agent=None
        )
        assert result == FailureReason.DEPENDENCY_MISSING

    def test_blocked_returns_safety_blocked(self):
        result = infer_failure_reason("Action is blocked by policy.", agent=None)
        assert result == FailureReason.SAFETY_BLOCKED

    def test_approval_returns_approval_pending(self):
        result = infer_failure_reason("Approval required for this action.", agent=None)
        assert result == FailureReason.APPROVAL_PENDING

    def test_context_drift(self):
        result = infer_failure_reason(
            "Kattappa drifted from your latest message — please resend the exact task.",
            agent=None,
        )
        assert result == FailureReason.CONTEXT_DRIFT

    def test_stub_returns_no_backend(self):
        result = infer_failure_reason("not implemented: stub", agent=None)
        assert result == FailureReason.NO_BACKEND_IMPLEMENTED

    def test_empty_string_returns_unknown(self):
        result = infer_failure_reason("", agent=None)
        assert result == FailureReason.UNKNOWN

    def test_successful_result_returns_ok(self):
        result = infer_failure_reason("Here are the files in the directory.", agent="file")
        assert result == FailureReason.OK


# ── RequestTracer.finalize_failure ───────────────────────────────────────────

class TestRequestTracerFinaleFailure:
    def test_finalize_failure_sets_reason(self, capsys):
        tracer = RequestTracer("open calculator", mode="ASSISTANT")
        tracer.finalize_failure(
            FailureReason.NO_BACKEND_IMPLEMENTED,
            detail="desktop stub: no pyautogui backend"
        )
        assert tracer.failure_reason == FailureReason.NO_BACKEND_IMPLEMENTED
        assert tracer.failure_detail == "desktop stub: no pyautogui backend"

    def test_finalize_failure_prints_failure_reason_in_trace(self, capsys):
        tracer = RequestTracer("do something risky", mode="CHAT")
        tracer.finalize_failure(FailureReason.SAFETY_BLOCKED, detail="policy gate")
        captured = capsys.readouterr()
        assert "FAILURE_REASON" in captured.out
        assert "SAFETY_BLOCKED" in captured.out

    def test_finalize_failure_sets_latency(self):
        tracer = RequestTracer("test", mode="CHAT")
        tracer.finalize_failure(FailureReason.OK)
        assert tracer.latency_ms >= 0.0

    def test_finalize_failure_sets_result(self, capsys):
        tracer = RequestTracer("test", mode="CHAT")
        tracer.finalize_failure(FailureReason.TOOL_EXECUTION_ERROR, result="file not found")
        assert tracer.result == "file not found"

    def test_finalize_auto_infers_ok_for_good_result(self, capsys):
        tracer = RequestTracer("list files", mode="ASSISTANT")
        tracer.record_stage(router="file")
        tracer.finalize(result="backend/core/graph.py\nbackend/main.py")
        assert tracer.failure_reason == FailureReason.OK

    def test_finalize_auto_infers_dependency_missing(self, capsys):
        tracer = RequestTracer("open chrome", mode="ASSISTANT")
        tracer.finalize(result="Playwright is not available in this runtime.")
        assert tracer.failure_reason == FailureReason.DEPENDENCY_MISSING

    def test_finalize_auto_infers_safety_blocked(self, capsys):
        tracer = RequestTracer("delete everything", mode="ASSISTANT")
        tracer.finalize(result="Action is blocked by policy.")
        assert tracer.failure_reason == FailureReason.SAFETY_BLOCKED

    def test_trace_output_contains_failure_reason_line(self, capsys):
        tracer = RequestTracer("What is 2+2?", mode="CHAT")
        tracer.finalize(result="4")
        captured = capsys.readouterr()
        assert "FAILURE_REASON:" in captured.out

    def test_escalation_bypassed_detail_shown_in_trace(self, capsys):
        tracer = RequestTracer("hello", mode="CHAT")
        tracer.finalize_failure(
            FailureReason.ESCALATION_BYPASSED,
            detail="RBIL Level 1 → direct_model (no agent graph)",
            result="Hello! How can I help?",
        )
        captured = capsys.readouterr()
        assert "ESCALATION_BYPASSED" in captured.out
        assert "RBIL Level 1" in captured.out
