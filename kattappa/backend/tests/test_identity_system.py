import pytest
import time
import uuid
import warnings
import threading
from fastapi.testclient import TestClient

from backend.core.ledger.stores.sqlite_store import SQLiteLedgerStore
from backend.core.ledger.stores.memory_store import MemoryLedgerStore
from backend.core.governance.identity_registry import (
    IdentityRegistry,
    Principal,
    PrincipalValidationError,
    bootstrap_default_principals,
    PRINCIPAL_SYSTEM,
    PRINCIPAL_HUMAN_DEFAULT,
)
from backend.core.governance.permission_governor import PermissionGovernor
from backend.core.governance.policy_engine import PolicyEngine
from backend.core.governance.safety_monitor import SafetyMonitor
from backend.core.governance.goal_lifecycle import GoalLifecycleGovernor, GoalStatus
from backend.core.governance.delegation_token_manager import mint_delegation_token, validate_token_capability
from backend.core.cos.kernel import KERNEL
from backend.main import app

# Parametrize over SQLiteStore and MemoryStore backends
@pytest.fixture(params=["sqlite", "memory"])
def store(request):
    if request.param == "sqlite":
        # Shared connection in-memory sqlite store
        store_obj = SQLiteLedgerStore(":memory:")
    else:
        store_obj = MemoryLedgerStore()
    return store_obj


def test_principal_registration(store):
    registry = IdentityRegistry(store)

    # 1. Successful registration with numeric trust
    p = registry.register(
        name="test-agent",
        principal_type="AGENT",
        trust_level=2,
        capabilities=["CAP_FILE_READ", "CAP_FILE_WRITE"],
        metadata={"role": "worker"},
    )
    assert p.principal_id.startswith("PRINCIPAL-")
    assert p.name == "test-agent"
    assert p.principal_type == "AGENT"
    assert p.trust_level == 2
    assert "CAP_FILE_READ" in p.capabilities
    assert p.metadata["role"] == "worker"
    assert p.is_active is True
    assert p.status == "ACTIVE"
    assert p.expires_at is None

    # Retrieve by ID
    p2 = registry.get(p.principal_id)
    assert p2 is not None
    assert p2.name == "test-agent"

    # Retrieve by name
    p3 = registry.resolve("test-agent")
    assert p3 is not None
    assert p3.principal_id == p.principal_id


def test_invalid_registration(store):
    registry = IdentityRegistry(store)

    # Invalid type
    with pytest.raises(PrincipalValidationError, match="Invalid principal_type"):
        registry.register(name="bad-type", principal_type="alien")

    # Invalid trust level
    with pytest.raises(PrincipalValidationError, match="trust_level must be 0–5"):
        registry.register(name="bad-trust", principal_type="human", trust_level=9)

    # Invalid status
    with pytest.raises(PrincipalValidationError, match="Invalid status"):
        registry.register(name="bad-status", principal_type="human", status="TERMINATED")


def test_string_trust_levels(store):
    registry = IdentityRegistry(store)

    # String trust mapping tests
    p_sys = registry.register(name="sys-user", principal_type="human", trust_level="SYSTEM")
    assert p_sys.trust_level == 5

    p_trusted = registry.register(name="trusted-user", principal_type="human", trust_level="TRUSTED")
    assert p_trusted.trust_level == 3

    p_limited = registry.register(name="limited-user", principal_type="human", trust_level="LIMITED")
    assert p_limited.trust_level == 2

    p_sandboxed = registry.register(name="sandboxed-user", principal_type="human", trust_level="SANDBOXED")
    assert p_sandboxed.trust_level == 1

    p_untrusted = registry.register(name="untrusted-user", principal_type="human", trust_level="UNTRUSTED")
    assert p_untrusted.trust_level == 0

    p_revoked = registry.register(name="revoked-user", principal_type="human", trust_level="REVOKED")
    assert p_revoked.trust_level == -1


def test_unique_name_constraint(store):
    registry = IdentityRegistry(store)
    registry.register(name="unique-name", principal_type="AGENT")

    if isinstance(store, SQLiteLedgerStore):
        # sqlite will IGNORE the insert since create_principal uses INSERT OR IGNORE
        # resolved name should still point to first agent
        p2 = registry.register(name="unique-name", principal_type="HUMAN", trust_level=4)
        resolved = registry.resolve("unique-name")
        assert resolved.principal_type == "AGENT"
    else:
        pass


