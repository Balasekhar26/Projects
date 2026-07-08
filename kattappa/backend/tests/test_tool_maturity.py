"""Unit and integration tests for Program 11.8: Execution Framework Maturity.
"""
from __future__ import annotations

import time
import pytest
from typing import Dict, Any, List

from backend.core.execution.tool_models import ToolDefinition, ToolResult
from backend.core.execution.tool_engine import ToolEngine
from backend.core.execution.context import ExecutionContext
from backend.core.execution.circuit_breaker import ToolCircuitBreaker, CircuitState
from backend.core.execution.retry_policy import FixedRetryPolicy, LinearRetryPolicy
from backend.core.execution.policy_engine import PolicyEngine, PolicyEffect
from backend.core.execution.events import EventBus, ToolStartedEvent, ToolCompletedEvent


def test_execution_context_propagation():
    """Checks that ExecutionContext custom variables are accessible during runs."""
    engine = ToolEngine.get_instance()
    engine.registry.clear()

    tracker = []

    def mock_func(**kwargs):
        tracker.append("run")
        return {"ok": True}

    tool = ToolDefinition(
        name="ctx_test",
        version="1.0.0",
        description="Test context tool",
        func=mock_func,
    )
    engine.registry.register_tool(tool)

    ctx = ExecutionContext(user_id="user_99", trace_id="trace_77")
    res = engine.execute("ctx_test", {}, context=ctx)
    
    assert res.status == "ok"
    assert len(tracker) == 1


def test_half_open_circuit_breaker_recovery():
    """Checks the transition sequence CLOSED -> OPEN -> HALF-OPEN -> CLOSED (or OPEN)."""
    engine = ToolEngine.get_instance()
    engine.registry.clear()
    
    cb = engine.circuit_breaker
    cb.cooldown = 0.05
    cb.max_probes = 2
    cb.reset("probe_tool")

    fail_probe = True

    def mock_probe(**kwargs):
        if fail_probe:
            raise RuntimeError("Temporary outage")
        return "success"

    tool = ToolDefinition(
        name="probe_tool",
        version="1.0.0",
        description="Probe test tool",
        func=mock_probe,
    )
    engine.registry.register_tool(tool)

    # 1. Force 3 failures to trip OPEN
    for _ in range(3):
        engine.execute("probe_tool", {})

    assert cb.get_state("probe_tool") == CircuitState.OPEN

    # 2. Wait for cooldown -> state transitions to HALF-OPEN
    time.sleep(0.06)
    assert cb.get_state("probe_tool") == CircuitState.HALF_OPEN

    # 3. If probe fails in Half-Open state, retrips circuit back to OPEN immediately
    engine.execute("probe_tool", {})
    assert cb.get_state("probe_tool") == CircuitState.OPEN

    # 4. Wait again for cooldown -> state HALF-OPEN
    time.sleep(0.06)
    assert cb.get_state("probe_tool") == CircuitState.HALF_OPEN

    # 5. Successes transition Half-Open back to CLOSED after max_probes (2) successes
    fail_probe = False
    engine.execute("probe_tool", {})
    assert cb.get_state("probe_tool") == CircuitState.HALF_OPEN
    
    engine.execute("probe_tool", {})
    assert cb.get_state("probe_tool") == CircuitState.CLOSED


def test_retry_policies_durations():
    """Checks fixed and linear retry policies delay calculations."""
    fixed = FixedRetryPolicy(delay=0.15)
    assert fixed.get_delay(1) == 0.15
    assert fixed.get_delay(3) == 0.15

    linear = LinearRetryPolicy(initial_delay=0.05, multiplier=0.02)
    assert linear.get_delay(0) == 0.05
    assert linear.get_delay(2) == 0.09


def test_policy_engine_preflight_denials():
    """Checks that PolicyEngine blocks access based on roles constraints."""
    engine = ToolEngine.get_instance()
    engine.registry.clear()

    policy = PolicyEngine.get_instance()
    policy.deny_rules.append("sensitive_tool")

    tool = ToolDefinition(
        name="sensitive_tool",
        version="1.0.0",
        description="Sensitive data read",
        func=lambda: "data",
    )
    engine.registry.register_tool(tool)

    # Policy DENY pre-flight
    res = engine.execute("sensitive_tool", {})
    assert res.status == "failed"
    assert "policy preflight block" in res.error.lower()


def test_event_bus_lifecycle_notifications():
    """Checks that tool executions notify event bus subscribers."""
    engine = ToolEngine.get_instance()
    engine.registry.clear()

    tool = ToolDefinition(
        name="event_tool",
        version="1.0.0",
        description="Fires events",
        func=lambda: "fired",
    )
    engine.registry.register_tool(tool)

    events_captured = []

    def subscriber(event):
        events_captured.append(event)

    bus = EventBus.get_instance()
    bus.subscribers.clear()
    bus.subscribe(subscriber)

    engine.execute("event_tool", {})
    
    assert len(events_captured) == 2
    assert isinstance(events_captured[0], ToolStartedEvent)
    assert isinstance(events_captured[1], ToolCompletedEvent)
