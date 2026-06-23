import json
import os
import shutil
import tempfile
import subprocess
import pytest
from pathlib import Path

from backend.core.action_broker import ActionBroker
from backend.core.state import AgentState
from backend.core.execution_policy import PolicyOutcome


@pytest.fixture
def mock_env(monkeypatch):
    """Sets a temporary folder and configures Kattappa test environment."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_broker_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr(ActionBroker, "AUDIT_LOG_PATH", os.path.join(temp_dir, "action_broker_audit.log"))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_action_broker_capability_and_policy_gating(mock_env):
    state: AgentState = {
        "user_input": "Move mouse to 100, 200",
        "logs": [],
    }
    # 1. Blocked: Coder trying to run mouse clicks (DESKTOP_CONTROL -> CAP_MOUSE_MOVE is denied for coder)
    res = ActionBroker.intake_request("coder", "DESKTOP_CONTROL", {}, state)
    assert res["success"] is False
    assert "Security Error" in res["error"]

    # 2. Standard human approval: standard file deletion requires human review
    res_del = ActionBroker.intake_request("coder", "DELETE_FILE", {"target": "dummy.txt"}, state)
    assert res_del["success"] is False
    assert res_del["approval_required"] is True
    assert "human review" in res_del["error"]


def test_double_confirmation_gate(mock_env, monkeypatch):
    # High-risk action: PATCH_CODE requires double confirmation
    state: AgentState = {
        "user_input": "Modify code",
        "logs": [],
    }
    params = {"target": "dummy.py", "code": "def add(a, b): return a + b"}
    
    # 1. Step 1 check: requires step 1 confirmation
    res1 = ActionBroker.intake_request("coder", "PATCH_CODE", params, state)
    assert res1["success"] is False
    assert res1["approval_required"] is True
    assert res1["approval_step"] == 1
    assert "first confirmation" in res1["error"]

    # Apply first approval
    state["approved"] = True
    
    # 2. Step 2 check: requires step 2 double confirmation
    res2 = ActionBroker.intake_request("coder", "PATCH_CODE", params, state)
    assert res2["success"] is False
    assert res2["approval_required"] is True
    assert res2["approval_step"] == 2
    assert "double confirmation" in res2["error"]

    # Apply double approval
    state["double_approved"] = True
    
    # Mock sandbox execution pass
    class MockProcess:
        returncode = 0
        stdout = "all tests passed"
        stderr = ""

    # Monkeypatch to avoid real subprocess and ask_model
    monkeypatch.setattr(ActionBroker, "run_sandboxed_validation", lambda cmd, timeout=15: MockProcess())

    # 3. Success check: after double approval, execution completes successfully
    old_cwd = os.getcwd()
    os.chdir(mock_env)
    try:
        res3 = ActionBroker.intake_request("coder", "PATCH_CODE", params, state)
        assert res3["success"] is True
        assert "review_package" in res3["result"]
        assert res3["result"]["review_package"]["test_results"] == "PASS"
    finally:
        os.chdir(old_cwd)


def test_sandbox_runner_environment_scrubbing(mock_env):
    # Check that sandboxed runner removes secrets from env
    import os
    os.environ["SECRET_API_KEY"] = "mysecret123"
    
    # Run sandbox runner python snippet checking env
    res = ActionBroker.run_sandboxed_validation([
        "python", "-c", "import os; print('API_KEY' in str(os.environ))"
    ])
    assert "True" not in res.stdout
    assert "False" in res.stdout or res.stdout.strip() == ""


def test_rollback_execution(mock_env):
    # Setup test file
    target = mock_env / "calc.py"
    target.write_text("def sub(a, b): return a - b", encoding="utf-8")
    
    # Rollback of existing file restores it
    ActionBroker.execute_rollback(str(target), file_existed_before=True)
    assert target.read_text(encoding="utf-8") == "def sub(a, b): return a - b"

    # Rollback of new file deletes it
    new_file = mock_env / "new.py"
    new_file.write_text("new content", encoding="utf-8")
    ActionBroker.execute_rollback(str(new_file), file_existed_before=False)
    assert not new_file.exists()


def test_immutable_audit_logs(mock_env):
    ActionBroker.log_audit_trail("coder", "PATCH_CODE", "require_human", "double_approved", "Success")
    
    # Verify log entry is written as JSON
    assert os.path.exists(ActionBroker.AUDIT_LOG_PATH)
    with open(ActionBroker.AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
    log_entry = json.loads(lines[0].strip())
    assert log_entry["agent"] == "coder"
    assert log_entry["requested_action"] == "PATCH_CODE"
    assert log_entry["approval_state"] == "double_approved"