def test_deactivation_reactivation_and_lifecycle(store):
    registry = IdentityRegistry(store)
    p = registry.register(name="active-agent", principal_type="AGENT")
    assert p.is_active is True
    assert p.status == "ACTIVE"

    # Require active principal succeeds
    assert registry.require(p.principal_id) is not None

    # Suspend
    registry.suspend(p.principal_id)
    p_sus = registry.get(p.principal_id)
    assert p_sus.is_active is False
    assert p_sus.status == "SUSPENDED"

    with pytest.raises(PermissionError, match="suspended"):
        registry.require(p.principal_id)

    # Revoke
    registry.revoke(p.principal_id)
    p_rev = registry.get(p.principal_id)
    assert p_rev.is_active is False
    assert p_rev.status == "REVOKED"

    with pytest.raises(PermissionError, match="revoked"):
        registry.require(p.principal_id)

    # Reactivate
    registry.reactivate(p.principal_id)
    p_react = registry.get(p.principal_id)
    assert p_react.is_active is True
    assert p_react.status == "ACTIVE"


def test_principal_expiry(store):
    registry = IdentityRegistry(store)
    past_time = time.time() - 10
    p_expired = registry.register(name="expired-agent", principal_type="AGENT", expires_at=past_time)
    
    assert p_expired.can_authorize(1) is False

    with pytest.raises(PermissionError, match="expired"):
        registry.require(p_expired.principal_id)


def test_permission_governor_integration(store):
    registry = IdentityRegistry(store)
    
    p_agent = registry.register(
        name="governor-agent",
        principal_type="AGENT",
        trust_level=2,
        capabilities=["CAP_FILE_READ", "CAP_FILE_CREATE"],
    )

    policy = PolicyEngine()
    safety = SafetyMonitor()

    # Allowed capability
    allowed, status = PermissionGovernor.authorize_action_request(
        agent_name="governor-agent",
        tool_name="CAP_FILE_READ",
        args={},
        policy=policy,
        safety=safety,
        principal=p_agent,
    )
    assert allowed is True
    assert status == "AUTHORIZED"

    # Blocked capability (not explicitly granted)
    allowed, status = PermissionGovernor.authorize_action_request(
        agent_name="governor-agent",
        tool_name="CAP_WEB_SEARCH",
        args={},
        policy=policy,
        safety=safety,
        principal=p_agent,
    )
    assert allowed is False
    assert status == "BLOCKED_BY_CAPABILITY_REGISTRY"


def test_trust_level_gating(store):
    registry = IdentityRegistry(store)

    p_low_trust = registry.register(
        name="low-trust",
        principal_type="AGENT",
        trust_level=2,
        capabilities=["CAP_TERMINAL_EXECUTE"],
    )

    policy = PolicyEngine()
    safety = SafetyMonitor()

    allowed, status = PermissionGovernor.authorize_action_request(
        agent_name="low-trust",
        tool_name="CAP_TERMINAL_EXECUTE",
        args={"command": "ls"},
        policy=policy,
        safety=safety,
        principal=p_low_trust,
    )
    assert allowed is False
    assert status == "REQUIRES_APPROVAL"


def test_goal_ownership(store):
    registry = IdentityRegistry(store)
    governor = GoalLifecycleGovernor(store)

    # 1. Create with no owner_id
    g1 = governor.create_goal(title="g1")
    assert g1["owner_id"] is None

    # 2. Create with valid owner_id
    p = registry.register(name="goal-owner", principal_type="HUMAN")
    g2 = governor.create_goal(title="g2", owner_id=p.principal_id)
    assert g2["owner_id"] == p.principal_id

    # 3. Create with invalid owner_id
    with pytest.raises(KeyError, match="not found"):
        governor.create_goal(title="g3", owner_id="PRINCIPAL-NONEXISTENT")


def test_bootstrap_idempotent(store):
    bootstrap_default_principals(store)
    registry = IdentityRegistry(store)

    p_sys = registry.get(PRINCIPAL_SYSTEM)
    assert p_sys is not None
    assert p_sys.name == "kattappa-system"
    assert p_sys.principal_type == "SYSTEM"
    assert p_sys.trust_level == 5

    p_human = registry.get(PRINCIPAL_HUMAN_DEFAULT)
    assert p_human is not None
    assert p_human.name == "human-default"
    assert p_human.principal_type == "HUMAN"
    assert p_human.trust_level == 3


