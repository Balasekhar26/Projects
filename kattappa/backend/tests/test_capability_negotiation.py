import pytest
import time
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.ledger.stores.sqlite_store import SQLiteLedgerStore
from backend.core.ledger.stores.memory_store import MemoryLedgerStore
from backend.core.governance.identity_registry import IdentityRegistry
from backend.core.governance.permission_governor import PermissionGovernor
from backend.core.governance.policy_engine import PolicyEngine
from backend.core.governance.safety_monitor import SafetyMonitor
from backend.core.governance.capability_negotiator import (
    CapabilityNegotiator,
    NEGOTIATION_GRANTED,
    ESCALATION_REQUIRED,
    NEGOTIATION_DENIED,
    LEASE_EXPIRED,
)
from backend.core.governance.delegation_token_manager import mint_delegation_token
from backend.core.cos.kernel import KERNEL

@pytest.fixture(params=["sqlite", "memory"])
def store(request):
    if request.param == "sqlite":
        return SQLiteLedgerStore(":memory:")
    return MemoryLedgerStore()


def test_negotiation_by_trust_level(store):
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        
        # 1. High trust principal (trust_level = 3 -> TRUSTED)
        p_trusted = registry.register(name="trusted-agent", principal_type="AGENT", trust_level=3)
        res = CapabilityNegotiator.request_capability(
            principal_id=p_trusted.principal_id,
            capability="CAP_SCREENSHOT",
            reason="Need screen capture for diagnostic report",
            duration_seconds=100
        )
        assert res["status"] == NEGOTIATION_GRANTED
        assert res["contract"]["status"] == "APPROVED"

        # 2. Low trust principal (trust_level = 2 -> LIMITED)
        p_limited = registry.register(name="limited-agent", principal_type="AGENT", trust_level=2)
        res_esc = CapabilityNegotiator.request_capability(
            principal_id=p_limited.principal_id,
            capability="CAP_TERMINAL_EXECUTE",
            reason="Need shell execution to list files",
            duration_seconds=100
        )
        assert res_esc["status"] == ESCALATION_REQUIRED
        assert res_esc["contract"]["status"] == "ESCALATION_REQUIRED"
    finally:
        KERNEL.ledger = old_ledger


def test_negotiation_by_delegation_token(store):
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        p_issuer = registry.register(name="issuer-agent", principal_type="AGENT")
        p_limited = registry.register(name="limited-agent", principal_type="AGENT", trust_level=2)

        # Mint delegation token for CAP_FILE_WRITE
        token = mint_delegation_token(
            trace_id="t_neg",
            capabilities=["CAP_FILE_WRITE"],
            expires_in_minutes=10,
            max_invocations=3,
            allowed_paths=["/tmp"],
            allowed_domains=[],
            issued_by=p_issuer.principal_id,
        )

        # Request capability using delegation token -> Should auto-approve (NEGOTIATION_GRANTED)
        res = CapabilityNegotiator.request_capability(
            principal_id=p_limited.principal_id,
            capability="CAP_FILE_WRITE",
            reason="Save temporary logs",
            duration_seconds=60,
            delegation_token_id=token["token_id"],
        )
        assert res["status"] == NEGOTIATION_GRANTED
    finally:
        KERNEL.ledger = old_ledger


