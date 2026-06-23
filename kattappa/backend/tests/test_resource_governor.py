import os
import shutil
import tempfile
import json
import pytest
from pathlib import Path

from backend.core.resource_governor import ResourceGovernor
from backend.core.action_broker import ActionBroker
from backend.core.model_router import ask_model
from backend.core.state import AgentState


@pytest.fixture
def mock_env(monkeypatch):
    """Sets a temporary folder for resource governance metrics."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_gov_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    ResourceGovernor.reset()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


class MockVirtualMemory:
    def __init__(self, available):
        self.available = available


def test_cpu_limit_exceeded(mock_env, monkeypatch):
    # Mock CPU percent to 95.0% (limit is 90.0%)
    import psutil
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 95.0)
    
    res = ResourceGovernor.check_and_charge_resources("coder", "READ_FILE", {"path": "dummy.txt"})
    assert res["success"] is False
    assert "CPU usage is too high" in res["error"]

    # Also verify ActionBroker blocks it
    state: AgentState = {"user_input": "Read dummy.txt", "logs": []}
    broker_res = ActionBroker.intake_request("coder", "READ_FILE", {"path": "dummy.txt"}, state)
    assert broker_res["success"] is False
    assert "Resource Error" in broker_res["error"]


def test_ram_limit_exceeded(mock_env, monkeypatch):
    # Mock available RAM to 400 MB (limit min is 500 MB)
    import psutil
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 20.0)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: MockVirtualMemory(400 * 1024 * 1024))

    res = ResourceGovernor.check_and_charge_resources("coder", "READ_FILE", {"path": "dummy.txt"})
    assert res["success"] is False
    assert "Available RAM is too low" in res["error"]

    # Also verify ActionBroker blocks it
    state: AgentState = {"user_input": "Read dummy.txt", "logs": []}
    broker_res = ActionBroker.intake_request("coder", "READ_FILE", {"path": "dummy.txt"}, state)
    assert broker_res["success"] is False
    assert "Resource Error" in broker_res["error"]


def test_disk_quota_exceeded(mock_env, monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 20.0)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: MockVirtualMemory(16 * 1024 * 1024 * 1024))

    # Set disk usage close to limit (limit is 100MB = 104,857,600 bytes)
    # Mock _load to return high usage
    data = {
        "disk_used_bytes": 100 * 1024 * 1024 - 100,  # only 100 bytes left
        "network_download_bytes": 0,
        "network_requests": 0,
        "tokens_used": 0,
        "concurrent_tasks": 0
    }
    monkeypatch.setattr(ResourceGovernor, "_load", lambda: data)

    # Attempt to write 200 bytes should fail
    res = ResourceGovernor.check_and_charge_resources("coder", "WRITE_FILE", {"path": "dummy.txt", "content": "x" * 200})
    assert res["success"] is False
    assert "Disk quota exceeded" in res["error"]


def test_network_requests_limit(mock_env, monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 20.0)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: MockVirtualMemory(16 * 1024 * 1024 * 1024))

    data = {
        "disk_used_bytes": 0,
        "network_download_bytes": 0,
        "network_requests": 100,  # at limit
        "tokens_used": 0,
        "concurrent_tasks": 0
    }
    monkeypatch.setattr(ResourceGovernor, "_load", lambda: data)

    res = ResourceGovernor.check_and_charge_resources("browser", "BROWSER_SEARCH", {"query": "test"})
    assert res["success"] is False
    assert "Network requests limit reached" in res["error"]


def test_tokens_budget_limit(mock_env, monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 20.0)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: MockVirtualMemory(16 * 1024 * 1024 * 1024))

    data = {
        "disk_used_bytes": 0,
        "network_download_bytes": 0,
        "network_requests": 0,
        "tokens_used": 49990,  # 10 tokens left (limit is 50,000)
        "concurrent_tasks": 0
    }
    monkeypatch.setattr(ResourceGovernor, "_load", lambda: data)

    # Ask model with input estimated to be 20 tokens should be blocked
    res = ask_model("This prompt is long and takes more than 10 tokens.")
    assert "Error: System token budget exceeded." in res


def test_concurrent_tasks_limit(mock_env, monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 20.0)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: MockVirtualMemory(16 * 1024 * 1024 * 1024))

    data = {
        "disk_used_bytes": 0,
        "network_download_bytes": 0,
        "network_requests": 0,
        "tokens_used": 0,
        "concurrent_tasks": 5  # at limit
    }
    monkeypatch.setattr(ResourceGovernor, "_load", lambda: data)

    res = ResourceGovernor.check_and_charge_resources("coder", "RUN_SHELL", {})
    assert res["success"] is False
    assert "Concurrent task limit reached" in res["error"]