def test_delegation_issuer_validation(store):
    # Set the global KERNEL ledger to this test store so delegation token manager uses it
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        p_active = registry.register(name="issuer-active", principal_type="HUMAN")
        p_inactive = registry.register(name="issuer-inactive", principal_type="HUMAN")
        registry.deactivate(p_inactive.principal_id)

        # 1. Unknown issuer emits warning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            mint_delegation_token(
                trace_id="t1",
                capabilities=["CAP_FILE_READ"],
                expires_in_minutes=10,
                max_invocations=5,
                allowed_paths=[],
                allowed_domains=[],
                issued_by="UNKNOWN_ISSUER",
            )
            assert len(w) == 1
            assert "Unknown issuer principal" in str(w[0].message)

        # 2. Known active issuer accepted without warning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tok = mint_delegation_token(
                trace_id="t1",
                capabilities=["CAP_FILE_READ"],
                expires_in_minutes=10,
                max_invocations=5,
                allowed_paths=[],
                allowed_domains=[],
                issued_by=p_active.principal_id,
            )
            assert len(w) == 0

        # Validate capabilities work
        valid, msg = validate_token_capability(tok["token_id"], "CAP_FILE_READ")
        assert valid is True

        # 3. Disabled principal issuer rejected at mint time
        with pytest.raises(PermissionError, match="deactivated, suspended, revoked, or expired"):
            mint_delegation_token(
                trace_id="t1",
                capabilities=["CAP_FILE_READ"],
                expires_in_minutes=10,
                max_invocations=5,
                allowed_paths=[],
                allowed_domains=[],
                issued_by=p_inactive.principal_id,
            )

        # 4. Deactivated principal validation rejection
        # If principal is deactivated *after* token minting, token validation should reject
        tok_valid_at_mint = mint_delegation_token(
            trace_id="t1",
            capabilities=["CAP_FILE_READ"],
            expires_in_minutes=10,
            max_invocations=5,
            allowed_paths=[],
            allowed_domains=[],
            issued_by=p_active.principal_id,
        )
        registry.deactivate(p_active.principal_id)
        valid, msg = validate_token_capability(tok_valid_at_mint["token_id"], "CAP_FILE_READ")
        assert valid is False
        assert "deactivated, suspended, revoked, or expired" in msg

    finally:
        KERNEL.ledger = old_ledger


def test_concurrency_principals_creation(store):
    registry = IdentityRegistry(store)
    errors = []

    def create_batch(thread_idx: int):
        try:
            for i in range(10):
                registry.register(
                    name=f"thread-{thread_idx}-principal-{i}",
                    principal_type="AGENT",
                    trust_level=2,
                )
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=create_batch, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent registration errors: {errors}"
    all_principals = registry.list(active_only=False)
    # 10 threads * 10 principals = 100 principals
    # Plus the default bootstrapped system/human default if sqlite bootstrapped
    assert len(all_principals) >= 100


def test_api_principal_endpoints():
    client = TestClient(app)

    reg_req = {
        "name": "api-principal",
        "principal_type": "AGENT",
        "trust_level": "TRUSTED",
        "capabilities": ["CAP_FILE_READ"],
        "metadata": {"source": "api-test"},
    }
    response = client.post("/api/v1/principals/register", json=reg_req)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    pid = data["principal"]["principal_id"]
    assert pid.startswith("PRINCIPAL-")
    assert data["principal"]["trust_level"] == 3  # TRUSTED resolves to 3

    # Duplicate name conflict
    response = client.post("/api/v1/principals/register", json=reg_req)
    assert response.status_code == 409

    # Retrieve info
    response = client.get(f"/api/v1/principals/{pid}")
    assert response.status_code == 200
    p_data = response.json()["principal"]
    assert p_data["name"] == "api-principal"
    assert p_data["is_active"] is True
    assert p_data["status"] == "ACTIVE"

    # List
    response = client.get("/api/v1/principals/list")
    assert response.status_code == 200
    principals = response.json()["principals"]
    assert len(principals) >= 3

    # Deactivate
    response = client.post(f"/api/v1/principals/{pid}/deactivate")
    assert response.status_code == 200

    # Retrieve info again
    response = client.get(f"/api/v1/principals/{pid}")
    assert response.status_code == 200
    assert response.json()["principal"]["is_active"] is False
    assert response.json()["principal"]["status"] == "SUSPENDED"