def test_escalation_approval_rejection_and_governor(store):
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        p = registry.register(name="sandbox-agent", principal_type="AGENT", trust_level=1)

        # 1. Static check fails because sandbox-agent does not have CAP_SCREENSHOT
        policy = PolicyEngine()
        safety = SafetyMonitor()
        ok, msg = PermissionGovernor.authorize_action_request(
            agent_name="sandbox-agent",
            tool_name="DESKTOP_SCREENSHOT",
            args={},
            policy=policy,
            safety=safety,
            principal=p
        )
        assert ok is False
        assert msg == "BLOCKED_BY_CAPABILITY_REGISTRY"

        # 2. Negotiate capability -> Escalation Required
        res = CapabilityNegotiator.request_capability(
            principal_id=p.principal_id,
            capability="CAP_SCREENSHOT",
            reason="Diagnostic",
            duration_seconds=500
        )
        contract_id = res["contract_id"]
        assert res["status"] == ESCALATION_REQUIRED

        # Governor still blocks because the contract is not APPROVED yet
        ok, msg = PermissionGovernor.authorize_action_request(
            agent_name="sandbox-agent",
            tool_name="DESKTOP_SCREENSHOT",
            args={},
            policy=policy,
            safety=safety,
            principal=p
        )
        assert ok is False

        # 3. Manually Approve escalation
        approve_res = CapabilityNegotiator.approve_request(contract_id)
        assert approve_res["status"] == NEGOTIATION_GRANTED

        # Governor now allows the request!
        ok_app, msg_app = PermissionGovernor.authorize_action_request(
            agent_name="sandbox-agent",
            tool_name="DESKTOP_SCREENSHOT",
            args={},
            policy=policy,
            safety=safety,
            principal=p
        )
        assert ok_app is True

        # 4. Reject/Revoke contract
        reject_res = CapabilityNegotiator.reject_request(contract_id)
        assert reject_res["status"] == NEGOTIATION_DENIED

        # Governor blocks again
        ok_rej, msg_rej = PermissionGovernor.authorize_action_request(
            agent_name="sandbox-agent",
            tool_name="DESKTOP_SCREENSHOT",
            args={},
            policy=policy,
            safety=safety,
            principal=p
        )
        assert ok_rej is False
    finally:
        KERNEL.ledger = old_ledger


def test_expired_lease_rejection(store):
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        p = registry.register(name="sandbox-agent", principal_type="AGENT", trust_level=1)

        # Request capability with negative duration to simulate immediate expiry
        res = CapabilityNegotiator.request_capability(
            principal_id=p.principal_id,
            capability="CAP_SCREENSHOT",
            reason="Diagnostic",
            duration_seconds=-10
        )
        contract_id = res["contract_id"]
        
        # Approve manually (even though it's already past expires_at)
        approve_res = CapabilityNegotiator.approve_request(contract_id)
        assert approve_res["status"] == LEASE_EXPIRED

        # Get active contracts should list 0 active
        active = CapabilityNegotiator.get_active_contracts(p.principal_id)
        assert len(active) == 0
    finally:
        KERNEL.ledger = old_ledger


def test_negotiation_api_endpoints(store):
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    client = TestClient(app)
    try:
        registry = IdentityRegistry(store)
        p = registry.register(name="api-limited-agent", principal_type="AGENT", trust_level=2)

        # 1. Post negotiation request -> returns escalation required
        response = client.post(
            "/api/v1/governance/negotiate",
            json={
                "principal_id": p.principal_id,
                "capability": "CAP_FILE_WRITE",
                "reason": "Save task progress logs",
                "duration_seconds": 60.0,
            }
        )
        assert response.status_code == 200
        res = response.json()
        assert res["status"] == ESCALATION_REQUIRED
        contract_id = res["contract_id"]

        # 2. Get active contracts list -> count is 0 because not approved yet
        resp_list = client.get(f"/api/v1/governance/contracts?principal_id={p.principal_id}")
        assert resp_list.status_code == 200
        assert resp_list.json()["count"] == 0

        # 3. Post approve contract
        resp_app = client.post(f"/api/v1/governance/contracts/{contract_id}/approve")
        assert resp_app.status_code == 200
        assert resp_app.json()["status"] == NEGOTIATION_GRANTED

        # 4. Get active contracts list -> count is now 1
        resp_list2 = client.get(f"/api/v1/governance/contracts?principal_id={p.principal_id}")
        assert resp_list2.json()["count"] == 1

        # 5. Post reject/revoke contract
        resp_rej = client.post(f"/api/v1/governance/contracts/{contract_id}/reject")
        assert resp_rej.status_code == 200
        assert resp_rej.json()["status"] == NEGOTIATION_DENIED
    finally:
        KERNEL.ledger = old_ledger
