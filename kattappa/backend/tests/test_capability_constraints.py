"""Test suite for M36: Capability Constraint Engine.

Tests:
- Scope-based access control (glob path matching)
- Usage quota enforcement (max_uses)
- Delegation chain parent-child contract creation
- Recursive revocation propagation
- validate_contract_access() enforcement
- Governor blocks scope/quota violations
"""
import pytest
import time

from backend.core.ledger.stores.sqlite_store import SQLiteLedgerStore
from backend.core.ledger.stores.memory_store import MemoryLedgerStore
from backend.core.governance.identity_registry import IdentityRegistry
from backend.core.governance.capability_negotiator import (
    CapabilityNegotiator,
    NEGOTIATION_GRANTED,
    NEGOTIATION_DENIED,
    ESCALATION_REQUIRED,
    LEASE_EXPIRED,
    QUOTA_EXCEEDED,
    SCOPE_VIOLATION,
)
from backend.core.governance.permission_governor import PermissionGovernor
from backend.core.governance.policy_engine import PolicyEngine
from backend.core.governance.safety_monitor import SafetyMonitor
from backend.core.cos.kernel import KERNEL


@pytest.fixture(params=["sqlite", "memory"])
def store(request):
    if request.param == "sqlite":
        return SQLiteLedgerStore(":memory:")
    return MemoryLedgerStore()


# ─── Scope Constraint Tests ───────────────────────────────────────────────────

