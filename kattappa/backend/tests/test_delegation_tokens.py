import time
import uuid
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.cos.kernel import KERNEL
from backend.core.governance.delegation_token_manager import (
    mint_delegation_token,
    validate_token_capability,
)
from backend.core.governance.permission_governor import PermissionGovernor
from backend.core.governance.policy_engine import PolicyEngine
from backend.core.governance.safety_monitor import SafetyMonitor
from backend.core.observability.telemetry import trace_span


def test_delegation_token_lifecycle():
    trace_id = str(uuid.uuid4())
    
    # 1. Mint delegation token
    token = mint_delegation_token(
        trace_id=trace_id,
        capabilities=["CAP_FILE_READ", "CAP_FILE_WRITE"],
        expires_in_minutes=10,
        max_invocations=3,
        allowed_paths=["C:\\Users\\balu\\Projects\\kattappa\\workspace"],
        allowed_domains=["github.com"],
        issued_by="user",
    )
    token_id = token["token_id"]
    assert token_id.startswith("DTK-")
    assert token["status"] == "ACTIVE"
    
    # Verify retrieval
    retrieved = KERNEL.ledger.get_delegation_token(token_id)
    assert retrieved is not None
    assert retrieved["max_invocations"] == 3
    
    # 2. Check capability matching
    # Valid
    ok, status = validate_token_capability(token_id, "CAP_FILE_READ")
    assert ok is True
    assert status == "AUTHORIZED"
    
    # Invalid capability
    ok, status = validate_token_capability(token_id, "CAP_TERMINAL_EXECUTE")
    assert ok is False
    assert "not allowed" in status

    # 3. Check path constraints
    # Valid target path
    ok, status = validate_token_capability(
        token_id,
        "CAP_FILE_WRITE",
        target="C:\\Users\\balu\\Projects\\kattappa\\workspace\\some_file.txt",
    )
    assert ok is True
    assert status == "AUTHORIZED"

    # Invalid path
    ok, status = validate_token_capability(
        token_id,
        "CAP_FILE_WRITE",
        target="C:\\Windows\\system32\\cmd.exe",
    )
    assert ok is False
    assert "resides outside allowed path" in status

    # 4. Check invocation exhaustion
    # Invocations spent so far in test: 2 successful validations (first read + first write path).
    # Next successful invocation (3rd):
    ok, status = validate_token_capability(token_id, "CAP_FILE_READ")
    assert ok is True
    # The status updates to EXHAUSTED after hitting maximum limit (3)
    retrieved = KERNEL.ledger.get_delegation_token(token_id)
    assert retrieved["status"] == "EXHAUSTED"

    # 4th invocation fails
    ok, status = validate_token_capability(token_id, "CAP_FILE_READ")
    assert ok is False
    assert "EXHAUSTED" in status


def test_delegation_token_expiration():
    trace_id = str(uuid.uuid4())
    
    # Mint token with 0 expiration (expires immediately)
    token = mint_delegation_token(
        trace_id=trace_id,
        capabilities=["CAP_FILE_READ"],
        expires_in_minutes=-1,  # past expiry
        max_invocations=5,
        allowed_paths=[],
        allowed_domains=[],
    )
    token_id = token["token_id"]
    
    # Validate fails
    ok, status = validate_token_capability(token_id, "CAP_FILE_READ")
    assert ok is False
    assert "expired" in status


def test_governor_delegation_integration():
    policy = PolicyEngine()
    safety = SafetyMonitor()
    trace_id = str(uuid.uuid4())
    
    # Mint token for CAP_FILE_DELETE (which normally maps to L4, always prompts)
    token = mint_delegation_token(
        trace_id=trace_id,
        capabilities=["CAP_FILE_DELETE"],
        expires_in_minutes=10,
        max_invocations=2,
        allowed_paths=["C:\\Users\\balu\\Projects\\kattappa\\workspace"],
        allowed_domains=[],
    )
    token_id = token["token_id"]
    
    # Run request through Governor supplying the delegation_token_id
    with trace_span("delegation-test-span") as active_span:
        ok, status = PermissionGovernor.authorize_action_request(
            agent_name="file",
            tool_name="DELETE_FILE",
            args={
                "path": "C:\\Users\\balu\\Projects\\kattappa\\workspace\\target_delete.txt",
                "delegation_token_id": token_id,
            },
            policy=policy,
            safety=safety,
        )
        assert ok is True
        assert status == "AUTHORIZED"
        
        # Verify receipt has been generated with delegation_token mapping
        receipts = KERNEL.ledger.get_execution_receipts(active_span.trace_id)
        assert len(receipts) == 1
        assert "delegation_token" in receipts[0]["authorized_by"]
        assert receipts[0]["approval_scope"] == "token_constraints"


def test_delegation_token_endpoints():
    client = TestClient(app)
    trace_id = str(uuid.uuid4())
    
    # 1. Mint token via endpoint
    response = client.post(
        "/api/v1/telemetry/delegation/token",
        json={
            "trace_id": trace_id,
            "capabilities": ["CAP_SCREEN_READ"],
            "expires_in_minutes": 20,
            "max_invocations": 5,
            "allowed_paths": [],
            "allowed_domains": ["google.com"],
        }
    )
    assert response.status_code == 200
    token_id = response.json()["token_id"]
    
    # 2. Query token details via endpoint
    response = client.get(f"/api/v1/telemetry/delegation/token/{token_id}")
    assert response.status_code == 200
    token = response.json()
    assert token["token_id"] == token_id
    assert "CAP_SCREEN_READ" in token["capabilities"]
