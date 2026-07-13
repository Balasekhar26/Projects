"""
M32: Identity System — Principal model and registry.

A Principal is a typed, persisted identity that replaces free-text agent_name/owner
strings throughout the governance layer.

Principal types:
    SYSTEM   — Internal kernel coordinator operations.
    HUMAN    — Interactive user at the keyboard.
    AGENT    — Autonomous skill or planner subagent.
    SERVICE  — External API caller or integration.
    TOOL     — Dedicated tool access wrapper.
    SANDBOX  — Sandboxed execution environment.

Trust levels map to AuthorizationLevel in trust_policy.py:
    ROOT/SYSTEM   → L5  (physical world / dangerous)
    TRUSTED       → L3  (external communications)
    LIMITED       → L2  (local write/modifications)
    SANDBOXED     → L1  (read-only)
    UNTRUSTED     → L0  (internal reasoning only)
    REVOKED       → -1  (blocked / inactive)
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

# ─── Built-in principal IDs (stable across restarts) ──────────────────────────
PRINCIPAL_SYSTEM = "PRINCIPAL-SYSTEM"
PRINCIPAL_HUMAN_DEFAULT = "PRINCIPAL-HUMAN-DEFAULT"

# Valid principal types (standardized as uppercase)
_VALID_TYPES = frozenset({"SYSTEM", "HUMAN", "AGENT", "SERVICE", "TOOL", "SANDBOX"})

# Default trust levels per principal type
_TYPE_DEFAULT_TRUST: dict[str, int] = {
    "SYSTEM":  5,
    "HUMAN":   3,
    "AGENT":   2,
    "SERVICE": 1,
    "TOOL":    1,
    "SANDBOX": 1,
}

# String trust levels mapping
TRUST_LEVEL_MAP = {
    "ROOT": 5,
    "SYSTEM": 5,
    "TRUSTED": 3,
    "LIMITED": 2,
    "SANDBOXED": 1,
    "UNTRUSTED": 0,
    "REVOKED": -1,
}

_VALID_STATUSES = frozenset({"CREATED", "ACTIVE", "SUSPENDED", "REVOKED"})


@dataclass
class Principal:
    """Typed, persisted identity for the Kattappa AIOS governance layer."""

    principal_id: str
    name: str
    principal_type: str          # SYSTEM | HUMAN | AGENT | SERVICE | TOOL | SANDBOX
    trust_level: int             # 0–5
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    is_active: bool = True
    status: str = "ACTIVE"       # CREATED | ACTIVE | SUSPENDED | REVOKED
    expires_at: Optional[float] = None
    public_key: Optional[str] = None

    # ── Helpers ────────────────────────────────────────────────────────────────

    @property
    def is_effectively_active(self) -> bool:
        """Returns True if the principal is active, status is ACTIVE, and has not expired."""
        if not self.is_active or self.status != "ACTIVE":
            return False
        if self.expires_at is not None and time.time() > self.expires_at:
            return False
        return True

    def has_capability(self, cap: str) -> bool:
        """Returns True if this principal is explicitly granted the capability."""
        return cap.upper() in (c.upper() for c in self.capabilities)

    def can_authorize(self, required_level: int) -> bool:
        """True if the principal's trust_level meets or exceeds required_level."""
        if not self.is_effectively_active:
            return False
        return self.trust_level >= required_level


    def to_dict(self) -> dict[str, Any]:
        return {
            "principal_id":   self.principal_id,
            "name":           self.name,
            "principal_type": self.principal_type,
            "trust_level":    self.trust_level,
            "capabilities":   list(self.capabilities),
            "metadata":       dict(self.metadata),
            "created_at":     self.created_at,
            "is_active":      self.is_active,
            "status":         self.status,
            "expires_at":     self.expires_at,
            "public_key":     self.public_key,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Principal":
        return Principal(
            principal_id=d["principal_id"],
            name=d["name"],
            principal_type=d["principal_type"],
            trust_level=int(d["trust_level"]),
            capabilities=list(d.get("capabilities") or []),
            metadata=dict(d.get("metadata") or {}),
            created_at=float(d.get("created_at") or time.time()),
            is_active=bool(d.get("is_active", True)),
            status=d.get("status", "ACTIVE"),
            expires_at=d.get("expires_at"),
            public_key=d.get("public_key"),
        )


class PrincipalValidationError(ValueError):
    """Raised when principal registration data is invalid."""


class IdentityRegistry:
    """Thin governance wrapper around the ledger store's principal CRUD."""

    def __init__(self, store: Any) -> None:
        """
        Args:
            store: Any LedgerStore implementation that exposes the principal
                   CRUD methods (create_principal, get_principal, etc.).
        """
        self._store = store

    # ── Registration ──────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        principal_type: str,
        trust_level: Optional[int | str] = None,
        capabilities: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        principal_id: Optional[str] = None,
        status: str = "ACTIVE",
        expires_at: Optional[float] = None,
        public_key: Optional[str] = None,
    ) -> Principal:
        """Creates and persists a new principal.

        Args:
            name:           Unique human-readable label.
            principal_type: SYSTEM | HUMAN | AGENT | SERVICE | TOOL | SANDBOX.
            trust_level:    Override default trust (0–5 or string name e.g. "TRUSTED").
            capabilities:   Explicit CAP_* grants.
            metadata:       Arbitrary key-value tags.
            principal_id:   Stable ID; auto-generated if not provided.
            status:         CREATED | ACTIVE | SUSPENDED | REVOKED.
            expires_at:     Expiry timestamp, if any.
            public_key:     Hex-encoded Ed25519 public key.

        Returns:
            The newly registered Principal.

        Raises:
            PrincipalValidationError: On invalid type, status, trust_level, or duplicate name.
        """
        ptype_upper = str(principal_type).upper().strip()
        if ptype_upper not in _VALID_TYPES:
            raise PrincipalValidationError(
                f"Invalid principal_type '{principal_type}'. Must be one of {sorted(_VALID_TYPES)}."
            )

        status_upper = str(status).upper().strip()
        if status_upper not in _VALID_STATUSES:
            raise PrincipalValidationError(
                f"Invalid status '{status}'. Must be one of {sorted(_VALID_STATUSES)}."
            )

        if isinstance(trust_level, str):
            tl_upper = trust_level.upper().strip()
            if tl_upper not in TRUST_LEVEL_MAP:
                raise PrincipalValidationError(
                    f"Invalid trust level name '{trust_level}'. Must be one of {sorted(TRUST_LEVEL_MAP.keys())}."
                )
            effective_trust = TRUST_LEVEL_MAP[tl_upper]
        else:
            effective_trust = (
                trust_level if trust_level is not None
                else _TYPE_DEFAULT_TRUST[ptype_upper]
            )

        if not (0 <= effective_trust <= 5) and effective_trust != -1:
            raise PrincipalValidationError(
                f"trust_level must be 0–5 or -1, got {effective_trust}."
            )

        pid = principal_id or f"PRINCIPAL-{uuid.uuid4().hex[:12].upper()}"
        now = time.time()

        principal = Principal(
            principal_id=pid,
            name=str(name).strip(),
            principal_type=ptype_upper,
            trust_level=effective_trust,
            capabilities=list(capabilities or []),
            metadata=dict(metadata or {}),
            created_at=now,
            is_active=(status_upper == "ACTIVE"),
            status=status_upper,
            expires_at=expires_at,
            public_key=public_key,
        )
        self._store.create_principal(principal.to_dict())
        return principal


    # ── Lookup ────────────────────────────────────────────────────────────────

    def get(self, principal_id: str) -> Optional[Principal]:
        """Retrieves a principal by ID, or None if not found."""
        row = self._store.get_principal(principal_id)
        return Principal.from_dict(row) if row else None

    def resolve(self, name: str) -> Optional[Principal]:
        """Looks up a principal by unique name, or None if not found."""
        row = self._store.get_principal_by_name(name)
        return Principal.from_dict(row) if row else None

    def require(self, principal_id: str) -> Principal:
        """Like get() but raises KeyError or PermissionError based on lifecycle/status/expiry."""
        p = self.get(principal_id)
        if p is None:
            raise KeyError(f"Principal '{principal_id}' not found.")
        if p.status == "SUSPENDED":
            raise PermissionError(f"Principal '{principal_id}' is suspended.")
        if p.status == "REVOKED":
            raise PermissionError(f"Principal '{principal_id}' is revoked.")
        if p.expires_at is not None and time.time() > p.expires_at:
            raise PermissionError(f"Principal '{principal_id}' has expired.")
        if not p.is_effectively_active:
            raise PermissionError(f"Principal '{principal_id}' is deactivated or suspended (status: {p.status}).")
        return p


    # ── Mutation / Status Changes ─────────────────────────────────────────────

    def deactivate(self, principal_id: str) -> None:
        """Suspends a principal (status → SUSPENDED, is_active → False)."""
        self._store.update_principal_status(principal_id, is_active=False, status="SUSPENDED")

    def suspend(self, principal_id: str) -> None:
        """Suspends a principal."""
        self._store.update_principal_status(principal_id, is_active=False, status="SUSPENDED")

    def revoke(self, principal_id: str) -> None:
        """Revokes a principal."""
        self._store.update_principal_status(principal_id, is_active=False, status="REVOKED")

    def reactivate(self, principal_id: str) -> None:
        """Restores a previously deactivated principal."""
        self._store.update_principal_status(principal_id, is_active=True, status="ACTIVE")

    # ── List ──────────────────────────────────────────────────────────────────

    def list(
        self,
        principal_type: Optional[str] = None,
        active_only: bool = True,
    ) -> list[Principal]:
        """Returns all principals, optionally filtered by type and active status."""
        rows = self._store.list_principals(
            principal_type=principal_type,
            active_only=active_only,
        )
        return [Principal.from_dict(r) for r in rows]


# ─── Bootstrap ────────────────────────────────────────────────────────────────

def bootstrap_default_principals(store: Any) -> None:
    """Creates the two built-in principals if they do not already exist.

    Uses INSERT OR IGNORE semantics via the store, so calling this multiple
    times is safe (idempotent).

    Built-ins:
        PRINCIPAL-SYSTEM        — Internal kernel agent, trust L5.
        PRINCIPAL-HUMAN-DEFAULT — Default interactive human, trust L3.
    """
    registry = IdentityRegistry(store)
    _ensure(registry, PRINCIPAL_SYSTEM,       "kattappa-system",  "SYSTEM",  5)
    _ensure(registry, PRINCIPAL_HUMAN_DEFAULT, "human-default",   "HUMAN",   3)


def _ensure(
    registry: IdentityRegistry,
    principal_id: str,
    name: str,
    ptype: str,
    trust: int,
) -> None:
    """Registers a principal only if its ID does not already exist."""
    existing = registry.get(principal_id)
    if existing is None:
        registry.register(
            name=name,
            principal_type=ptype,
            trust_level=trust,
            principal_id=principal_id,
            metadata={"builtin": True},
        )
