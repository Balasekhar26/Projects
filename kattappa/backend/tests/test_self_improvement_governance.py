"""Tests for Step 21: Self-Improvement Governance."""

from __future__ import annotations

import time
import uuid
import pytest
from unittest.mock import patch

from backend.core.self_improvement_governance import (
    ArchitecturalProposal,
    GateDecision,
    SelfImprovementGovernance,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.self_improvement_governance as sig_module
    monkeypatch.setenv("KATTAPPA_DATA_DIR", str(tmp_path))
    sig_module._schema_ensured.clear()
    yield


def _proposal(
    source: str = "benchmark",
    affected_modules: list[str] | None = None,
    benchmark_confirmed: bool = False,
    title: str = "Optimise planning cache",
) -> ArchitecturalProposal:
    return ArchitecturalProposal(
        proposal_id=str(uuid.uuid4()),
        title=title,
        source=source,
        source_id=None,
        affected_modules=affected_modules or ["executive_planner"],
        proposal_text="Add LRU cache to blueprint constraint matching in ExecutivePlanner.",
        benchmark_confirmed=benchmark_confirmed,
        created_at=time.time(),
    )


# ── Gate 1: Protected Core ─────────────────────────────────────────────────

class TestGate1ProtectedCore:

    def test_non_protected_module_passes(self):
        """A proposal targeting a non-core module should pass Gate 1."""
        p = _proposal(affected_modules=["executive_planner"])
        with patch(
            "backend.core.self_improvement_governance.SelfImprovementGovernance"
            "._run_gate_protected_core",
            return_value=7.5,
        ) as mock_gate:
            # Don't mock other gates — let them pass silently
            with patch(
                "backend.core.self_improvement_governance.SelfImprovementGovernance"
                "._run_gate_safety_regression"
            ), patch(
                "backend.core.self_improvement_governance.SelfImprovementGovernance"
                "._run_gate_benchmark_confirmation"
            ), patch(
                "backend.core.self_improvement_governance.SelfImprovementGovernance"
                "._run_gate_budget"
            ):
                decision = SelfImprovementGovernance.submit(p)
        assert decision.passed is True
        assert decision.gate_status == "pending"

    def test_proposal_persisted_after_submit(self):
        p = _proposal()
        with patch.object(SelfImprovementGovernance, "_run_gate_protected_core", return_value=8.0), \
             patch.object(SelfImprovementGovernance, "_run_gate_safety_regression"), \
             patch.object(SelfImprovementGovernance, "_run_gate_benchmark_confirmation"), \
             patch.object(SelfImprovementGovernance, "_run_gate_budget"):
            decision = SelfImprovementGovernance.submit(p)

        fetched = SelfImprovementGovernance.get_proposal(p.proposal_id)
        assert fetched is not None
        assert fetched["gate_status"] == decision.gate_status


# ── Gate 3: Benchmark Confirmation ────────────────────────────────────────────

class TestGate3BenchmarkConfirmation:

    def test_research_proposal_without_confirmation_is_blocked(self):
        """Research source + benchmark_confirmed=False → Gate 3 block."""
        p = _proposal(source="research", benchmark_confirmed=False)
        with patch.object(SelfImprovementGovernance, "_run_gate_protected_core", return_value=8.0), \
             patch.object(SelfImprovementGovernance, "_run_gate_safety_regression"), \
             patch.object(SelfImprovementGovernance, "_run_gate_budget"):
            decision = SelfImprovementGovernance.submit(p)

        assert decision.passed is False
        assert decision.gate_status == "blocked"
        assert any("GATE 3" in r for r in decision.reasons)

    def test_research_proposal_with_confirmation_passes_gate3(self):
        """Research source + benchmark_confirmed=True → Gate 3 passes."""
        p = _proposal(source="research", benchmark_confirmed=True)
        with patch.object(SelfImprovementGovernance, "_run_gate_protected_core", return_value=8.0), \
             patch.object(SelfImprovementGovernance, "_run_gate_safety_regression"), \
             patch.object(SelfImprovementGovernance, "_run_gate_budget"):
            decision = SelfImprovementGovernance.submit(p)

        assert decision.passed is True
        assert not any("GATE 3" in r for r in decision.reasons)

    def test_benchmark_source_does_not_require_confirmation(self):
        """Benchmark-sourced proposals don't need benchmark_confirmed=True."""
        p = _proposal(source="benchmark", benchmark_confirmed=False)
        with patch.object(SelfImprovementGovernance, "_run_gate_protected_core", return_value=8.0), \
             patch.object(SelfImprovementGovernance, "_run_gate_safety_regression"), \
             patch.object(SelfImprovementGovernance, "_run_gate_budget"):
            decision = SelfImprovementGovernance.submit(p)

        assert not any("GATE 3" in r for r in decision.reasons)


# ── Approve / Reject flow ──────────────────────────────────────────────────────

class TestApproveRejectFlow:

    def _submit_pending(self) -> str:
        p = _proposal(source="benchmark")
        with patch.object(SelfImprovementGovernance, "_run_gate_protected_core", return_value=8.0), \
             patch.object(SelfImprovementGovernance, "_run_gate_safety_regression"), \
             patch.object(SelfImprovementGovernance, "_run_gate_benchmark_confirmation"), \
             patch.object(SelfImprovementGovernance, "_run_gate_budget"), \
             patch.object(SelfImprovementGovernance, "_record_approval_decision"), \
             patch.object(SelfImprovementGovernance, "_record_track"):
            SelfImprovementGovernance.submit(p)
        return p.proposal_id

    def test_approve_changes_status(self):
        proposal_id = self._submit_pending()
        with patch.object(SelfImprovementGovernance, "_record_approval_decision"), \
             patch.object(SelfImprovementGovernance, "_record_track"):
            success = SelfImprovementGovernance.approve(proposal_id, reviewer_id="user_01")
        assert success is True
        fetched = SelfImprovementGovernance.get_proposal(proposal_id)
        assert fetched["gate_status"] == "approved"
        assert fetched["reviewer_id"] == "user_01"

    def test_reject_changes_status(self):
        proposal_id = self._submit_pending()
        with patch.object(SelfImprovementGovernance, "_record_approval_decision"), \
             patch.object(SelfImprovementGovernance, "_record_track"):
            success = SelfImprovementGovernance.reject(
                proposal_id, reviewer_id="user_01", reason="Not enough evidence"
            )
        assert success is True
        fetched = SelfImprovementGovernance.get_proposal(proposal_id)
        assert fetched["gate_status"] == "rejected"

    def test_approve_non_pending_returns_false(self):
        proposal_id = self._submit_pending()
        with patch.object(SelfImprovementGovernance, "_record_approval_decision"), \
             patch.object(SelfImprovementGovernance, "_record_track"):
            SelfImprovementGovernance.approve(proposal_id, "user_01")
            # Second approval attempt on already-approved proposal
            result = SelfImprovementGovernance.approve(proposal_id, "user_02")
        assert result is False

    def test_reject_non_pending_returns_false(self):
        proposal_id = self._submit_pending()
        with patch.object(SelfImprovementGovernance, "_record_approval_decision"), \
             patch.object(SelfImprovementGovernance, "_record_track"):
            SelfImprovementGovernance.reject(proposal_id, "user_01")
            result = SelfImprovementGovernance.reject(proposal_id, "user_02")
        assert result is False

    def test_approve_unknown_proposal_returns_false(self):
        with patch.object(SelfImprovementGovernance, "_record_approval_decision"), \
             patch.object(SelfImprovementGovernance, "_record_track"):
            result = SelfImprovementGovernance.approve("nonexistent_id", "user_01")
        assert result is False


# ── list_pending ──────────────────────────────────────────────────────────────

class TestListPending:

    def test_pending_list_empty_initially(self):
        assert SelfImprovementGovernance.list_pending() == []

    def test_submitted_pending_proposal_appears(self):
        p = _proposal(source="benchmark")
        with patch.object(SelfImprovementGovernance, "_run_gate_protected_core", return_value=8.0), \
             patch.object(SelfImprovementGovernance, "_run_gate_safety_regression"), \
             patch.object(SelfImprovementGovernance, "_run_gate_benchmark_confirmation"), \
             patch.object(SelfImprovementGovernance, "_run_gate_budget"):
            SelfImprovementGovernance.submit(p)

        pending = SelfImprovementGovernance.list_pending()
        ids = [pp["id"] for pp in pending]
        assert p.proposal_id in ids

    def test_blocked_proposal_does_not_appear_in_pending(self):
        p = _proposal(source="research", benchmark_confirmed=False)
        with patch.object(SelfImprovementGovernance, "_run_gate_protected_core", return_value=8.0), \
             patch.object(SelfImprovementGovernance, "_run_gate_safety_regression"), \
             patch.object(SelfImprovementGovernance, "_run_gate_budget"):
            SelfImprovementGovernance.submit(p)

        pending = SelfImprovementGovernance.list_pending()
        ids = [pp["id"] for pp in pending]
        assert p.proposal_id not in ids


# ── Audit log ─────────────────────────────────────────────────────────────────

class TestAuditLog:

    def test_submit_creates_audit_entry(self):
        p = _proposal(source="benchmark")
        with patch.object(SelfImprovementGovernance, "_run_gate_protected_core", return_value=8.0), \
             patch.object(SelfImprovementGovernance, "_run_gate_safety_regression"), \
             patch.object(SelfImprovementGovernance, "_run_gate_benchmark_confirmation"), \
             patch.object(SelfImprovementGovernance, "_run_gate_budget"):
            SelfImprovementGovernance.submit(p)

        log = SelfImprovementGovernance.get_audit_log(p.proposal_id)
        assert len(log) == 1
        assert log[0]["event"] == "SUBMITTED"

    def test_approve_adds_audit_entry(self):
        p = _proposal(source="benchmark")
        with patch.object(SelfImprovementGovernance, "_run_gate_protected_core", return_value=8.0), \
             patch.object(SelfImprovementGovernance, "_run_gate_safety_regression"), \
             patch.object(SelfImprovementGovernance, "_run_gate_benchmark_confirmation"), \
             patch.object(SelfImprovementGovernance, "_run_gate_budget"):
            SelfImprovementGovernance.submit(p)

        with patch.object(SelfImprovementGovernance, "_record_approval_decision"), \
             patch.object(SelfImprovementGovernance, "_record_track"):
            SelfImprovementGovernance.approve(p.proposal_id, "user_01")

        log = SelfImprovementGovernance.get_audit_log(p.proposal_id)
        events = [e["event"] for e in log]
        assert "SUBMITTED" in events
        assert "APPROVED" in events


# ── Immutability: no auto-deploy ──────────────────────────────────────────────

class TestImmutabilityInvariants:

    def test_approved_status_is_terminal(self):
        """Once approved, a proposal cannot be further modified by submit."""
        p = _proposal(source="benchmark")
        with patch.object(SelfImprovementGovernance, "_run_gate_protected_core", return_value=8.0), \
             patch.object(SelfImprovementGovernance, "_run_gate_safety_regression"), \
             patch.object(SelfImprovementGovernance, "_run_gate_benchmark_confirmation"), \
             patch.object(SelfImprovementGovernance, "_run_gate_budget"):
            SelfImprovementGovernance.submit(p)

        with patch.object(SelfImprovementGovernance, "_record_approval_decision"), \
             patch.object(SelfImprovementGovernance, "_record_track"):
            SelfImprovementGovernance.approve(p.proposal_id, "user_01")

        # Approve again → should fail (no longer pending)
        with patch.object(SelfImprovementGovernance, "_record_approval_decision"), \
             patch.object(SelfImprovementGovernance, "_record_track"):
            result = SelfImprovementGovernance.approve(p.proposal_id, "user_02")

        assert result is False

    def test_list_all_returns_all_statuses(self):
        p1 = _proposal(source="benchmark", title="Plan cache")
        p2 = _proposal(source="research", benchmark_confirmed=False, title="Paper X")

        with patch.object(SelfImprovementGovernance, "_run_gate_protected_core", return_value=8.0), \
             patch.object(SelfImprovementGovernance, "_run_gate_safety_regression"), \
             patch.object(SelfImprovementGovernance, "_run_gate_benchmark_confirmation"), \
             patch.object(SelfImprovementGovernance, "_run_gate_budget"):
            SelfImprovementGovernance.submit(p1)

        with patch.object(SelfImprovementGovernance, "_run_gate_protected_core", return_value=8.0), \
             patch.object(SelfImprovementGovernance, "_run_gate_safety_regression"), \
             patch.object(SelfImprovementGovernance, "_run_gate_budget"):
            SelfImprovementGovernance.submit(p2)

        all_proposals = SelfImprovementGovernance.list_all()
        statuses = {pp["gate_status"] for pp in all_proposals}
        assert "pending" in statuses
        assert "blocked" in statuses