def test_scope_allows_matching_resource(store):
    """A contract scoped to /tmp/* should allow /tmp/log.txt."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        p = registry.register(name="scope-agent", principal_type="AGENT", trust_level=4)

        res = CapabilityNegotiator.request_capability(
            principal_id=p.principal_id,
            capability="CAP_FILE_WRITE",
            reason="Write temp logs",
            duration_seconds=300,
            scope="/tmp/*",
        )
        assert res["status"] == NEGOTIATION_GRANTED
        contract_id = res["contract_id"]

        # Accessing /tmp/log.txt — within scope
        ok, reason = CapabilityNegotiator.validate_contract_access(
            contract_id, resource="/tmp/log.txt"
        )
        assert ok is True, f"Expected authorized but got: {reason}"
    finally:
        KERNEL.ledger = old_ledger


def test_scope_blocks_out_of_scope_resource(store):
    """A contract scoped to /tmp/* should block access to /etc/passwd."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        p = registry.register(name="scope-agent-2", principal_type="AGENT", trust_level=4)

        res = CapabilityNegotiator.request_capability(
            principal_id=p.principal_id,
            capability="CAP_FILE_WRITE",
            reason="Write temp logs",
            duration_seconds=300,
            scope="/tmp/*",
        )
        contract_id = res["contract_id"]

        # Accessing /etc/passwd — out of scope
        ok, reason = CapabilityNegotiator.validate_contract_access(
            contract_id, resource="/etc/passwd"
        )
        assert ok is False
        assert SCOPE_VIOLATION in reason
    finally:
        KERNEL.ledger = old_ledger


def test_scope_domain_matching(store):
    """A contract scoped to *.github.com should allow api.github.com but block google.com."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        p = registry.register(name="web-agent", principal_type="AGENT", trust_level=4)

        res = CapabilityNegotiator.request_capability(
            principal_id=p.principal_id,
            capability="CAP_WEB_SEARCH",
            reason="GitHub API access",
            duration_seconds=300,
            scope="*.github.com",
        )
        contract_id = res["contract_id"]

        ok_allowed, _ = CapabilityNegotiator.validate_contract_access(
            contract_id, resource="api.github.com"
        )
        ok_blocked, reason = CapabilityNegotiator.validate_contract_access(
            contract_id, resource="google.com"
        )

        assert ok_allowed is True
        assert ok_blocked is False
        assert SCOPE_VIOLATION in reason
    finally:
        KERNEL.ledger = old_ledger


# ─── Usage Quota Tests ────────────────────────────────────────────────────────

def test_quota_blocks_after_max_uses(store):
    """A contract with max_uses=2 should block on the 3rd invocation."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        p = registry.register(name="quota-agent", principal_type="AGENT", trust_level=4)

        res = CapabilityNegotiator.request_capability(
            principal_id=p.principal_id,
            capability="CAP_SCREENSHOT",
            reason="Limited screenshot capability",
            duration_seconds=300,
            max_uses=2,
        )
        contract_id = res["contract_id"]

        # First use — allowed
        ok1, _ = CapabilityNegotiator.validate_contract_access(contract_id)
        assert ok1 is True
        CapabilityNegotiator.record_contract_use(contract_id)

        # Second use — allowed
        ok2, _ = CapabilityNegotiator.validate_contract_access(contract_id)
        assert ok2 is True
        CapabilityNegotiator.record_contract_use(contract_id)

        # Third use — quota exceeded
        ok3, reason = CapabilityNegotiator.validate_contract_access(contract_id)
        assert ok3 is False
        assert QUOTA_EXCEEDED in reason
    finally:
        KERNEL.ledger = old_ledger


def test_quota_not_enforced_when_none(store):
    """A contract without max_uses should allow unlimited invocations."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        p = registry.register(name="unlimited-agent", principal_type="AGENT", trust_level=4)

        res = CapabilityNegotiator.request_capability(
            principal_id=p.principal_id,
            capability="CAP_FILE_READ",
            reason="Read access",
            duration_seconds=300,
            max_uses=None,
        )
        contract_id = res["contract_id"]

        for _ in range(20):
            ok, _ = CapabilityNegotiator.validate_contract_access(contract_id)
            assert ok is True
            CapabilityNegotiator.record_contract_use(contract_id)
    finally:
        KERNEL.ledger = old_ledger


# ─── Delegation Chain Tests ───────────────────────────────────────────────────

def test_parent_child_delegation_chain(store):
    """Parent contract grants scope /data/*, child contract inherits scoped access."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        architect = registry.register(name="architect", principal_type="AGENT", trust_level=5)
        planner = registry.register(name="planner", principal_type="AGENT", trust_level=4)

        # Parent contract: Architect -> CAP_FILE_WRITE scoped to /data/*
        parent_res = CapabilityNegotiator.request_capability(
            principal_id=architect.principal_id,
            capability="CAP_FILE_WRITE",
            reason="Architect data access",
            duration_seconds=600,
            scope="/data/*",
        )
        assert parent_res["status"] == NEGOTIATION_GRANTED
        parent_id = parent_res["contract_id"]

        # Child contract: Planner -> CAP_FILE_WRITE delegated from Architect
        child_res = CapabilityNegotiator.request_capability(
            principal_id=planner.principal_id,
            capability="CAP_FILE_WRITE",
            reason="Planner sub-delegation",
            duration_seconds=300,
            scope="/data/*",
            parent_contract_id=parent_id,
        )
        assert child_res["status"] == NEGOTIATION_GRANTED
        child_id = child_res["contract_id"]

        # Child can access /data/plan.json
        ok, _ = CapabilityNegotiator.validate_contract_access(child_id, resource="/data/plan.json")
        assert ok is True

        # Verify parent_contract_id is stored correctly
        child_contract = store.get_capability_contract(child_id)
        assert child_contract["parent_contract_id"] == parent_id
    finally:
        KERNEL.ledger = old_ledger


def test_child_cannot_exceed_parent_scope(store):
    """Child contract scope cannot exceed parent scope (parent scope is inherited)."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        architect = registry.register(name="architect-2", principal_type="AGENT", trust_level=5)
        researcher = registry.register(name="researcher", principal_type="AGENT", trust_level=4)

        # Parent: scoped to /data/reports/*
        parent_res = CapabilityNegotiator.request_capability(
            principal_id=architect.principal_id,
            capability="CAP_FILE_READ",
            reason="Reports access",
            duration_seconds=600,
            scope="/data/reports/*",
        )
        parent_id = parent_res["contract_id"]

        # Child: tries to claim broader /data/* scope
        # The negotiator should enforce parent scope -> scope inherited as /data/reports/*
        child_res = CapabilityNegotiator.request_capability(
            principal_id=researcher.principal_id,
            capability="CAP_FILE_READ",
            reason="Sub-delegation",
            duration_seconds=300,
            scope=None,   # Inherits from parent
            parent_contract_id=parent_id,
        )
        child_id = child_res["contract_id"]
        child_contract = store.get_capability_contract(child_id)

        # Scope should have been inherited from parent
        assert child_contract["scope"] == "/data/reports/*"

        # Access within inherited scope allowed
        ok_in, _ = CapabilityNegotiator.validate_contract_access(
            child_id, resource="/data/reports/q1.pdf"
        )
        assert ok_in is True

        # Access outside parent scope blocked
        ok_out, reason = CapabilityNegotiator.validate_contract_access(
            child_id, resource="/data/secrets/key.pem"
        )
        assert ok_out is False
        assert SCOPE_VIOLATION in reason
    finally:
        KERNEL.ledger = old_ledger


# ─── Recursive Revocation Tests ───────────────────────────────────────────────

def test_recursive_revocation_propagates_to_children(store):
    """Revoking a parent contract recursively revokes all descendant contracts."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        root = registry.register(name="root-agent", principal_type="AGENT", trust_level=5)
        child_p = registry.register(name="child-agent", principal_type="AGENT", trust_level=4)
        grandchild_p = registry.register(name="grandchild-agent", principal_type="AGENT", trust_level=4)

        # Root contract
        root_res = CapabilityNegotiator.request_capability(
            principal_id=root.principal_id,
            capability="CAP_TERMINAL_EXECUTE",
            reason="Root shell access",
            duration_seconds=600,
        )
        root_id = root_res["contract_id"]

        # Child contract (delegates from root)
        child_res = CapabilityNegotiator.request_capability(
            principal_id=child_p.principal_id,
            capability="CAP_TERMINAL_EXECUTE",
            reason="Child shell access",
            duration_seconds=300,
            parent_contract_id=root_id,
        )
        child_id = child_res["contract_id"]

        # Grandchild contract (delegates from child)
        grandchild_res = CapabilityNegotiator.request_capability(
            principal_id=grandchild_p.principal_id,
            capability="CAP_TERMINAL_EXECUTE",
            reason="Grandchild shell access",
            duration_seconds=150,
            parent_contract_id=child_id,
        )
        grandchild_id = grandchild_res["contract_id"]

        # Verify all are approved
        assert store.get_capability_contract(root_id)["status"] == "APPROVED"
        assert store.get_capability_contract(child_id)["status"] == "APPROVED"
        assert store.get_capability_contract(grandchild_id)["status"] == "APPROVED"

        # Revoke root — should cascade to child and grandchild
        revoke_res = CapabilityNegotiator.reject_request(root_id, propagate=True)
        assert revoke_res["status"] == NEGOTIATION_DENIED

        # All should now be REVOKED
        assert store.get_capability_contract(root_id)["status"] == "REVOKED"
        assert store.get_capability_contract(child_id)["status"] == "REVOKED"
        assert store.get_capability_contract(grandchild_id)["status"] == "REVOKED"

        # Verify revoked_children is reported
        assert child_id in revoke_res["revoked_children"]
        assert grandchild_id in revoke_res["revoked_children"]
    finally:
        KERNEL.ledger = old_ledger


def test_revoke_without_propagation(store):
    """Revoking with propagate=False should only revoke the target contract."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        parent_p = registry.register(name="parent-np", principal_type="AGENT", trust_level=5)
        child_p = registry.register(name="child-np", principal_type="AGENT", trust_level=4)

        parent_res = CapabilityNegotiator.request_capability(
            principal_id=parent_p.principal_id,
            capability="CAP_FILE_WRITE",
            reason="Parent",
            duration_seconds=600,
        )
        parent_id = parent_res["contract_id"]

        child_res = CapabilityNegotiator.request_capability(
            principal_id=child_p.principal_id,
            capability="CAP_FILE_WRITE",
            reason="Child",
            duration_seconds=300,
            parent_contract_id=parent_id,
        )
        child_id = child_res["contract_id"]

        # Revoke parent WITHOUT propagation
        CapabilityNegotiator.reject_request(parent_id, propagate=False)

        # Parent is revoked, child remains APPROVED (no cascade)
        assert store.get_capability_contract(parent_id)["status"] == "REVOKED"
        assert store.get_capability_contract(child_id)["status"] == "APPROVED"
    finally:
        KERNEL.ledger = old_ledger


# ─── Governor Integration Tests ───────────────────────────────────────────────

def test_governor_blocks_scope_violated_contract(store):
    """PermissionGovernor should block a request when the active contract is out-of-scope."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        p = registry.register(name="scoped-gov-agent", principal_type="AGENT", trust_level=4)

        # Grant CAP_SCREENSHOT scoped to /tmp/* (approval policy=auto)
        CapabilityNegotiator.request_capability(
            principal_id=p.principal_id,
            capability="CAP_SCREENSHOT",
            reason="Temp only",
            duration_seconds=300,
            scope="/tmp/*",
        )

        policy = PolicyEngine()
        safety = SafetyMonitor()

        # Resource /etc/hosts is outside /tmp/* scope → governor blocks
        ok, msg = PermissionGovernor.authorize_action_request(
            agent_name="scoped-gov-agent",
            tool_name="DESKTOP_SCREENSHOT",
            args={"path": "/etc/hosts"},
            policy=policy,
            safety=safety,
            principal=p,
        )
        assert ok is False
        assert msg == "BLOCKED_BY_CAPABILITY_REGISTRY"
    finally:
        KERNEL.ledger = old_ledger


def test_governor_allows_scoped_contract(store):
    """PermissionGovernor should allow a request that falls within the contract scope."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        p = registry.register(name="scoped-allow-agent", principal_type="AGENT", trust_level=4)

        # Grant CAP_SCREENSHOT scoped to /tmp/* (CAP_SCREENSHOT has auto policy → no prior receipt needed)
        CapabilityNegotiator.request_capability(
            principal_id=p.principal_id,
            capability="CAP_SCREENSHOT",
            reason="Temp only",
            duration_seconds=300,
            scope="/tmp/*",
        )

        policy = PolicyEngine()
        safety = SafetyMonitor()

        # Resource /tmp/output.txt is within /tmp/* scope → governor allows
        ok, msg = PermissionGovernor.authorize_action_request(
            agent_name="scoped-allow-agent",
            tool_name="DESKTOP_SCREENSHOT",
            args={"path": "/tmp/output.txt"},
            policy=policy,
            safety=safety,
            principal=p,
        )
        assert ok is True
    finally:
        KERNEL.ledger = old_ledger


# ─── Delegation Chain Security Invariant Tests ────────────────────────────────

def test_invariant_a_child_scope_broader_than_parent_blocked(store):
    """Invariant A: child.scope must be ⊆ parent.scope — broader scope is rejected."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        root = registry.register(name="inv-root", principal_type="AGENT", trust_level=5)
        child_p = registry.register(name="inv-child", principal_type="AGENT", trust_level=4)

        # Parent scoped to /tmp/*
        parent_res = CapabilityNegotiator.request_capability(
            principal_id=root.principal_id,
            capability="CAP_FILE_WRITE",
            reason="Parent",
            duration_seconds=600,
            scope="/tmp/*",
        )
        parent_id = parent_res["contract_id"]

        # Child attempts broader scope /* — should be blocked
        child_res = CapabilityNegotiator.request_capability(
            principal_id=child_p.principal_id,
            capability="CAP_FILE_WRITE",
            reason="Child escalation attempt",
            duration_seconds=300,
            scope="/*",
            parent_contract_id=parent_id,
        )
        assert child_res["status"] == NEGOTIATION_DENIED
        assert child_res.get("contract_id") is None
        assert "Delegation cannot escalate scope" in child_res.get("message", "")
    finally:
        KERNEL.ledger = old_ledger


def test_invariant_a_child_narrower_scope_allowed(store):
    """Invariant A: child scope narrower than parent is allowed."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        root = registry.register(name="inv-root-2", principal_type="AGENT", trust_level=5)
        child_p = registry.register(name="inv-child-2", principal_type="AGENT", trust_level=4)

        parent_res = CapabilityNegotiator.request_capability(
            principal_id=root.principal_id,
            capability="CAP_FILE_WRITE",
            reason="Parent",
            duration_seconds=600,
            scope="/tmp/*",
        )
        parent_id = parent_res["contract_id"]

        # Child claims /tmp/logs/* — a subset of /tmp/*
        child_res = CapabilityNegotiator.request_capability(
            principal_id=child_p.principal_id,
            capability="CAP_FILE_WRITE",
            reason="Narrowed delegation",
            duration_seconds=300,
            scope="/tmp/logs/*",
            parent_contract_id=parent_id,
        )
        assert child_res["status"] == NEGOTIATION_GRANTED
        child_contract = store.get_capability_contract(child_res["contract_id"])
        assert child_contract["scope"] == "/tmp/logs/*"
    finally:
        KERNEL.ledger = old_ledger


def test_invariant_c_child_quota_capped_to_parent_remaining(store):
    """Invariant C: child.max_uses is capped to the parent's remaining invocation budget."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        root = registry.register(name="quota-root", principal_type="AGENT", trust_level=5)
        child_p = registry.register(name="quota-child", principal_type="AGENT", trust_level=4)

        # Parent has max_uses=5, already used 2
        parent_res = CapabilityNegotiator.request_capability(
            principal_id=root.principal_id,
            capability="CAP_SCREENSHOT",
            reason="Parent",
            duration_seconds=600,
            max_uses=5,
        )
        parent_id = parent_res["contract_id"]

        # Simulate 2 uses on parent
        KERNEL.ledger.increment_contract_use_count(parent_id)
        KERNEL.ledger.increment_contract_use_count(parent_id)

        # Child requests max_uses=100 — should be capped to parent remaining (5-2=3)
        child_res = CapabilityNegotiator.request_capability(
            principal_id=child_p.principal_id,
            capability="CAP_SCREENSHOT",
            reason="Child with excessive quota request",
            duration_seconds=300,
            max_uses=100,
            parent_contract_id=parent_id,
        )
        assert child_res["status"] == NEGOTIATION_GRANTED
        child_contract = store.get_capability_contract(child_res["contract_id"])
        assert child_contract["max_uses"] == 3  # capped to parent remaining budget
    finally:
        KERNEL.ledger = old_ledger


def test_invariant_c_child_blocked_when_parent_quota_exhausted(store):
    """Invariant C: child creation is blocked if parent quota is already exhausted."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        root = registry.register(name="exhausted-root", principal_type="AGENT", trust_level=5)
        child_p = registry.register(name="exhausted-child", principal_type="AGENT", trust_level=4)

        # Parent with max_uses=2
        parent_res = CapabilityNegotiator.request_capability(
            principal_id=root.principal_id,
            capability="CAP_SCREENSHOT",
            reason="Parent",
            duration_seconds=600,
            max_uses=2,
        )
        parent_id = parent_res["contract_id"]

        # Exhaust parent quota
        KERNEL.ledger.increment_contract_use_count(parent_id)
        KERNEL.ledger.increment_contract_use_count(parent_id)

        # Child creation should be blocked — parent has no remaining budget
        child_res = CapabilityNegotiator.request_capability(
            principal_id=child_p.principal_id,
            capability="CAP_SCREENSHOT",
            reason="Child",
            duration_seconds=300,
            parent_contract_id=parent_id,
        )
        assert child_res["status"] == NEGOTIATION_DENIED
        assert "exhausted its quota" in child_res.get("message", "")
    finally:
        KERNEL.ledger = old_ledger
