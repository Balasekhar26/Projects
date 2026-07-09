"""Unit tests for Program 46.0: Audit Ledger.

Verifies SHA-256 arguments hashing, JSON records persistence, and query filters.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from backend.core.governance import AuditLedger


@pytest.fixture
def temp_ledger():
    with tempfile.TemporaryDirectory() as tmp:
        ledger_path = Path(tmp) / "audit.json"
        yield AuditLedger(ledger_file=ledger_path)


# ── Audit Ledger Tests ────────────────────────────────────────────────────────

class TestAuditLedger:
    def test_log_entry_hashing_and_persistence(self, temp_ledger):
        args = {"CommandLine": "rm -rf /", "force": True}
        entry = temp_ledger.log_audit_entry(
            agent="desktop",
            tool="run_command",
            arguments=args,
            decision="BLOCKED",
            reason="Unsafe pattern matching trigger",
            approver=None,
            session_id="session_123",
        )

        assert entry["audit_id"].startswith("audit_")
        assert entry["agent"] == "desktop"
        assert entry["tool"] == "run_command"
        assert entry["decision"] == "BLOCKED"
        assert entry["session_id"] == "session_123"

        # Check hash is generated and immutable
        assert len(entry["arguments_hash"]) == 64  # SHA-256 length
        
        # Verify persistence
        loaded = temp_ledger.load_audit_entries()
        assert len(loaded) == 1
        assert loaded[0]["audit_id"] == entry["audit_id"]
        assert loaded[0]["arguments_hash"] == entry["arguments_hash"]

    def test_query_filters(self, temp_ledger):
        # Log multiple records
        temp_ledger.log_audit_entry("coder", "write_file", {"path": "a.txt"}, "APPROVED", "Safe path")
        temp_ledger.log_audit_entry("coder", "delete_file", {"path": "b.txt"}, "BLOCKED", "Path bounds exceeded")
        temp_ledger.log_audit_entry("voice", "tts", {"text": "hello"}, "APPROVED", "Safe voice text")

        # Query by agent
        coder_logs = temp_ledger.query_by_agent("coder")
        assert len(coder_logs) == 2
        assert all(log["agent"] == "coder" for log in coder_logs)

        # Query by decision
        blocked_logs = temp_ledger.query_by_decision("BLOCKED")
        assert len(blocked_logs) == 1
        assert blocked_logs[0]["tool"] == "delete_file"
        
        approved_logs = temp_ledger.query_by_decision("APPROVED")
        assert len(approved_logs) == 2
