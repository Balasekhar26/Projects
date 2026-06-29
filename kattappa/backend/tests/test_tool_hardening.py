"""Unit and integration tests for Program 11.5: Tool Framework Production Hardening.
"""
from __future__ import annotations

import asyncio
import time
import pytest
from typing import Dict, Any

from backend.core.execution.tool_models import ToolDefinition, ToolResult
from backend.core.execution.tool_engine import ToolEngine
from backend.core.execution.circuit_breaker import ToolCircuitBreaker
from backend.core.execution.approval import HumanApprovalPipeline
from backend.core.execution.cancellation import CancellationToken
from backend.core.execution.async_dispatcher import AsyncToolDispatcher


def test_tool_circuit_breaker_tripping():
    """Checks that circuit breaker trips after 3 failures, blocking execution, and resets after cooldown."""
    engine = ToolEngine.get_instance()
    engine.registry.clear()
    engine.circuit_breaker.cooldown = 0.2  # Short cooldown for test fast-run
    engine.circuit_breaker.reset("flaky_api")

    def failing_func(**kwargs):
        raise RuntimeError("Network timeout")

    flaky_tool = ToolDefinition(
        name="flaky_api",
        version="1.0.0",
        description="Fails consistently",
        func=failing_func,
    )
    engine.registry.register_tool(flaky_tool)

    # 1. First 2 failures
    res1 = engine.execute("flaky_api", {})
    res2 = engine.execute("flaky_api", {})
    assert res1.status == "failed"
    assert res2.status == "failed"
    assert engine.circuit_breaker.is_available("flaky_api") is True

    # 2. Third failure trips circuit to OPEN
    res3 = engine.execute("flaky_api", {})
    assert res3.status == "failed"
    assert engine.circuit_breaker.is_available("flaky_api") is False

    # 3. Subsequent executions blocked immediately by Open circuit
    res_blocked = engine.execute("flaky_api", {})
    assert res_blocked.status == "failed"
    assert "circuit breaker is open" in res_blocked.error.lower()

    # 4. Wait for cooldown to expire
    time.sleep(0.25)
    assert engine.circuit_breaker.is_available("flaky_api") is True


def test_human_approval_pipeline_locks():
    """Checks that gated tools lock until manual confirmation status is approved or rejected."""
    engine = ToolEngine.get_instance()
    engine.registry.clear()
    engine.approval.requests.clear()

    del_tool = ToolDefinition(
        name="delete_keys",
        version="1.0.0",
        description="Destructive deletion tool",
        required_permissions=["require_approval"],
        func=lambda **kwargs: "deleted",

    )
    engine.registry.register_tool(del_tool)

    # 1. Invoking without request ID raises pending approval
    res_pending = engine.execute("delete_keys", {})
    assert res_pending.status == "failed"
    assert "pending human approval" in res_pending.error.lower()
    
    req_id = res_pending.metadata.get("request_id")
    assert req_id is not None
    assert engine.approval.get_status(req_id) == "pending"

    # 2. Invoking with pending ID still keeps it locked
    res_still_pending = engine.execute("delete_keys", {"request_id": req_id})
    assert res_still_pending.status == "failed"

    # 3. Rejecting request terminates execution
    engine.approval.reject(req_id)
    res_rejected = engine.execute("delete_keys", {"request_id": req_id})
    assert res_rejected.status == "failed"
    assert "rejected" in res_rejected.error.lower()

    # 4. Creating a new request and approving it completes successfully
    res_new = engine.execute("delete_keys", {})
    new_req_id = res_new.metadata.get("request_id")
    
    engine.approval.approve(new_req_id)
    res_approved = engine.execute("delete_keys", {"request_id": new_req_id})
    assert res_approved.status == "ok"
    assert res_approved.data == "deleted"


@pytest.mark.anyio
async def test_async_dispatcher_parallel_runs():
    """Checks that AsyncToolDispatcher executes multiple tools concurrently."""
    engine = ToolEngine.get_instance()
    engine.registry.clear()

    # Reset circuit breaker
    engine.circuit_breaker.reset("sleep_tool")

    def sleep_func(duration: float, **kwargs):
        time.sleep(duration)
        return {"slept": duration}

    sleep_tool = ToolDefinition(
        name="sleep_tool",
        version="1.0.0",
        description="Simulated sleep delay tool",
        func=sleep_func,
    )
    engine.registry.register_tool(sleep_tool)

    dispatcher = AsyncToolDispatcher(engine.executor)
    
    calls = [
        ("sleep_tool", {"duration": 0.05}),
        ("sleep_tool", {"duration": 0.05}),
    ]

    start_t = time.time()
    results = await dispatcher.async_dispatch_parallel(calls)
    duration = time.time() - start_t

    assert len(results) == 2
    assert results[0].status == "ok"
    assert results[1].status == "ok"
    assert results[0].data == {"slept": 0.05}
    # Parallel execution duration should be close to 0.05s, not sequential 0.10s
    assert duration < 0.09


def test_cancellation_token_interrupts():
    """Checks that CancellationToken triggers aborts before execution."""
    engine = ToolEngine.get_instance()
    engine.registry.clear()

    dummy_tool = ToolDefinition(
        name="dummy",
        version="1.0.0",
        description="Simple tool",
        func=lambda: "done",
    )
    engine.registry.register_tool(dummy_tool)

    token = CancellationToken()
    token.cancel()

    res = engine.execute("dummy", {}, cancellation_token=token)
    assert res.status == "failed"
    assert "aborted by cancellation token" in res.error.lower()
