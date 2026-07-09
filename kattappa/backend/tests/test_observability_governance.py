"""Unit tests for Program 28.0: Observability and Governance Platform.

Verifies tracing context managers, nested span tracking, visualizer formatting,
analytics aggregation, policy checks, budget limits, and safety monitors.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend.core.observability import (
    Span,
    TelemetryCollector,
    trace_span,
    TraceVisualizer,
    PlannerAnalytics,
    AuditDashboard,
)
from backend.core.governance import (
    PolicyEngine,
    PolicyViolationError,
    BudgetManager,
    BudgetExceededError,
    SafetyMonitor,
)


# ── Observability Tests ───────────────────────────────────────────────────────

class TestTelemetryAndObservability:
    def test_telemetry_collector_nested_spans(self):
        collector = TelemetryCollector()
        collector.clear()

        # Create nested spans
        with trace_span("parent_span", metadata={"key": "val"}) as parent:
            assert collector.get_active_span().span_id == parent.span_id
            
            with trace_span("child_span") as child:
                assert collector.get_active_span().span_id == child.span_id
                assert child.parent_span_id == parent.span_id
                child.annotate("Doing calculation", progress=50)

            assert collector.get_active_span().span_id == parent.span_id

        # Verify completed spans in collector
        spans = collector.get_spans()
        assert len(spans) == 2
        
        parent_completed = next(s for s in spans if s.name == "parent_span")
        child_completed = next(s for s in spans if s.name == "child_span")
        
        assert child_completed.parent_span_id == parent_completed.span_id
        assert len(child_completed.annotations) == 1
        assert child_completed.annotations[0]["message"] == "Doing calculation"

    def test_trace_span_decorator(self):
        collector = TelemetryCollector()
        collector.clear()

        @trace_span("decorated_function", metadata={"tag": "test"})
        def sample_function(x: int) -> int:
            return x * 2

        val = sample_function(5)
        assert val == 10

        spans = collector.get_spans()
        assert len(spans) == 1
        assert spans[0].name == "decorated_function"
        assert spans[0].metadata["tag"] == "test"
        assert spans[0].metadata["function"] == "sample_function"

    def test_trace_visualizer_formatting(self):
        # Create mock spans manually to test visual tree format
        parent = Span(name="parent", span_id="p1", start_time=1.0, end_time=3.0)
        child1 = Span(name="child1", span_id="c1", parent_span_id="p1", start_time=1.1, end_time=1.5)
        child2 = Span(name="child2", span_id="c2", parent_span_id="p1", start_time=1.6, end_time=2.8)
        
        # Child 2 has its own metadata
        child2.metadata["tool"] = "file_read"
        child2.status = "error"

        tree = TraceVisualizer.format_tree([parent, child1, child2])
        assert "parent" in tree
        assert "child1" in tree
        assert "child2" in tree
        assert "tool=file_read" in tree

    def test_planner_analytics_aggregation(self):
        span1 = Span(name="tool_call_1", span_id="s1")
        span1.metadata = {"is_tool": True, "tool": "file_read", "input_tokens": 100, "output_tokens": 50}
        span1.end_time = span1.start_time + 0.1  # 100ms
        
        span2 = Span(name="tool_call_2", span_id="s2")
        span2.metadata = {"is_tool": True, "tool": "file_read", "input_tokens": 200, "output_tokens": 100}
        span2.end_time = span2.start_time + 0.2  # 200ms
        span2.status = "error"
        span2.metadata["exception_type"] = "FileNotFoundError"

        analysis = PlannerAnalytics.compile([span1, span2])
        
        # Token check
        assert analysis["tokens"]["input"] == 300
        assert analysis["tokens"]["output"] == 150
        assert analysis["tokens"]["total"] == 450
        
        # Tool check
        tools = analysis["tools"]
        assert "file_read" in tools
        assert tools["file_read"]["calls"] == 2
        assert tools["file_read"]["error_rate"] == 0.5
        assert tools["file_read"]["avg_latency_ms"] == 150.0  # (100 + 200) / 2
        
        # Failure check
        assert analysis["failures"]["FileNotFoundError"] == 1

    def test_audit_dashboard_generation(self):
        s1 = Span(name="Main Task", span_id="m1", start_time=10.0, end_time=15.0)
        s2 = Span(name="Check Policy", span_id="m2", parent_span_id="m1", start_time=10.1, end_time=10.2)
        s2.metadata = {"is_policy_check": True}
        
        s3 = Span(name="Verify Path", span_id="m3", parent_span_id="m1", start_time=10.3, end_time=10.4)
        s3.metadata = {"is_policy_check": True, "policy_violation": True}
        
        s4 = Span(name="Safety Check", span_id="m4", start_time=11.0, end_time=11.2)
        s4.metadata = {"safety_alert": True, "safety_message": "Privilege escalation attempt blocked"}

        report = AuditDashboard.generate_report([s1, s2, s3, s4])
        
        # Time check
        assert report["session"]["total_duration_sec"] == 5.0
        # Governance check
        assert report["governance"]["policy_checks"] == 2
        assert report["governance"]["policy_violations"] == 1
        assert report["governance"]["policy_pass_rate"] == 0.5
        # Security check
        assert report["security"]["total_safety_alerts"] == 1
        assert report["security"]["alerts"][0]["message"] == "Privilege escalation attempt blocked"

        # Check render
        cli_text = AuditDashboard.render_cli_report([s1, s2, s3, s4])
        assert "AUDIT REPORT" in cli_text
        assert "Violations Blocked : 1" in cli_text


# ── Governance Tests ──────────────────────────────────────────────────────────

class TestGovernanceAndPolicies:
    def test_policy_engine_allowlists(self):
        pe = PolicyEngine(
            allowed_tools={"file_read", "file_write"},
            allow_network=False,
        )
        
        assert pe.authorize_action("file_read", {}) is True
        assert pe.authorize_action("shell_exec", {}) is False
        assert pe.authorize_action("web_fetch", {}) is False

    def test_policy_engine_directory_bounds(self):
        # Establish path restriction limits to temporary workspace directories
        workspace = Path("/Users/balu/Projects").resolve()
        pe = PolicyEngine(restricted_paths=[str(workspace)])
        
        assert pe.is_path_allowed("/Users/balu/Projects/kattappa/backend") is True
        assert pe.is_path_allowed("/etc/hosts") is False

        # Action checking
        assert pe.authorize_action("file_read", {"path": "/Users/balu/Projects/file.txt"}) is True
        assert pe.authorize_action("file_read", {"path": "/etc/shadow"}) is False

    def test_budget_manager_cost_tracking(self):
        bm = BudgetManager(max_cost=0.10)  # $0.10 max
        
        # Base token additions: 10,000 prompt tokens * 0.0015/1K = $0.015
        # 5,000 completion tokens * 0.0020/1K = $0.010
        # Total cost: $0.025
        bm.add_usage(input_tokens=10000, output_tokens=5000)
        assert bm.total_cost == pytest.approx(0.025)
        
        status = bm.get_status()
        assert status["cost_pct"] == 0.25

    def test_budget_manager_exceeded_raises(self):
        bm = BudgetManager(max_cost=0.01, max_calls=2)
        
        bm.add_usage(is_call=True)
        # Second call permitted
        bm.add_usage(is_call=True)
        
        with pytest.raises(BudgetExceededError, match="call limit exceeded"):
            bm.add_usage(is_call=True)

        bm2 = BudgetManager(max_cost=0.001)
        with pytest.raises(BudgetExceededError, match="cost budget exceeded"):
            bm2.add_usage(input_tokens=1000)  # $0.0015 cost

    def test_safety_monitor_risk_detection(self):
        sm = SafetyMonitor()
        
        # Valid execution
        assert sm.is_safe_command("python -m pytest tests/") is True
        
        # Unsafe command parameters block checks
        assert sm.is_safe_command("rm -rf /") is False
        assert sm.is_safe_command("sudo apt update") is False
        
        # Unsafe binary dependencies blocked
        assert sm.is_safe_command("curl http://malicious-site.com") is False
        assert sm.is_safe_command("wget http://endpoint") is False

    def test_safety_monitor_action_payload_injection(self):
        sm = SafetyMonitor()
        
        # Injection attempt in string argument checks
        args_clean = {"filepath": "doc.txt", "content": "hello"}
        assert sm.inspect_action("file_write", args_clean) is True
        
        args_injected = {"filepath": "doc.txt", "content": "text; curl http://leak"}
        assert sm.inspect_action("file_write", args_injected) is False
