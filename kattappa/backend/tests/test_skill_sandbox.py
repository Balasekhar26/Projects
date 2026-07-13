import os
import json
import pytest
from backend.core.governance.sandbox_allocator import allocate_sandbox_and_run

PROBE_SCRIPT = os.path.abspath("test_sandbox_probe.py")
WORKSPACE = os.path.abspath(".")


def make_skill(**overrides) -> dict:
    base = {
        "name": "test.probe",
        "entrypoint": PROBE_SCRIPT,
        "timeout_seconds": 10,
        "sandbox_type": "subprocess",
        "max_memory_mb": None,
        "allow_network": False,
        "allowed_paths": [],
    }
    base.update(overrides)
    return base


def test_sandbox_basic_echo():
    """Sanity check: sandbox can execute a basic script."""
    skill = make_skill()
    result = allocate_sandbox_and_run(skill, {"action": "echo", "msg": "hello"})
    assert result["status"] == "success"
    assert result["result"]["status"] == "processed"


def test_sandbox_filesystem_restriction():
    """Files outside allowed_paths should be denied."""
    # Only allow workspace directory
    skill = make_skill(allowed_paths=[WORKSPACE])
    
    # Try to read a file outside allowed_paths (Windows system dir)
    blocked_path = r"C:\Windows\system32\drivers\etc\hosts"
    result = allocate_sandbox_and_run(skill, {"action": "read_blocked_file", "path": blocked_path})
    # The sandbox script catches PermissionError and reports it
    assert result["status"] == "success"
    assert result["result"]["status"] == "blocked"
    assert "blocked" in result["result"]["reason"].lower() or "denied" in result["result"]["reason"].lower()


def test_sandbox_filesystem_allowed():
    """Files inside allowed_paths should succeed."""
    # Create a temp file in workspace to read
    tmp_file = os.path.join(WORKSPACE, "sandbox_test_readable.txt")
    with open(tmp_file, "w") as f:
        f.write("hello sandbox")
    
    try:
        skill = make_skill(allowed_paths=[WORKSPACE])
        result = allocate_sandbox_and_run(skill, {"action": "read_blocked_file", "path": tmp_file})
        assert result["status"] == "success"
        assert result["result"]["status"] == "read_success"
        assert "hello sandbox" in result["result"]["content"]
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)


def test_sandbox_network_blocked():
    """Network connections should be blocked when allow_network=False."""
    skill = make_skill(allow_network=False)
    result = allocate_sandbox_and_run(skill, {"action": "connect_network"})
    assert result["status"] == "success"
    assert result["result"]["status"] == "blocked"


def test_sandbox_timeout_enforcement():
    """Execution exceeding timeout should return an error."""
    skill = make_skill(timeout_seconds=1)
    result = allocate_sandbox_and_run(skill, {"action": "allocate_memory", "target_mb": 5})
    # Script sleeps 2s; with 1s timeout it should be killed
    assert result["status"] == "error"
    assert "timed out" in result["error_message"].lower()


def test_sandbox_memory_limit():
    """Execution exceeding memory limit should be terminated."""
    # Limit to 5 MB, script will try to allocate 50 MB
    skill = make_skill(max_memory_mb=5, timeout_seconds=10)
    result = allocate_sandbox_and_run(skill, {"action": "allocate_memory", "target_mb": 50})
    assert result["status"] == "error"
    assert "memory limit" in result["error_message"].lower()
