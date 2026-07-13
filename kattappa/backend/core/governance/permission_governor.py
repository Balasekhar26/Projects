"""Permission and Safety Governor (Program 44.0).

Coordinates checks from CapabilityRegistry, PolicyEngine (paths/network/allowlists),
and SafetyMonitor (injection/malicious binaries checks) into a unified validation workflow,
and manages thread-local permission elevations/restrictions.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.capability_registry import CapabilityRegistry, ACTION_CAPABILITY_MAP
from backend.core.governance.policy_engine import PolicyEngine
from backend.core.governance.safety_monitor import SafetyMonitor


class SessionPermissionScope:
    """Thread-local context manager enabling temporary permission overrides."""

    _local = threading.local()

    def __init__(
        self,
        agent_name: str,
        allowed_capabilities: Set[str],
        denied_capabilities: Optional[Set[str]] = None,
    ) -> None:
        self.agent_name = str(agent_name).lower().strip()
        self.allowed = set(allowed_capabilities)
        self.denied = set(denied_capabilities or [])

    def __enter__(self) -> SessionPermissionScope:
        if not hasattr(self._local, "stack"):
            self._local.stack = []
        self._local.stack.append((self.agent_name, self.allowed, self.denied))
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if hasattr(self._local, "stack") and self._local.stack:
            self._local.stack.pop()

    @classmethod
    def get_override(cls, agent_name: str, capability: str) -> Optional[bool]:
        """Looks up active thread-local permission overrides for a given capability."""
        if not hasattr(cls._local, "stack") or not cls._local.stack:
            return None
        
        agent_clean = str(agent_name).lower().strip()
        # Traverse overrides stack backwards (most recent first)
        for agent, allowed, denied in reversed(cls._local.stack):
            if agent == agent_clean:
                if capability in denied:
                    return False
                if capability in allowed:
                    return True
        return None


class PermissionGovernor:
    """Orchestrates comprehensive safety and permission evaluations."""

    @classmethod
    def authorize_action_request(
        cls,
        agent_name: str,
        tool_name: str,
        args: Dict[str, Any],
        policy: PolicyEngine,
        safety: SafetyMonitor,
        principal: Optional[Any] = None,
    ) -> Tuple[bool, str]:
        """Runs the action request through Capability checks, Policy rules, and Safety filters."""
        # 1. Look up matching capability requirements
        # e.g., mapping edit_file/file_write -> CAP_FILE_WRITE. Match case insensitively
        action_key = tool_name.upper().strip()
        if action_key.startswith("CAP_"):
            capability = action_key
        else:
            capability = ACTION_CAPABILITY_MAP.get(action_key)
            
            # Fallback helper lookup if not exact match (e.g. file_read -> READ_FILE)
            if not capability:
                for k, cap in ACTION_CAPABILITY_MAP.items():
                    if k in action_key or action_key in k:
                        capability = cap
                        break
            
            # Default safety fallback capability if still unknown
            if not capability:
                capability = "CAP_TERMINAL_EXECUTE"

        # Target/resource resolver
        target_val = args.get("path") or args.get("filepath") or args.get("TargetFile") or args.get("url") or args.get("domain") or args.get("query")
        resource = str(target_val) if target_val is not None else None
        
        # Principal / ID resolver
        principal_id = principal.principal_id if principal else agent_name
        
        # Delegation chain
        delegation_token_id = args.get("delegation_token_id")
        delegation_chain = [delegation_token_id] if delegation_token_id else []
        
        from backend.core.governance.audit_ledger import AuditLedger
        audit = AuditLedger()

        # 2. Check capability registry (including thread local scopes)
        if principal is not None:
            if not principal.is_effectively_active:
                audit.log_audit_entry(
                    principal_id=principal_id,
                    action=capability,
                    arguments=args,
                    decision="BLOCKED",
                    reason="Principal is deactivated, suspended, revoked, or expired.",
                    resource=resource,
                )
                return False, "BLOCKED_BY_PRINCIPAL_INACTIVE"
            
            # Check thread-local session overrides for the principal name or ID
            from backend.core.governance.permission_governor import SessionPermissionScope
            override = SessionPermissionScope.get_override(principal.name, capability)
            if override is None:
                override = SessionPermissionScope.get_override(principal.principal_id, capability)
            
            if override is False:
                audit.log_audit_entry(
                    principal_id=principal_id,
                    action=capability,
                    arguments=args,
                    decision="BLOCKED",
                    reason="Blocked by capability override.",
                    resource=resource,
                )
                return False, "BLOCKED_BY_CAPABILITY_REGISTRY"
            elif override is not True:
                # If no thread-local override, check explicit principal capabilities
                if not principal.has_capability(capability):
                    # Check active capability contracts (leases) before blocking
                    # M36: also validates scope and quota for matched contracts
                    from backend.core.cos.kernel import KERNEL
                    from backend.core.governance.capability_negotiator import CapabilityNegotiator
                    has_contract = False
                    if hasattr(KERNEL, "ledger") and KERNEL.ledger is not None:
                        try:
                            contracts = KERNEL.ledger.get_active_capability_contracts(principal_id)
                            for c in contracts:
                                if c["capability"].upper() == capability.upper():
                                    ok, _ = CapabilityNegotiator.validate_contract_access(
                                        c["contract_id"], resource=resource
                                    )
                                    if ok:
                                        has_contract = True
                                        CapabilityNegotiator.record_contract_use(c["contract_id"])
                                        break
                        except Exception:
                            pass
                    
                    if not has_contract:
                        audit.log_audit_entry(
                            principal_id=principal_id,
                            action=capability,
                            arguments=args,
                            decision="BLOCKED",
                            reason="Principal missing explicit capability grant or active lease contract.",
                            resource=resource,
                        )
                        return False, "BLOCKED_BY_CAPABILITY_REGISTRY"
        else:
            if not CapabilityRegistry.is_capability_allowed(agent_name, capability):
                # Check active capability contracts (leases) before blocking
                # M36: validates scope and quota for matched contracts
                from backend.core.cos.kernel import KERNEL
                from backend.core.governance.capability_negotiator import CapabilityNegotiator
                has_contract = False
                if hasattr(KERNEL, "ledger") and KERNEL.ledger is not None:
                    try:
                        contracts = KERNEL.ledger.get_active_capability_contracts(principal_id)
                        for c in contracts:
                            if c["capability"].upper() == capability.upper():
                                ok, _ = CapabilityNegotiator.validate_contract_access(
                                    c["contract_id"], resource=resource
                                )
                                if ok:
                                    has_contract = True
                                    CapabilityNegotiator.record_contract_use(c["contract_id"])
                                    break
                    except Exception:
                        pass
                
                if not has_contract:
                    audit.log_audit_entry(
                        principal_id=principal_id,
                        action=capability,
                        arguments=args,
                        decision="BLOCKED",
                        reason="Blocked by CapabilityRegistry, no active lease contract found.",
                        resource=resource,
                    )
                    return False, "BLOCKED_BY_CAPABILITY_REGISTRY"

        # 3. Check Policy Engine allowlists, network toggles, and path restrictions
        if not policy.authorize_action(tool_name, args):
            audit.log_audit_entry(
                principal_id=principal_id,
                action=capability,
                arguments=args,
                decision="BLOCKED",
                reason="Blocked by PolicyEngine.",
                resource=resource,
                delegation_chain=delegation_chain,
            )
            return False, "BLOCKED_BY_POLICY"

        # 4. Check Safety command injection filters and forbidden binary checks
        if not safety.inspect_action(tool_name, args):
            audit.log_audit_entry(
                principal_id=principal_id,
                action=capability,
                arguments=args,
                decision="BLOCKED",
                reason="Blocked by SafetyMonitor.",
                resource=resource,
                delegation_chain=delegation_chain,
            )
            return False, "BLOCKED_BY_SAFETY"

        # 5. Trust Zone and Level assessment
        from backend.core.governance.trust_policy import get_capability_policy
        from backend.core.cos.kernel import KERNEL
        from backend.core.observability.telemetry import TelemetryCollector
        import uuid

        zone, level, approval_policy = get_capability_policy(capability)

        # Check thread-local overrides to auto-approve
        from backend.core.governance.permission_governor import SessionPermissionScope
        is_elevated = False
        if principal is not None:
            if SessionPermissionScope.get_override(principal.name, capability) is True or SessionPermissionScope.get_override(principal.principal_id, capability) is True:
                is_elevated = True
        else:
            if SessionPermissionScope.get_override(agent_name, capability) is True:
                is_elevated = True

        if is_elevated:
            approval_policy = "auto"

        # Trust level gating integration:
        # If principal's trust_level < capability auth level, always require approval
        if principal is not None:
            if not is_elevated and principal.trust_level < int(level):
                approval_policy = "always"

        # Get active trace and span
        active_span = TelemetryCollector().get_active_span()
        trace_id = active_span.trace_id if (active_span and active_span.trace_id) else "ROOT"
        span_id = active_span.span_id if active_span else "ROOT"

        # Check Delegation Token override
        if delegation_token_id:
            from backend.core.governance.delegation_token_manager import validate_token_capability
            valid, reason = validate_token_capability(delegation_token_id, capability, resource)
            if valid:
                if hasattr(KERNEL, "ledger") and KERNEL.ledger is not None:
                    action_id = f"REC-{str(uuid.uuid4())[:8].upper()}"
                    try:
                        KERNEL.ledger.record_execution_receipt(
                            action_id=action_id,
                            capability=capability,
                            authorized_by=f"delegation_token:{delegation_token_id}",
                            approval_scope="token_constraints",
                            trace_id=trace_id,
                            span_id=span_id,
                            metadata={"args": args, "delegation_token_id": delegation_token_id}
                        )
                    except Exception:
                        pass
                audit.log_audit_entry(
                    principal_id=principal_id,
                    action=capability,
                    arguments=args,
                    decision="AUTHORIZED",
                    reason="Authorized by delegation token.",
                    resource=resource,
                    delegation_chain=delegation_chain,
                )
                return True, "AUTHORIZED"

        authorized_by = "policy_bypass"
        approval_scope = approval_policy

        if approval_policy == "always":
            audit.log_audit_entry(
                principal_id=principal_id,
                action=capability,
                arguments=args,
                decision="REQUIRES_APPROVAL",
                reason="Capability approval policy is always-escalate.",
                resource=resource,
                delegation_chain=delegation_chain,
            )
            return False, "REQUIRES_APPROVAL"

        elif approval_policy in ("once", "session"):
            # Check if an execution receipt has already been logged for this capability in the current trace
            receipts_logged = []
            if hasattr(KERNEL, "ledger") and KERNEL.ledger is not None:
                try:
                    receipts_logged = KERNEL.ledger.get_execution_receipts(trace_id)
                except Exception:
                    pass
            
            has_receipt = any(r["capability"] == capability for r in receipts_logged)
            if not has_receipt:
                audit.log_audit_entry(
                    principal_id=principal_id,
                    action=capability,
                    arguments=args,
                    decision="REQUIRES_APPROVAL",
                    reason="Requires approval once per trace, no execution receipt found.",
                    resource=resource,
                    delegation_chain=delegation_chain,
                )
                return False, "REQUIRES_APPROVAL"
            else:
                authorized_by = "session_rules"

        # If authorized, generate and record Execution Receipt
        if hasattr(KERNEL, "ledger") and KERNEL.ledger is not None:
            action_id = f"REC-{str(uuid.uuid4())[:8].upper()}"
            try:
                KERNEL.ledger.record_execution_receipt(
                    action_id=action_id,
                    capability=capability,
                    authorized_by=authorized_by,
                    approval_scope=approval_scope,
                    trace_id=trace_id,
                    span_id=span_id,
                    metadata={"args": args, "trust_zone": zone.value, "auth_level": int(level)}
                )
            except Exception:
                pass

        audit.log_audit_entry(
            principal_id=principal_id,
            action=capability,
            arguments=args,
            decision="AUTHORIZED",
            reason=f"Authorized under approval policy: {approval_scope}",
            resource=resource,
            delegation_chain=delegation_chain,
        )
        return True, "AUTHORIZED"
