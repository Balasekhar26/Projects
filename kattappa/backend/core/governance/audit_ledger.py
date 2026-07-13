"""Governance Audit Ledger (Program 46.0).

Records immutable governance logs for tool runs: computes SHA-256 parameter hashes,
persists records cryptographically to the store, and validates ledger integrity.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

# Genesis hash block of 64 zeroes
GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"


class AuditLedger:
    """Manages persistent execution audit ledgers and validates hash-chain integrity."""

    def __init__(self, store: Any = None) -> None:
        if store is not None:
            self._store = store
        else:
            from backend.core.cos.kernel import KERNEL
            self._store = KERNEL.ledger

    def _require_store(self) -> Any:
        if self._store is None:
            raise ValueError("Store must be initialized or KERNEL.ledger must be set.")
        return self._store

    def log_audit_entry(
        self,
        principal_id: str,
        action: str,
        arguments: Dict[str, Any],
        decision: str,
        reason: str,
        resource: Optional[str] = None,
        delegation_chain: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Calculates argument hashes, appends a cryptographically chained record."""
        store = self._require_store()

        # 1. Calculate SHA-256 hash of arguments
        args_str = json.dumps(arguments, sort_keys=True) if arguments else "{}"
        args_hash = hashlib.sha256(args_str.encode("utf-8")).hexdigest()

        # 2. Get latest entry hash for linking
        prev_hash = store.get_latest_audit_hash() or GENESIS_HASH

        # 3. Create entry
        timestamp = time.time()
        audit_id = f"AUDIT-{uuid.uuid4().hex[:8].upper()}"
        chain = list(delegation_chain or [])

        # Build payload for cryptographic hash computation
        payload = {
            "timestamp":        timestamp,
            "principal_id":     principal_id,
            "action":           action,
            "resource":         resource,
            "decision":         decision,
            "reason":           reason,
            "arguments_hash":   args_hash,
            "delegation_chain": chain,
            "previous_hash":    prev_hash,
        }

        # Calculate entry hash
        payload_str = json.dumps(payload, sort_keys=True)
        entry_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

        entry = {
            "audit_id":         audit_id,
            "timestamp":        timestamp,
            "principal_id":     principal_id,
            "action":           action,
            "resource":         resource,
            "decision":         decision,
            "reason":           reason,
            "arguments_hash":   args_hash,
            "delegation_chain": chain,
            "previous_hash":    prev_hash,
            "entry_hash":       entry_hash,
        }

        store.append_audit_entry(entry)
        return entry

    def load_audit_entries(self) -> List[Dict[str, Any]]:
        """Loads all logged audit entries."""
        store = self._require_store()
        return store.list_audit_entries()

    def query_by_agent(self, agent: str) -> List[Dict[str, Any]]:
        """Filters audit records matching agent name or principal ID (for backwards compatibility)."""
        target = str(agent).lower().strip()
        return [
            entry for entry in self.load_audit_entries()
            if entry.get("principal_id", "").lower() == target or entry.get("agent", "").lower() == target
        ]

    def query_by_decision(self, decision: str) -> List[Dict[str, Any]]:
        """Filters audit records matching decision type."""
        target = str(decision).upper().strip()
        return [entry for entry in self.load_audit_entries() if entry.get("decision") == target]

    def validate_ledger_integrity(self) -> Tuple[bool, str]:
        """Recomputes and validates the hash-chain from genesis to latest entry.

        Returns:
            (True, "") if the chain is structurally and cryptographically intact.
            (False, error_reason) if a mismatch or tampering is detected.
        """
        entries = self.load_audit_entries()
        if not entries:
            return True, ""

        expected_prev_hash = GENESIS_HASH

        for idx, entry in enumerate(entries):
            # Check previous_hash link
            if entry["previous_hash"] != expected_prev_hash:
                return (
                    False,
                    f"Cryptographic link broken at index {idx} (audit_id: {entry['audit_id']}). "
                    f"Expected previous_hash {expected_prev_hash}, got {entry['previous_hash']}."
                )

            # Recompute payload hash
            payload = {
                "timestamp":        entry["timestamp"],
                "principal_id":     entry["principal_id"],
                "action":           entry["action"],
                "resource":         entry["resource"],
                "decision":         entry["decision"],
                "reason":           entry["reason"],
                "arguments_hash":   entry["arguments_hash"],
                "delegation_chain": entry["delegation_chain"],
                "previous_hash":    entry["previous_hash"],
            }
            payload_str = json.dumps(payload, sort_keys=True)
            recomputed_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

            # Check hash match
            if entry["entry_hash"] != recomputed_hash:
                return (
                    False,
                    f"Hash mismatch at index {idx} (audit_id: {entry['audit_id']}). "
                    f"Expected entry_hash {recomputed_hash}, got {entry['entry_hash']}."
                )

            # Set up next links
            expected_prev_hash = entry["entry_hash"]

        return True, ""

