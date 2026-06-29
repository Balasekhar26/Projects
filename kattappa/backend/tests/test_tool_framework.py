"""Unit and integration tests for Program 11: Execution & Tool Framework.
"""
from __future__ import annotations

import time
import pytest
from typing import Dict, Any

from backend.core.execution.tool_models import ToolDefinition, ToolResult
from backend.core.execution.registry import ToolRegistry
from backend.core.execution.capability_matcher import ToolCapabilityMatcher
from backend.core.execution.executor import ToolExecutor
from backend.core.execution.validator import ToolResultValidator
from backend.core.execution.permissions import PermissionManager
from backend.core.execution.scheduler import ToolScheduler
from backend.core.execution.audit import AuditLogger
from backend.core.execution.tool_engine import ToolEngine


def test_tool_registration_and_capability_matching():
    """Verifies that ToolRegistry registers tools and matcher filters by capabilities."""
    registry = ToolRegistry()
    registry.clear()

    tool1 = ToolDefinition(
        name="web_search",
        version="1.0.0",
        description="Search web",
        capabilities=["web", "retrieval"],
    )
    tool2 = ToolDefinition(
        name="file_read",
        version="1.0.0",
        description="Read file",
        capabilities=["file", "read"],
    )

    registry.register_tool(tool1)
    registry.register_tool(tool2)

    matcher = ToolCapabilityMatcher(registry)
    
    # Matches web
    web_matches = matcher.find_matching_tools(["web"])
    assert len(web_matches) == 1
    assert web_matches[0].name == "web_search"

    # Non-existent capability
    assert len(matcher.find_matching_tools(["missing"])) == 0


def test_tool_executor_retries():
    """Verifies that ToolExecutor retries on failures and backoff works."""
    registry = ToolRegistry()
    registry.clear()

    call_count = 0

    def mock_flaky_func(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("Flaky connection issue")
        return {"data": "recovered"}

    flaky_tool = ToolDefinition(
        name="flaky",
        version="1.0.0",
        description="Flaky tool",
        retries=2,
        func=mock_flaky_func,
    )
    registry.register_tool(flaky_tool)

    executor = ToolExecutor(registry)
    result = executor.execute_tool("flaky", {})

    assert result.status == "ok"
    assert result.data == {"data": "recovered"}
    assert call_count == 2


def test_tool_timeout_cancellation():
    """Checks that TimeoutManager interrupts execution if the duration exceeds limits."""
    registry = ToolRegistry()
    registry.clear()

    def slow_func(**kwargs):
        time.sleep(0.5)
        return "done"

    slow_tool = ToolDefinition(
        name="slow",
        version="1.0.0",
        description="Slow tool",
        timeout=0.1,  # Strict timeout limit
        func=slow_func,
    )
    registry.register_tool(slow_tool)

    executor = ToolExecutor(registry)
    result = executor.execute_tool("slow", {})

    assert result.status == "failed"
    assert "timed out" in result.error.lower()


def test_tool_result_schema_validation():
    """Checks that ToolResultValidator rejects outputs not conforming to schema properties."""
    schema = {
        "properties": {
            "status_code": "int",
            "body": "str",
        },
        "required": ["status_code"],
    }

    # Valid data
    valid_data = {"status_code": 200, "body": "ok"}
    assert ToolResultValidator.validate(valid_data, schema) is True

    # Invalid type
    invalid_data = {"status_code": "200"}
    assert ToolResultValidator.validate(invalid_data, schema) is False

    # Missing required field
    missing_data = {"body": "no-status"}
    assert ToolResultValidator.validate(missing_data, schema) is False


def test_permissions_guard():
    """Checks that PermissionManager restricts execution of unauthorized tools."""
    registry = ToolRegistry()
    registry.clear()

    secret_tool = ToolDefinition(
        name="secrets_deletion",
        version="1.0.0",
        description="Deletes keys",
        required_permissions=["delete_credentials"],
        func=lambda: "done",
    )
    registry.register_tool(secret_tool)

    pm = PermissionManager.get_instance()
    # Revoke default if present
    pm.revoke_permission("delete_credentials")

    executor = ToolExecutor(registry, pm)
    result = executor.execute_tool("secrets_deletion", {})
    assert result.status == "failed"
    assert "permission denied" in result.error.lower()

    # Grant permission and try again
    pm.grant_permission("delete_credentials")
    result_ok = executor.execute_tool("secrets_deletion", {})
    assert result_ok.status == "ok"


def test_scheduler_delayed_execution():
    """Checks scheduler registers tasks and triggers them at the correct timing."""
    scheduler = ToolScheduler.get_instance()
    scheduler.queue.clear()

    tracker = []

    def mock_run(name, args):
        tracker.append((name, args))

    scheduler.schedule("task_1", "my_tool", {"arg": 1}, delay_seconds=0.01)
    
    # Not ready yet immediately if delay is evaluated strictly
    scheduler.trigger_ready_tasks(mock_run)
    assert len(tracker) == 0

    # Wait for delay and trigger
    time.sleep(0.015)
    scheduler.trigger_ready_tasks(mock_run)
    assert len(tracker) == 1
    assert tracker[0] == ("my_tool", {"arg": 1})


def test_e2e_tool_engine_orchestration():
    """Integration test: runs complete tool engine loop and logs audit records."""
    engine = ToolEngine.get_instance()
    engine.registry.clear()
    engine.audit.clear()

    test_tool = ToolDefinition(
        name="calc",
        version="1.0.0",
        description="Calculate addition",
        input_schema={
            "properties": {
                "a": "int",
                "b": "int",
            },
            "required": ["a", "b"],
        },
        output_schema={
            "properties": {
                "result": "int",
            },
            "required": ["result"],
        },
        func=lambda a, b: {"result": a + b},
    )
    engine.registry.register_tool(test_tool)


    # Valid execution
    res = engine.execute("calc", {"a": 2, "b": 3})
    assert res.status == "ok"
    assert res.data == {"result": 5}

    # Verify audit logs
    history = engine.audit.get_history()
    assert len(history) == 1
    assert history[0]["tool_name"] == "calc"
    assert history[0]["status"] == "ok"
