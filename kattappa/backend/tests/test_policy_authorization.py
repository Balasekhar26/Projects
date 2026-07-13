import uuid
import pytest
import sqlite3
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.cos.kernel import KERNEL
from backend.core.governance.permission_governor import PermissionGovernor
from backend.core.governance.policy_engine import PolicyEngine
from backend.core.governance.safety_monitor import SafetyMonitor
from backend.core.observability.telemetry import trace_span


def test_sqlite_receipt_immutability():
    # Attempt to update or delete a receipt directly in SQLite, asserting failure
    db_conn = KERNEL.ledger._get_connection()
    try:
        cursor = db_conn.cursor()
        
        action_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        
        # Insert works
        cursor.execute(
            """
            INSERT INTO execution_receipts (
                action_id, capability, authorized_by, approval_scope, timestamp_utc, trace_id, span_id
            ) VALUES (?, ?, ?, ?, 123.45, ?, ?)
        """,
            (action_id, "CAP_FILE_READ", "policy_bypass", "auto", trace_id, span_id),
        )
        db_conn.commit()
        
        # Update fails (IntegrityError is raised for trigger raise)
        with pytest.raises(sqlite3.IntegrityError, match="Updates to execution_receipts are prohibited"):
            cursor.execute(
                "UPDATE execution_receipts SET capability = 'CAP_FILE_WRITE' WHERE action_id = ?",
                (action_id,),
            )
            db_conn.commit()
            
        # Delete fails
        with pytest.raises(sqlite3.IntegrityError, match="Deletions from execution_receipts are prohibited"):
            cursor.execute(
                "DELETE FROM execution_receipts WHERE action_id = ?",
                (action_id,),
            )
            db_conn.commit()
    finally:
        db_conn.close()


def test_permission_governor_gating_and_receipts():
    policy = PolicyEngine(allow_network=True)
    safety = SafetyMonitor()
    
    # 1. auto policy (L1) - CAP_FILE_READ maps to L1, auto
    # Start span to establish trace context
    with trace_span("test-read-span") as active_span:
        ok, status = PermissionGovernor.authorize_action_request(
            agent_name="file",
            tool_name="READ_FILE",
            args={"path": "some_test_file.txt"},
            policy=policy,
            safety=safety
        )
        assert ok is True
        assert status == "AUTHORIZED"
        
        # Verify receipt exists in SQLite
        receipts = KERNEL.ledger.get_execution_receipts(active_span.trace_id)
        assert len(receipts) == 1
        assert receipts[0]["capability"] == "CAP_FILE_READ"
        assert receipts[0]["authorized_by"] == "policy_bypass"
        assert receipts[0]["approval_scope"] == "auto"

    # 2. always policy (L4) - CAP_FILE_DELETE maps to L4, always
    with trace_span("test-delete-span"):
        ok, status = PermissionGovernor.authorize_action_request(
            agent_name="file",
            tool_name="DELETE_FILE",
            args={"path": "some_test_file.txt"},
            policy=policy,
            safety=safety
        )
        assert ok is False
        assert status == "REQUIRES_APPROVAL"


def test_receipts_endpoint():
    client = TestClient(app)
    
    trace_id = str(uuid.uuid4())
    span_id = str(uuid.uuid4())
    action_id = str(uuid.uuid4())
    
    # Log directly via ledger
    KERNEL.ledger.record_execution_receipt(
        action_id=action_id,
        capability="CAP_SCREEN_READ",
        authorized_by="policy_bypass",
        approval_scope="auto",
        trace_id=trace_id,
        span_id=span_id,
    )
    
    # Query API endpoint
    response = client.get(f"/api/v1/telemetry/receipts/{trace_id}")
    assert response.status_code == 200
    receipts = response.json()
    assert len(receipts) == 1
    assert receipts[0]["action_id"] == action_id
    assert receipts[0]["capability"] == "CAP_SCREEN_READ"
