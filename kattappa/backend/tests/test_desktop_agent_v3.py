import os
import shutil
import tempfile
import json
import pytest
from pathlib import Path

from backend.agents.desktop import desktop_node, classify_desktop_action
from backend.core.state import AgentState


@pytest.fixture
def mock_env(monkeypatch):
    """Sets a temporary folder for files and log databases."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_desktop_v3_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.tools.desktop_tools.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.agents.desktop.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    import psutil
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 10.0)
    class MockVM:
        percent = 20.0
        used = 1024 * 1024
        available = 8 * 1024 * 1024 * 1024
    monkeypatch.setattr(psutil, "virtual_memory", lambda: MockVM())
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


def _get_audit_logs(mock_env_path: Path) -> list[dict]:
    log_file = mock_env_path / "backend" / "data" / "desktop_audit.log"
    if not log_file.exists():
        return []
    logs = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                logs.append(json.loads(line.strip()))
    return logs


# ===========================================================================
# Capability Tests
# ===========================================================================

def test_open_approved_app(mock_env):
    state: AgentState = {
        "user_input": "Open app VS Code",
        "logs": [],
    }
    res = desktop_node(state)
    assert res.get("approval_required") is False
    assert "opened" in res["result"]


def test_block_protected_app(mock_env):
    state: AgentState = {
        "user_input": "Open app Keychain",
        "logs": [],
    }
    # Open Keychain should raise PermissionError or be blocked by policy
    res = desktop_node(state)
    assert "strictly prohibited" in res["result"]


def test_move_mouse(mock_env):
    state: AgentState = {
        "user_input": "Move mouse to 200, 300",
        "logs": [],
    }
    res = desktop_node(state)
    assert res.get("approval_required") is False
    assert "moved mouse" in res["result"]


def test_click_target(mock_env):
    state: AgentState = {
        "user_input": "Click at 150, 250",
        "logs": [],
    }
    res = desktop_node(state)
    assert res.get("approval_required") is False
    assert "clicked" in res["result"]


def test_type_text(mock_env):
    state: AgentState = {
        "user_input": "Type text 'Hello Kattappa'",
        "logs": [],
    }
    res = desktop_node(state)
    assert res.get("approval_required") is False
    assert "typed" in res["result"]


def test_read_screen(mock_env):
    state: AgentState = {
        "user_input": "Read screen contents",
        "logs": [],
    }
    res = desktop_node(state)
    assert res.get("approval_required") is False
    assert "provenance_data" in res
    assert res["provenance_data"]["provenance"] == "UNTRUSTED_UI_DATA"


def test_screenshot_creation(mock_env):
    state: AgentState = {
        "user_input": "Take screenshot",
        "logs": [],
    }
    res = desktop_node(state)
    assert res.get("approval_required") is False
    assert "provenance_data" in res
    assert "sha256" in res["provenance_data"]


# ===========================================================================
# Safety Tests
# ===========================================================================

def test_delete_action_requires_approval(mock_env):
    state: AgentState = {
        "user_input": "Delete file source.py",
        "logs": [],
    }
    res = desktop_node(state)
    assert res.get("approval_required") is True
    assert "Approval needed" in res["result"]


def test_protected_directory_blocked(mock_env):
    state: AgentState = {
        "user_input": "Delete file ~/.ssh/id_rsa",
        "logs": [],
    }
    res = desktop_node(state)
    assert "strictly prohibited" in res["result"]
    assert res.get("approval_required") is False


def test_protected_application_blocked(mock_env):
    # Keyboard typing inside protected app should trigger block
    state: AgentState = {
        "user_input": "Open app LastPass",
        "logs": [],
    }
    res = desktop_node(state)
    assert "strictly prohibited" in res["result"]


def test_password_typing_blocked(mock_env):
    state: AgentState = {
        "user_input": "Type text password='mysecretpassword123'",
        "logs": [],
    }
    res = desktop_node(state)
    assert "blocked: Typing or pasting secrets" in res["result"]


def test_shutdown_requires_approval(mock_env):
    state: AgentState = {
        "user_input": "Shutdown system now",
        "logs": [],
    }
    res = desktop_node(state)
    assert res.get("approval_required") is True
    assert "Approval needed" in res["result"]


# ===========================================================================
# Audit Tests
# ===========================================================================

def test_screenshot_logged(mock_env):
    state: AgentState = {
        "user_input": "Take screenshot",
        "logs": [],
    }
    desktop_node(state)
    logs = _get_audit_logs(mock_env)
    assert len(logs) > 0
    screenshot_entry = next((log for log in logs if log["category"] == "screenshot"), None)
    assert screenshot_entry is not None
    assert "sha256" in screenshot_entry["details"]


def test_mouse_actions_logged(mock_env):
    state: AgentState = {
        "user_input": "Click at 100, 200",
        "logs": [],
    }
    desktop_node(state)
    logs = _get_audit_logs(mock_env)
    assert len(logs) > 0
    click_entry = next((log for log in logs if log["category"] == "mouse" and log["action"] == "click"), None)
    assert click_entry is not None
    assert click_entry["details"]["x_norm"] == 100.0


def test_keyboard_actions_logged(mock_env):
    state: AgentState = {
        "user_input": "Type text 'hello'",
        "logs": [],
    }
    desktop_node(state)
    logs = _get_audit_logs(mock_env)
    assert len(logs) > 0
    keyboard_entry = next((log for log in logs if log["category"] == "keyboard" and log["action"] == "type_text"), None)
    assert keyboard_entry is not None
    assert keyboard_entry["details"]["text"] == "hello"
