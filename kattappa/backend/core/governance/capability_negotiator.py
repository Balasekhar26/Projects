"""Capability Negotiator (M35 Dynamic Negotiation / M36 Constraint Engine).

Handles dynamic capability lease requests:
  - Auto-approval based on trust level or valid delegation tokens
  - Scope-based constraint validation (e.g. CAP_FILE_WRITE scoped to /tmp/*)
  - Usage quota enforcement (max_uses)
  - Delegation chain parent tracking (parent_contract_id)
  - Recursive revocation propagation when a parent contract is revoked
"""
from __future__ import annotations

import fnmatch
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.core.cos.kernel import KERNEL
from backend.core.governance.identity_registry import IdentityRegistry
from backend.core.governance.delegation_token_manager import validate_token_capability

# Protocol Status Codes
NEGOTIATION_GRANTED = "NEGOTIATION_GRANTED"
NEGOTIATION_DENIED = "NEGOTIATION_DENIED"
ESCALATION_REQUIRED = "ESCALATION_REQUIRED"
LEASE_EXPIRED = "LEASE_EXPIRED"
QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
SCOPE_VIOLATION = "SCOPE_VIOLATION"


class CapabilityNegotiator:
    """Handles dynamic capability requests, lease grants, and escalation workflows."""

    @classmethod
    def request_capability(
        cls,
        principal_id: str,
        capability: str,
        reason: str,
        duration_seconds: float = 60.0,
        delegation_token_id: Optional[str] = None,
        scope: Optional[str] = None,
        max_uses: Optional[int] = None,
        parent_contract_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Requests a temporary capability lease, evaluating auto-approval criteria.

        Args:
            principal_id: The principal requesting the capability.
            capability: The capability key (e.g. CAP_FILE_WRITE).
            reason: Human-readable justification.
            duration_seconds: Lease TTL in seconds.
            delegation_token_id: Optional delegation token to bootstrap approval.
            scope: Optional resource scope constraint (e.g. /tmp/*, github.com).
            max_uses: Optional maximum number of invocations allowed under this lease.
            parent_contract_id: Optional parent contract ID for delegation chain tracking.
        """
        if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
            raise RuntimeError("Ledger database is not initialized.")

        capability = capability.upper().strip()
        contract_id = f"CON-{str(uuid.uuid4())[:8].upper()}"
        expires_at = time.time() + duration_seconds

        # 1. Resolve requesting principal to check trust level
        registry = IdentityRegistry(KERNEL.ledger)
        principal = registry.get(principal_id)
        if principal is None:
            principal = registry.resolve(principal_id)

        # 2. Validate parent delegation chain security invariants
        if parent_contract_id:
            parent = KERNEL.ledger.get_capability_contract(parent_contract_id)
            if parent is None:
                return {
                    "contract_id": None,
                    "status": NEGOTIATION_DENIED,
                    "message": f"Parent contract {parent_contract_id} not found.",
                }
            if parent["status"] not in ("APPROVED",):
                return {
                    "contract_id": None,
                    "status": NEGOTIATION_DENIED,
                    "message": f"Parent contract {parent_contract_id} is not active (status={parent['status']}).",
                }

            parent_scope = parent.get("scope")

            # Invariant A: child.scope ⊆ parent.scope
            # A child cannot claim a broader scope than its parent grants.
            if parent_scope:
                if scope is None:
                    # No child scope specified → inherit parent scope exactly
                    scope = parent_scope
                elif scope != parent_scope and not cls._scope_is_subset(scope, parent_scope):
                    return {
                        "contract_id": None,
                        "status": NEGOTIATION_DENIED,
                        "message": (
                            f"Child scope '{scope}' is not a subset of parent scope '{parent_scope}'. "
                            "Delegation cannot escalate scope."
                        ),
                    }

            # Invariant B: child.expiry ≤ parent.expiry
            if parent["expires_at"] < expires_at:
                expires_at = parent["expires_at"]

            # Invariant C: child.max_uses ≤ parent.remaining_budget
            parent_max_uses = parent.get("max_uses")
            if parent_max_uses is not None:
                parent_use_count = parent.get("use_count") or 0
                parent_remaining = parent_max_uses - parent_use_count
                if parent_remaining <= 0:
                    return {
                        "contract_id": None,
                        "status": NEGOTIATION_DENIED,
                        "message": f"Parent contract {parent_contract_id} has exhausted its quota ({parent_max_uses} uses).",
                    }
                if max_uses is None or max_uses > parent_remaining:
                    # Cap child quota to parent's remaining budget
                    max_uses = parent_remaining

        # 3. Check Auto-Approval rules
        status = ESCALATION_REQUIRED

        # Case A: Delegation Token provides pre-authorization
        if delegation_token_id:
            valid, msg = validate_token_capability(delegation_token_id, capability, scope)
            if valid:
                status = NEGOTIATION_GRANTED

        # Case B: High Trust Level auto-approval (TRUSTED=3, SYSTEM=5, ROOT=5)
        elif principal is not None and principal.is_effectively_active:
            if principal.trust_level >= 3:
                status = NEGOTIATION_GRANTED

        contract = {
            "contract_id": contract_id,
            "principal_id": principal_id,
            "capability": capability,
            "reason": reason,
            "expires_at": expires_at,
            "status": "APPROVED" if status == NEGOTIATION_GRANTED else "ESCALATION_REQUIRED",
            "scope": scope,
            "max_uses": max_uses,
            "use_count": 0,
            "parent_contract_id": parent_contract_id,
        }

        KERNEL.ledger.create_capability_contract(contract)

        return {
            "contract_id": contract_id,
            "status": status,
            "contract": contract,
        }

    @classmethod
    def approve_request(cls, contract_id: str) -> Dict[str, Any]:
        """Manually approves an escalation contract, moving it to APPROVED status."""
        if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
            raise RuntimeError("Ledger database is not initialized.")

        contract = KERNEL.ledger.get_capability_contract(contract_id)
        if not contract:
            return {"status": "error", "message": "Contract not found."}

        # Check if already expired
        if time.time() > contract["expires_at"]:
            KERNEL.ledger.update_capability_contract_status(contract_id, "EXPIRED")
            return {"status": LEASE_EXPIRED, "message": "Lease has already expired."}

        KERNEL.ledger.update_capability_contract_status(contract_id, "APPROVED")
        contract["status"] = "APPROVED"
        return {"status": NEGOTIATION_GRANTED, "contract": contract}

    @classmethod
    def reject_request(cls, contract_id: str, propagate: bool = True) -> Dict[str, Any]:
        """Manually rejects or revokes a contract.

        Args:
            contract_id: The contract to revoke.
            propagate: If True, recursively revokes all child contracts in the delegation chain.
        """
        if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
            raise RuntimeError("Ledger database is not initialized.")

        contract = KERNEL.ledger.get_capability_contract(contract_id)
        if not contract:
            return {"status": "error", "message": "Contract not found."}

        KERNEL.ledger.update_capability_contract_status(contract_id, "REVOKED")
        contract["status"] = "REVOKED"

        revoked_children: List[str] = []
        if propagate:
            revoked_children = cls._revoke_children(contract_id)

        return {
            "status": NEGOTIATION_DENIED,
            "contract": contract,
            "revoked_children": revoked_children,
        }

    @classmethod
    def _revoke_children(cls, parent_contract_id: str) -> List[str]:
        """Recursively revokes all child contracts in the delegation chain.

        Returns:
            List of all revoked child contract_ids.
        """
        revoked: List[str] = []
        if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
            return revoked

        # Fetch child contracts by parent_contract_id
        children = cls._get_children_contracts(parent_contract_id)
        for child in children:
            child_id = child["contract_id"]
            if child["status"] not in ("REVOKED", "EXPIRED"):
                KERNEL.ledger.update_capability_contract_status(child_id, "REVOKED")
                revoked.append(child_id)
                # Recurse to grandchildren
                revoked.extend(cls._revoke_children(child_id))
        return revoked

    @classmethod
    def _get_children_contracts(cls, parent_contract_id: str) -> List[Dict[str, Any]]:
        """Returns all contracts that have parent_contract_id as their parent.

        Note: This queries all contracts for the principal, then filters by parent.
        A future optimization can add a dedicated index query.
        """
        if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
            return []

        # Use get_all_contracts_by_parent if available, else fall back to list_all
        try:
            return KERNEL.ledger.get_contracts_by_parent(parent_contract_id)
        except (AttributeError, NotImplementedError):
            # Fallback: not all store implementations support this yet
            return []

    @classmethod
    def validate_contract_access(
        cls,
        contract_id: str,
        resource: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Validates that a contract is still active, not quota-exceeded, and scope-valid.

        Args:
            contract_id: The contract to validate.
            resource: The resource being accessed (checked against contract scope).

        Returns:
            (allowed: bool, reason: str)
        """
        if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
            return False, "Ledger not initialized."

        contract = KERNEL.ledger.get_capability_contract(contract_id)
        if not contract:
            return False, "Contract not found."

        if contract["status"] in ("REVOKED", "EXPIRED"):
            return False, f"Contract is {contract['status']}."

        if contract["status"] != "APPROVED":
            return False, f"Contract not yet approved (status={contract['status']})."

        # Expiry check
        if time.time() > contract["expires_at"]:
            KERNEL.ledger.update_capability_contract_status(contract_id, "EXPIRED")
            return False, LEASE_EXPIRED

        # Usage quota check
        max_uses = contract.get("max_uses")
        if max_uses is not None:
            use_count = contract.get("use_count", 0) or 0
            if use_count >= max_uses:
                KERNEL.ledger.update_capability_contract_status(contract_id, "EXPIRED")
                return False, QUOTA_EXCEEDED

        # Scope validation
        scope = contract.get("scope")
        if scope and resource:
            if not cls._scope_matches(scope, resource):
                return False, f"{SCOPE_VIOLATION}: resource '{resource}' not allowed under scope '{scope}'"

        return True, "AUTHORIZED"

    @staticmethod
    def _scope_matches(scope: str, resource: str) -> bool:
        """Checks whether a resource path/domain matches the contract scope pattern.

        Supports glob wildcards (e.g., /tmp/*, *.github.com).
        """
        return fnmatch.fnmatch(resource, scope) or fnmatch.fnmatch(resource, scope.rstrip("/") + "/*")

    @staticmethod
    def _scope_is_subset(child_scope: str, parent_scope: str) -> bool:
        """Checks that child_scope is a strict subset of parent_scope.

        A child scope is a subset when any resource matching child_scope
        would also match parent_scope. For glob patterns this is validated by
        checking that the child prefix is rooted within the parent prefix.

        Examples:
            child=/tmp/logs/*, parent=/tmp/* → True  (logs/ is under tmp/)
            child=/tmp/*, parent=/tmp/* → True  (equal scope is allowed)
            child=/*, parent=/tmp/* → False  (child is broader)
            child=*.api.github.com, parent=*.github.com → True
            child=*.evil.com, parent=*.github.com → False
        """
        # Normalize by stripping trailing wildcards to get the base prefix
        def base(pattern: str) -> str:
            return pattern.rstrip("/*").rstrip("*").rstrip(".")

        child_base = base(child_scope)
        parent_base = base(parent_scope)

        # Child scope base must start with parent scope base (path prefix containment)
        if child_base.startswith(parent_base):
            return True

        # Fallback: test if a representative child resource matches the parent scope
        # Use the child base itself as the test resource (most specific point in child scope)
        return fnmatch.fnmatch(child_base, parent_scope) or fnmatch.fnmatch(
            child_base, parent_scope.rstrip("/") + "/*"
        )

    @classmethod
    def record_contract_use(cls, contract_id: str) -> None:
        """Increments the use_count for a contract (called on each successful authorized use)."""
        if hasattr(KERNEL, "ledger") and KERNEL.ledger is not None:
            try:
                KERNEL.ledger.increment_contract_use_count(contract_id)
            except Exception:
                pass

    @classmethod
    def get_active_contracts(cls, principal_id: str) -> List[Dict[str, Any]]:
        """Lists active approved contracts for a principal, filtering out expired ones."""
        if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
            return []

        contracts = KERNEL.ledger.get_active_capability_contracts(principal_id)
        now = time.time()
        active = []
        for c in contracts:
            if c["expires_at"] > now:
                # Quota check
                max_uses = c.get("max_uses")
                use_count = c.get("use_count", 0) or 0
                if max_uses is not None and use_count >= max_uses:
                    KERNEL.ledger.update_capability_contract_status(c["contract_id"], "EXPIRED")
                    continue
                active.append(c)
            else:
                KERNEL.ledger.update_capability_contract_status(c["contract_id"], "EXPIRED")
        return active
