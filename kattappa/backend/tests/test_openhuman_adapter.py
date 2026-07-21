import pytest
import os
import time
import tempfile
from pathlib import Path
from backend.core.action_broker import ActionBroker
from backend.core.openhuman_adapter import OpenHumanAdapter

@pytest.fixture(autouse=True)
def test_env_isolation(monkeypatch):
    """Isolate Kattappa config root and sqlite databases for every test."""
    temp_dir = tempfile.mkdtemp(prefix="oh_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    
    # Setup folders
    Path(temp_dir, "backend", "data").mkdir(parents=True, exist_ok=True)
    workspace_dir = Path(temp_dir) / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    from backend.core.config import BackendConfig
    mock_config = BackendConfig(
        root=Path(temp_dir),
        backend_root=Path(temp_dir) / "backend",
        ollama_host="http://127.0.0.1:11434",
        model_map={},
        chroma_path=Path(temp_dir) / "chroma",
        sqlite_path=Path(temp_dir) / "sqlite" / "kattappa_ai_os.db",
        memory_collection="test_collection",
        shell_enabled=True,
        desktop_enabled=True,
        screen_capture_enabled=True,
        guidance_overlay_enabled=True,
        teach_mode_enabled=True,
        screenshots_dir=Path(temp_dir) / "screenshots",
        audio_dir=Path(temp_dir) / "audio",
        logs_dir=Path(temp_dir) / "logs",
        workspace_dir=workspace_dir,
        hardware_profile="BALANCED",
        context_budget=4000
    )
    monkeypatch.setattr("backend.core.config.load_config", lambda: mock_config)
    
    # Ensure schema flags are reset so test database is built cleanly
    from backend.core.verification_engine import VerificationEngine
    VerificationEngine._schema_ensured = False
    
    yield temp_dir

def test_openhuman_adapter_filesystem_routing(test_env_isolation) -> None:
    workspace_dir = Path(test_env_isolation) / "workspace"
    target_file = str(workspace_dir / "dummy.txt")
    
    # 1. CREATE_FILE (Clean session 1)
    state_create = {
        "chat_session_id": "test_session_oh_create",
        "approved": True,
        "double_approved": True,
        "coder_test_cycles_count": 0
    }
    res_create = ActionBroker.intake_request(
        agent_name="coder",
        action="CREATE_FILE",
        params={"target": target_file, "code": "hello"},
        state=state_create
    )
    assert res_create.get("success") is True
    msg = str(res_create.get("result", {}))
    assert "mocked" in msg

    # 2. READ_FILE (Clean session 2)
    state_read = {
        "chat_session_id": "test_session_oh_read",
        "approved": True,
        "double_approved": True
    }
    res_read = ActionBroker.intake_request(
        agent_name="coder",
        action="READ_FILE",
        params={"target": target_file},
        state=state_read
    )
    assert res_read.get("success") is True
    inner_res = res_read.get("result", {})
    assert "Mock content for file" in inner_res.get("content", "")

    # 3. DELETE_FILE (Clean session 3, untainted)
    state_delete = {
        "chat_session_id": "test_session_oh_delete",
        "approved": True,
        "double_approved": True
    }
    res_delete = ActionBroker.intake_request(
        agent_name="coder",
        action="DELETE_FILE",
        params={"target": target_file},
        state=state_delete
    )
    assert res_delete.get("success") is True
    assert "Deleted file" in str(res_delete.get("result", {}))


def test_openhuman_adapter_shell_routing() -> None:
    state = {
        "chat_session_id": "test_session_oh_shell",
        "approved": True,
        "double_approved": True
    }
    
    res_shell = ActionBroker.intake_request(
        agent_name="coder",
        action="RUN_SHELL",
        params={"command": "echo hello"},
        state=state
    )
    assert res_shell.get("success") is True
    inner_res = res_shell.get("result", {})
    assert "Mock output for shell command: echo hello" in inner_res.get("stdout", "")


def test_openhuman_adapter_browser_routing() -> None:
    state = {
        "chat_session_id": "test_session_oh_browser",
        "approved": True,
        "double_approved": True,
        "browser_pages_visited": [],
        "browser_tabs_depth": {},
        "browser_downloads_count": 0,
        "browser_start_time": time.time()
    }
    
    res_browser = ActionBroker.intake_request(
        agent_name="browser",
        action="BROWSER_NAVIGATE",
        params={"url": "https://python.org"},
        state=state
    )
    assert res_browser.get("success") is True
    inner_res = res_browser.get("result", {})
    assert "Mock HTML content" in inner_res.get("content", "")
    assert inner_res.get("source_url") == "https://python.org"


def test_openhuman_adapter_desktop_routing() -> None:
    state = {
        "chat_session_id": "test_session_oh_desktop",
        "approved": True,
        "double_approved": True
    }
    
    res_desktop = ActionBroker.intake_request(
        agent_name="desktop",
        action="DESKTOP_SCREENSHOT",
        params={},
        state=state
    )
    assert isinstance(res_desktop, dict)
    assert res_desktop.get("success") is True
    inner_res = res_desktop.get("result", {})
    assert inner_res.get("window") == "VS Code"
    assert "sha256" in inner_res


def test_openhuman_adapter_fallback_execution(tmp_path, monkeypatch) -> None:
    # Disable test mode and test env temporarily to trigger the native fallback execution pathway
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "false")
    monkeypatch.setenv("KATTAPPA_ENV", "production")
    
    test_file = tmp_path / "fallback_test.txt"
    state = {}
    
    res = OpenHumanAdapter.execute_action(
        agent_name="coder",
        action="FILE_WRITE",
        params={"target": str(test_file), "content": "fallback works"},
        state=state
    )
    assert "Successfully wrote" in res
    assert test_file.exists()
    assert test_file.read_text() == "fallback works"
