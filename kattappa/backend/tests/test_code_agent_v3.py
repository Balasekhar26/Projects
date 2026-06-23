import os
import shutil
import tempfile
import subprocess
import pytest
from pathlib import Path

from backend.agents.coder import coder_node, classify_coder_action
from backend.core.action_broker import ActionBroker
is_safe_workspace_path = ActionBroker.is_safe_workspace_path
check_test_weakening = ActionBroker.check_test_weakening
run_command_in_sandbox = ActionBroker.run_sandboxed_validation
analyze_workspace = ActionBroker.analyze_workspace
from backend.core.execution_policy import DEFAULT_POLICY_ENGINE, PolicyOutcome
from backend.core.capability_registry import CapabilityRegistry, CAP_FILE_READ, CAP_FILE_WRITE, CAP_TEST_EXECUTE, CAP_PROPOSAL_CREATE
from backend.core.state import AgentState


@pytest.fixture
def mock_env(monkeypatch):
    """Sets a temporary folder and sets the KATTAPPA_ENV to test."""
    import psutil
    temp_dir = tempfile.mkdtemp(prefix="kattappa_coder_v3_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    
    # Mock psutil to make tests deterministic under heavy host CPU/RAM load
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 10.0)
    class MockVirtualMemory:
        percent = 10.0
        used = 100 * 1024 * 1024
        available = 8 * 1024 * 1024 * 1024
    monkeypatch.setattr(psutil, "virtual_memory", lambda: MockVirtualMemory())
    
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# Action Classification & Capability Tests
# ===========================================================================

def test_classify_coder_action():
    # Install package
    act, _ = classify_coder_action("pip install fastapi")
    assert act == "INSTALL_PACKAGE"
    
    act, _ = classify_coder_action("please run npm install webpack")
    assert act == "INSTALL_PACKAGE"

    # Analyze Repository (Mode 1)
    act, _ = classify_coder_action("please analyze this codebase repo")
    assert act == "ANALYZE_REPO"

    # Create Proposal (Mode 2)
    act, _ = classify_coder_action("create a change proposal for refactoring auth")
    assert act == "CREATE_PROPOSAL"

    # Run tests (Mode 4)
    act, params = classify_coder_action("run tests for backend/tests/test_backend.py")
    assert act == "RUN_TESTS"
    assert params["target"] == "backend/tests/test_backend.py"

    # Benchmarks
    act, _ = classify_coder_action("run benchmark scripts")
    assert act == "RUN_BENCHMARKS"

    # Analyze Code
    act, _ = classify_coder_action("please analyze this file for ast syntax")
    assert act == "ANALYZE_CODE"

    # Generate Patches (Mode 3)
    act, _ = classify_coder_action("modify file main.py to add logging")
    assert act == "PATCH_CODE"
    
    act, _ = classify_coder_action("edit main.py to fix bug")
    assert act == "PATCH_CODE"

    # Create / Write File
    act, _ = classify_coder_action("create file main.py with basic template")
    assert act == "CREATE_FILE"

    # Delete
    act, _ = classify_coder_action("delete file tmp.txt")
    assert act == "DELETE_FILE"


def test_coder_capabilities_evaluation():
    # Coder allowed capabilities
    assert CapabilityRegistry.is_capability_allowed("coder", CAP_FILE_READ) is True
    assert CapabilityRegistry.is_capability_allowed("coder", CAP_FILE_WRITE) is True
    assert CapabilityRegistry.is_capability_allowed("coder", CAP_TEST_EXECUTE) is True
    assert CapabilityRegistry.is_capability_allowed("coder", CAP_PROPOSAL_CREATE) is True

    # Coder denied capabilities
    from backend.core.capability_registry import CAP_MOUSE_MOVE, CAP_WEB_SEARCH
    assert CapabilityRegistry.is_capability_allowed("coder", CAP_MOUSE_MOVE) is False
    assert CapabilityRegistry.is_capability_allowed("coder", CAP_WEB_SEARCH) is False


def test_coder_node_capability_blocks():
    dec = DEFAULT_POLICY_ENGINE.evaluate("DESKTOP_MOUSE_MOVE", agent_name="coder")
    assert dec.outcome is PolicyOutcome.BLOCKED
    assert "lacks required capability" in dec.reason


# ===========================================================================
# Safety Gates: Dependency, Downloads & Budgets
# ===========================================================================

def test_dependency_protection_gate(mock_env):
    state: AgentState = {
        "user_input": "pip install requests",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
    }
    # Should require human approval
    res = coder_node(state)
    assert res.get("approval_required") is True
    assert "requires first confirmation" in res["result"] or "INSTALL_PACKAGE requires" in res["result"]


def test_download_protection_gate(mock_env):
    # Execution of downloaded.py should be blocked
    state: AgentState = {
        "user_input": "python downloaded.py",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
    }
    res = coder_node(state)
    assert "Execution of untrusted downloaded files is strictly prohibited" in res["result"]

    # Execution inside downloads/ folder should be blocked
    state_folder: AgentState = {
        "user_input": "python /path/to/downloads/script.py",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
    }
    res_folder = coder_node(state_folder)
    assert "Execution of untrusted downloaded files is strictly prohibited" in res_folder["result"]


