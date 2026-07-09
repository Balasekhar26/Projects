"""Governance Audit Ledger (Program 46.0).

Records immutable governance logs for tool runs: computes SHA-256 parameter hashes,
persists records to json audit logs, and supports query sorting filters.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import runtime_data_root


def _audit_file_path() -> Path:
    p = runtime_data_root() / "backend" / "data" / "governance"
    p.mkdir(parents=True, exist_ok=True)
    return p / "audit_ledger.json"


class AuditLedger:
    """Manages persistent execution audit ledgers, hashes action arguments, and filters records."""

    _lock = threading.Lock()

    def __init__(self, ledger_file: Optional[str | Path] = None) -> None:
        self.ledger_file = Path(ledger_file) if ledger_file else _audit_file_path()

    def load_audit_entries(self) -> List[Dict[str, Any]]:
        """Loads all logged entries from the JSON audit file."""
        with self._lock:
            if not self.ledger_file.exists():
                return []
            try:
                with self.ledger_file.open(encoding="utf-8") as fh:
                    return json.load(fh)
            except json.JSONDecodeError:
                return []

    def save_audit_entries(self, entries: List[Dict[str, Any]]) -> None:
        """Saves target list to the JSON audit file."""
        with self._lock:
            with self.ledger_file.open("w", encoding="utf-8") as fh:
                json.dump(entries, fh, indent=2)

    def log_audit_entry(
        self,
        agent: str,
        tool: str,
        arguments: Dict[str, Any],
        decision: str,
        reason: str,
        approver: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculates argument hashes, records timestamps, and appends logs to file."""
        # 1. Calculate SHA-256 hash of tool arguments to prevent manipulation
        args_str = json.dumps(arguments, sort_keys=True)
        args_hash = hashlib.sha256(args_str.encode("utf-8")).hexdigest()

        # 2. Build entry record
        entry = {
            "audit_id": f"audit_{uuid.uuid4().hex[:8]}",
            "timestamp": time.time(),
            "agent": str(agent).lower().strip(),
            "tool": str(tool).lower().strip(),
            "arguments_hash": args_hash,
            "decision": str(decision).upper().strip(),
            "reason": reason,
            "approver": approver,
            "session_id": session_id,
        }

        # 3. Save entry to persistent list
        entries = self.load_audit_entries()
        entries.append(entry)
        self.save_audit_entries(entries)

        return entry

    def query_by_agent(self, agent: str) -> List[Dict[str, Any]]:
        """Filters audit records matching agent name."""
        target = str(agent).lower().strip()
        return [entry for entry in self.load_audit_entries() if entry.get("agent") == target]

    def query_by_decision(self, decision: str) -> List[Dict[str, Any]]:
        """Filters audit records matching decision type."""
        target = str(decision).upper().strip()
        return [entry for entry in self.load_audit_entries() if entry.get("decision") == target]
