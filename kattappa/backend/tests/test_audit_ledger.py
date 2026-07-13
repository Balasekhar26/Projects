import pytest
import time
import uuid
from fastapi.testclient import TestClient

from backend.core.ledger.stores.sqlite_store import SQLiteLedgerStore
from backend.core.ledger.stores.memory_store import MemoryLedgerStore
from backend.core.governance.identity_registry import (
    IdentityRegistry,
    bootstrap_default_principals,
)
from backend.core.governance.audit_ledger import AuditLedger, GENESIS_HASH
from backend.core.governance.permission_governor import PermissionGovernor
from backend.core.governance.policy_engine import PolicyEngine
from backend.core.governance.safety_monitor import SafetyMonitor
from backend.core.cos.kernel import KERNEL
from backend.main import app

@pytest.fixture(params=["sqlite", "memory"])
def store(request):
    if request.param == "sqlite":
        return SQLiteLedgerStore(":memory:")
    return MemoryLedgerStore()


def test_genesis_hash(store):
    ledger = AuditLedger(store)
    # Empty ledger should return GENESIS_HASH (64 zeroes)
    assert store.get_latest_audit_hash() == GENESIS_HASH


def test_append_and_retrieve(store):
    ledger = AuditLedger(store)
    
    # First entry
    e1 = ledger.log_audit_entry(
        principal_id="PRINCIPAL-SYSTEM",
        action="CAP_FILE_READ",
        arguments={"path": "foo.txt"},
        decision="AUTHORIZED",
        reason="Test genesis run",
    )
    assert e1["previous_hash"] == GENESIS_HASH
    assert e1["entry_hash"] != GENESIS_HASH
    
    # Second entry links to first
    e2 = ledger.log_audit_entry(
        principal_id="PRINCIPAL-HUMAN-DEFAULT",
        action="CAP_FILE_WRITE",
        arguments={"path": "bar.txt"},
        decision="BLOCKED",
        reason="Security policy block",
    )
    assert e2["previous_hash"] == e1["entry_hash"]

    # Retrieve all
    entries = ledger.load_audit_entries()
    assert len(entries) == 2
    assert entries[0]["audit_id"] == e1["audit_id"]
    assert entries[1]["audit_id"] == e2["audit_id"]


def test_chain_validation_success(store):
    ledger = AuditLedger(store)
    for i in range(5):
        ledger.log_audit_entry(
            principal_id="PRINCIPAL-SYSTEM",
            action=f"CAP_ACTION_{i}",
            arguments={"idx": i},
            decision="AUTHORIZED",
            reason=f"Batch {i}",
        )

    valid, reason = ledger.validate_ledger_integrity()
    assert valid is True
    assert reason == ""


def test_chain_validation_failure(store):
    ledger = AuditLedger(store)
    # Add entries
    ledger.log_audit_entry(
        principal_id="PRINCIPAL-SYSTEM",
        action="CAP_FILE_READ",
        arguments={},
        decision="AUTHORIZED",
        reason="One",
    )
    ledger.log_audit_entry(
        principal_id="PRINCIPAL-SYSTEM",
        action="CAP_FILE_WRITE",
        arguments={},
        decision="AUTHORIZED",
        reason="Two",
    )

    # Let's bypass ledger validation by manually tampering with the DB
    if isinstance(store, SQLiteLedgerStore):
        conn = store._get_connection()
        cursor = conn.cursor()
        # Alter the action string of the first record in the database
        cursor.execute("UPDATE audit_log SET action = 'CAP_FILE_DELETE'")
        conn.commit()
        store._close_connection(conn)
    else:
        # Tamper MemoryLedgerStore directly
        store._audit_log[0]["action"] = "CAP_FILE_DELETE"

    # Cryptographic validation should now catch the tampering
    valid, reason = ledger.validate_ledger_integrity()
    assert valid is False
    assert "Hash mismatch" in reason or "Cryptographic link broken" in reason


def test_governor_audit_trigger(store):
    # Setup global KERNEL ledger reference for permission governor
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        bootstrap_default_principals(store)
        registry = IdentityRegistry(store)
        p = registry.get("PRINCIPAL-SYSTEM")

        policy = PolicyEngine()
        safety = SafetyMonitor()

        # Authorize action
        allowed, status = PermissionGovernor.authorize_action_request(
            agent_name="kattappa-system",
            tool_name="CAP_TERMINAL_EXECUTE",
            args={"command": "echo hello"},
            policy=policy,
            safety=safety,
            principal=p,
        )
        
        # Verify that an entry was logged to the store automatically
        ledger = AuditLedger(store)
        entries = ledger.load_audit_entries()
        assert len(entries) >= 1
        last_entry = entries[-1]
        assert last_entry["principal_id"] == "PRINCIPAL-SYSTEM"
        assert last_entry["action"] == "CAP_TERMINAL_EXECUTE"
        assert last_entry["decision"] == "AUTHORIZED" if allowed else "BLOCKED"
    finally:
        KERNEL.ledger = old_ledger


def test_api_endpoints(store):
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        client = TestClient(app)
        
        # Log a record via Python API
        ledger = AuditLedger(store)
        ledger.log_audit_entry(
            principal_id="PRINCIPAL-SYSTEM",
            action="CAP_FILE_READ",
            arguments={"path": "api.txt"},
            decision="AUTHORIZED",
            reason="API Test Check",
        )

        # 1. Test logs retrieval
        response = client.get("/api/v1/audit/logs")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["logs"]) >= 1

        # Test filters
        response = client.get("/api/v1/audit/logs?decision=AUTHORIZED")
        assert len(response.json()["logs"]) >= 1

        response = client.get("/api/v1/audit/logs?decision=BLOCKED")
        assert len(response.json()["logs"]) == 0

        # 2. Test cryptographic verification
        response = client.get("/api/v1/audit/verify")
        assert response.status_code == 200
        verify_data = response.json()
        assert verify_data["status"] == "success"
        assert verify_data["valid"] is True
    finally:
        KERNEL.ledger = old_ledger