def test_patch_budget_gates(mock_env):
    # Exceeded patches budget
    state_patches: AgentState = {
        "user_input": "Modify main.py to add log",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
        "coder_patches_count": 5,
    }
    res_patches = coder_node(state_patches)
    assert "budget exceeded" in res_patches["result"]

    # Exceeded retries budget
    state_retries: AgentState = {
        "user_input": "Modify main.py to add log",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
        "coder_retries_count": 3,
    }
    res_retries = coder_node(state_retries)
    assert "budget exceeded" in res_retries["result"]

    # Exceeded test cycles budget
    state_test_cycles: AgentState = {
        "user_input": "Modify main.py to add log",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
        "coder_test_cycles_count": 5,
    }
    res_test_cycles = coder_node(state_test_cycles)
    assert "budget exceeded" in res_test_cycles["result"]


# ===========================================================================
# Hardened Safety Layers (Path Traversal, Weakening, Sandbox Exec)
# ===========================================================================

def test_path_traversal_blocking(mock_env):
    # Rel path traversal attempt
    assert is_safe_workspace_path("../outside_file.py", ".") is False
    # Abs path traversal attempt
    assert is_safe_workspace_path("/etc/passwd", ".") is False
    # In-bounds path
    assert is_safe_workspace_path("backend/agents/coder.py", ".") is True

    # Node execution gate check
    state: AgentState = {
        "user_input": "Modify ../outside.py to add hack",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
        "approved": True,
    }
    res = coder_node(state)
    assert "outside the allowed workspace" in res["result"]


def test_test_weakening_blocks_patch():
    # Assertion count decreased
    old_test = "def test_add():\n    assert 1 == 1\n    assert 2 == 2"
    new_test = "def test_add():\n    assert 1 == 1"
    err = check_test_weakening(old_test, new_test)
    assert "assertion count decreased" in err

    # Skips increased
    old_test_2 = "def test_add():\n    assert 1 == 1"
    new_test_2 = "import pytest\n@pytest.mark.skip\ndef test_add():\n    assert 1 == 1"
    err_2 = check_test_weakening(old_test_2, new_test_2)
    assert "skip decorators increased" in err_2


def test_sandbox_exec_blocks_network():
    # Verify macOS sandbox-exec integration blocks network access
    import platform
    if platform.system().lower() == "darwin":
        res = run_command_in_sandbox(["ping", "-c", "1", "google.com"])
        assert res.returncode != 0
        assert "unknown host" in res.stderr.lower() or "cannot resolve" in res.stderr.lower() or "unknown host" in res.stdout.lower()


# ===========================================================================
# Coder Capabilities Modes
# ===========================================================================

def test_repository_analysis_mode(mock_env):
    state: AgentState = {
        "user_input": "Please analyze this codebase repo",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
    }
    res = coder_node(state)
    assert res.get("approval_required") is False
    assert "Repository Analysis Report" in res["result"]


def test_proposal_generation_mode(mock_env, monkeypatch):
    monkeypatch.setattr("backend.agents.coder.ask_model", lambda prompt, role: "Mock Proposal Content")
    state: AgentState = {
        "user_input": "Create a proposal to refactor the database",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
    }
    res = coder_node(state)
    assert res.get("approval_required") is False
    assert "Mock Proposal Content" in res["result"]


# ===========================================================================
# Git Rollback & Test Cycle Loop
# ===========================================================================

def test_mandatory_git_rollback_on_failure(mock_env, monkeypatch):
    called_commands = []

    def mock_run(cmd, *args, **kwargs):
        called_commands.append(cmd)
        # Mock pytest failing (returncode = 1)
        if "pytest" in cmd[0]:
            class MockResult:
                stdout = "test failure"
                stderr = ""
                returncode = 1
            return MockResult()
        class MockResult:
            stdout = ""
            stderr = ""
            returncode = 0
        return MockResult()

    monkeypatch.setattr(ActionBroker, "run_sandboxed_validation", mock_run)
    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr("backend.agents.coder.ask_model", lambda prompt, role: "def add(a, b): return a + b")

    # Set approved flag so modifying action bypasses human approval block
    state: AgentState = {
        "user_input": "Modify calculator.py to add add function",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
        "approved": True,
        "double_approved": True,
    }

    old_cwd = os.getcwd()
    temp_dir = tempfile.mkdtemp()
    os.chdir(temp_dir)
    try:
        # Create target file beforehand
        with open("calculator.py", "w") as f:
            f.write("def sub(a, b): return a - b")

        res = coder_node(state)
        # Validation should fail, modifications rolled back
        assert "Validation failed" in res["result"]
        # Check that git restore command was run
        assert any("restore" in cmd for cmd in called_commands)
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_mandatory_git_commit_on_success(mock_env, monkeypatch):
    called_commands = []

    def mock_run(cmd, *args, **kwargs):
        called_commands.append(cmd)
        # Mock pytest passing (returncode = 0)
        class MockResult:
            stdout = "all tests passed"
            stderr = ""
            returncode = 0
        return MockResult()

    monkeypatch.setattr(ActionBroker, "run_sandboxed_validation", mock_run)
    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr("backend.agents.coder.ask_model", lambda prompt, role: "def add(a, b): return a + b")

    state: AgentState = {
        "user_input": "Modify calculator.py to add add function",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
        "approved": True,
        "double_approved": True,
    }

    old_cwd = os.getcwd()
    temp_dir = tempfile.mkdtemp()
    os.chdir(temp_dir)
    try:
        with open("calculator.py", "w") as f:
            f.write("def sub(a, b): return a - b")

        res = coder_node(state)
        assert "pr_title" in res["result"]  # Checks Review Package format
        assert "pr_description" in res["result"]
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(temp_dir, ignore_errors=True)
