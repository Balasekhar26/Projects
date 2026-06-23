"""
Step 7.2 — Approval Workflow Test Suite

Covers every mandatory requirement from the design freeze:
  ✓ Valid state transitions
  ✓ Invalid transition rejection
  ✓ Human gate enforcement (H1 and H2)
  ✓ Protected-core escalation to ELEVATED_REVIEW
  ✓ Append-only approval history
  ✓ Deployment requires human reviewer identity
  ✓ Memory-schema change requires approval
  ✓ Agent-modification requires approval
  ✓ Concurrent approval safety
  ✓ API endpoint validation
  ✓ Metrics computation (AAR, TTR, DAR, RAR)
  ✓ Terminal state immutability
  ✓ Forbidden short-circuit transitions
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.approval_workflow import (
    ApprovalWorkflow,
    ApprovalState,
    ChangeType,
    HUMAN_GATED_TYPES,
)
from backend.core.proposal_governance import ProtectedCoreRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_store(tmp_path: Path):
    """Patch the approval store to a temp file for test isolation."""
    store = tmp_path / "approval_workflow.json"
    return patch(
        "backend.core.approval_workflow._approval_store_path",
        return_value=store,
    )


# ---------------------------------------------------------------------------
# 1. State Machine — Valid Transitions
# ---------------------------------------------------------------------------

class TestValidTransitions:
    def test_submit_reaches_reviewing(self, tmp_path):
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit(
                proposal_id="p-1",
                change_type=ChangeType.CODE_CHANGE,
                title="Cache optimization",
                description="Add LRU cache",
            )
        assert r["state"] == ApprovalState.REVIEWING.value

    def test_approve_reaches_approved(self, tmp_path):
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit(
                "p-2", ChangeType.CODE_CHANGE, "Title", "Desc"
            )
            r2 = ApprovalWorkflow.approve(r["approval_id"], reviewer="alice")
        assert r2["state"] == ApprovalState.APPROVED.value
        assert r2["reviewer"] == "alice"

    def test_advance_to_testing(self, tmp_path):
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-3", ChangeType.CONFIG_CHANGE, "T", "D")
            r2 = ApprovalWorkflow.approve(r["approval_id"], reviewer="bob")
            r3 = ApprovalWorkflow.advance_to_testing(r["approval_id"])
        assert r3["state"] == ApprovalState.TESTING.value

    def test_deploy_reaches_deployed(self, tmp_path):
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-4", ChangeType.CODE_CHANGE, "T", "D")
            ApprovalWorkflow.approve(r["approval_id"], reviewer="carol")
            ApprovalWorkflow.advance_to_testing(r["approval_id"])
            r4 = ApprovalWorkflow.deploy(r["approval_id"], reviewer="carol")
        assert r4["state"] == ApprovalState.DEPLOYED.value

    def test_reject_from_reviewing(self, tmp_path):
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-5", ChangeType.CODE_CHANGE, "T", "D")
            r2 = ApprovalWorkflow.reject(r["approval_id"], reviewer="dave")
        assert r2["state"] == ApprovalState.REJECTED.value

    def test_reject_from_testing(self, tmp_path):
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-6", ChangeType.CODE_CHANGE, "T", "D")
            ApprovalWorkflow.approve(r["approval_id"], reviewer="eve")
            ApprovalWorkflow.advance_to_testing(r["approval_id"])
            r2 = ApprovalWorkflow.reject(r["approval_id"], reviewer="eve")
        assert r2["state"] == ApprovalState.REJECTED.value

    def test_full_happy_path_states(self, tmp_path):
        """All six states traversed in the happy path."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-full", ChangeType.CODE_CHANGE, "T", "D")
            aid = r["approval_id"]
            # REVIEWING (auto-advanced)
            assert ApprovalWorkflow.get(aid)["state"] == "REVIEWING"
            # APPROVED
            ApprovalWorkflow.approve(aid, reviewer="frank")
            assert ApprovalWorkflow.get(aid)["state"] == "APPROVED"
            # TESTING
            ApprovalWorkflow.advance_to_testing(aid)
            assert ApprovalWorkflow.get(aid)["state"] == "TESTING"
            # DEPLOYED
            ApprovalWorkflow.deploy(aid, reviewer="frank")
            assert ApprovalWorkflow.get(aid)["state"] == "DEPLOYED"


# ---------------------------------------------------------------------------
# 2. Invalid Transition Rejection
# ---------------------------------------------------------------------------

class TestInvalidTransitions:
    def test_proposed_to_deployed_forbidden(self, tmp_path):
        """Direct PROPOSED → DEPLOYED must be blocked."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-skip", ChangeType.CODE_CHANGE, "T", "D")
            # Manually set state back to PROPOSED to test the forbidden path
            records = ApprovalWorkflow._load()
            for rec in records:
                if rec["approval_id"] == r["approval_id"]:
                    rec["state"] = ApprovalState.PROPOSED.value
            ApprovalWorkflow._save(records)

            with pytest.raises(ValueError, match="forbidden"):
                ApprovalWorkflow.transition(
                    r["approval_id"],
                    ApprovalState.DEPLOYED,
                    actor="hacker",
                    reason="skip",
                    is_human=True,
                )

    def test_reviewing_to_deployed_forbidden(self, tmp_path):
        """REVIEWING → DEPLOYED must be blocked."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-skip2", ChangeType.CODE_CHANGE, "T", "D")
            with pytest.raises(ValueError, match="forbidden"):
                ApprovalWorkflow.transition(
                    r["approval_id"],
                    ApprovalState.DEPLOYED,
                    actor="hacker",
                    reason="skip",
                    is_human=True,
                )

    def test_approved_to_deployed_forbidden(self, tmp_path):
        """APPROVED → DEPLOYED (skipping TESTING) must be blocked."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-skip3", ChangeType.CODE_CHANGE, "T", "D")
            ApprovalWorkflow.approve(r["approval_id"], reviewer="grace")
            with pytest.raises(ValueError, match="forbidden"):
                ApprovalWorkflow.transition(
                    r["approval_id"],
                    ApprovalState.DEPLOYED,
                    actor="grace",
                    reason="skip TESTING",
                    is_human=True,
                )

    def test_undefined_transition_raises(self, tmp_path):
        """Undefined transition (e.g. DEPLOYED → REVIEWING) raises ValueError."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-undef", ChangeType.CODE_CHANGE, "T", "D")
            ApprovalWorkflow.approve(r["approval_id"], reviewer="hr")
            ApprovalWorkflow.advance_to_testing(r["approval_id"])
            ApprovalWorkflow.deploy(r["approval_id"], reviewer="hr")
            with pytest.raises(ValueError, match="terminal"):
                ApprovalWorkflow.transition(
                    r["approval_id"],
                    ApprovalState.REVIEWING,
                    actor="hr",
                    reason="loop",
                    is_human=True,
                )

    def test_nonexistent_approval_raises(self, tmp_path):
        with _fresh_store(tmp_path):
            with pytest.raises(ValueError, match="not found"):
                ApprovalWorkflow.transition(
                    "appr_nonexistent",
                    ApprovalState.APPROVED,
                    actor="x",
                    reason="x",
                    is_human=True,
                )


# ---------------------------------------------------------------------------
# 3. Human Gate Enforcement
# ---------------------------------------------------------------------------

class TestHumanGateEnforcement:
    """System actors must never be able to execute human-only transitions."""

    def test_system_cannot_approve(self, tmp_path):
        """REVIEWING → APPROVED by system actor must raise."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-sys-approve", ChangeType.CODE_CHANGE, "T", "D")
            with pytest.raises(ValueError, match="human authorization"):
                ApprovalWorkflow.transition(
                    r["approval_id"],
                    ApprovalState.APPROVED,
                    actor="system",
                    reason="auto",
                    is_human=False,
                )

    def test_system_cannot_reject(self, tmp_path):
        """REVIEWING → REJECTED by system actor must raise."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-sys-reject", ChangeType.CODE_CHANGE, "T", "D")
            with pytest.raises(ValueError, match="human authorization"):
                ApprovalWorkflow.transition(
                    r["approval_id"],
                    ApprovalState.REJECTED,
                    actor="system",
                    reason="auto-reject",
                    is_human=False,
                )

    def test_system_cannot_deploy(self, tmp_path):
        """TESTING → DEPLOYED by system actor must raise."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-sys-deploy", ChangeType.CODE_CHANGE, "T", "D")
            ApprovalWorkflow.approve(r["approval_id"], reviewer="ian")
            ApprovalWorkflow.advance_to_testing(r["approval_id"])
            with pytest.raises(ValueError, match="human authorization"):
                ApprovalWorkflow.transition(
                    r["approval_id"],
                    ApprovalState.DEPLOYED,
                    actor="system",
                    reason="auto-deploy",
                    is_human=False,
                )

    def test_deploy_rejects_system_reviewer_identity(self, tmp_path):
        """deploy() specifically rejects 'system' as reviewer identity."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-sys-identity", ChangeType.CODE_CHANGE, "T", "D")
            ApprovalWorkflow.approve(r["approval_id"], reviewer="jan")
            ApprovalWorkflow.advance_to_testing(r["approval_id"])
            with pytest.raises(ValueError, match="human reviewer identity"):
                ApprovalWorkflow.deploy(r["approval_id"], reviewer="system")

    def test_deploy_rejects_empty_reviewer(self, tmp_path):
        """deploy() rejects empty-string reviewer."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-empty-reviewer", ChangeType.CODE_CHANGE, "T", "D")
            ApprovalWorkflow.approve(r["approval_id"], reviewer="jan")
            ApprovalWorkflow.advance_to_testing(r["approval_id"])
            with pytest.raises(ValueError, match="human reviewer identity"):
                ApprovalWorkflow.deploy(r["approval_id"], reviewer="")

    def test_system_can_advance_to_testing(self, tmp_path):
        """APPROVED → TESTING is a system-allowed transition (sandbox passed)."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-sys-testing", ChangeType.CODE_CHANGE, "T", "D")
            ApprovalWorkflow.approve(r["approval_id"], reviewer="ken")
            r2 = ApprovalWorkflow.advance_to_testing(r["approval_id"])
        assert r2["state"] == ApprovalState.TESTING.value

    def test_human_gated_types_set_is_correct(self):
        """CODE_CHANGE, MEMORY_SCHEMA_CHANGE, and AGENT_MODIFICATION are human-gated."""
        assert ChangeType.CODE_CHANGE in HUMAN_GATED_TYPES
        assert ChangeType.MEMORY_SCHEMA_CHANGE in HUMAN_GATED_TYPES
        assert ChangeType.AGENT_MODIFICATION in HUMAN_GATED_TYPES
        assert ChangeType.CONFIG_CHANGE not in HUMAN_GATED_TYPES
        assert ChangeType.DOCUMENTATION not in HUMAN_GATED_TYPES


# ---------------------------------------------------------------------------
# 4. Protected Core Escalation
# ---------------------------------------------------------------------------

class TestProtectedCoreEscalation:
    def test_approval_workflow_module_escalates(self, tmp_path):
        """Proposals touching approval_workflow itself escalate to ELEVATED_REVIEW."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit(
                "p-self",
                ChangeType.CODE_CHANGE,
                "Modify Approval Workflow",
                "Patch the approval engine",
                affected_modules=["approval_workflow"],
            )
        assert r["state"] == ApprovalState.ELEVATED_REVIEW.value
        assert r["protected_core"] is True

    def test_consensus_engine_escalates(self, tmp_path):
        """Proposals touching consensus_engine escalate to ELEVATED_REVIEW."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit(
                "p-consensus",
                ChangeType.CODE_CHANGE,
                "Tune consensus thresholds",
                "Change quorum size",
                affected_modules=["consensus_engine"],
            )
        assert r["state"] == ApprovalState.ELEVATED_REVIEW.value

    def test_proposal_governance_escalates(self, tmp_path):
        """Proposals touching proposal_governance escalate to ELEVATED_REVIEW."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit(
                "p-gov",
                ChangeType.CODE_CHANGE,
                "Relax governance rules",
                "Allow faster approvals",
                affected_modules=["proposal_governance"],
            )
        assert r["state"] == ApprovalState.ELEVATED_REVIEW.value

    def test_safe_module_does_not_escalate(self, tmp_path):
        """Safe modules go to standard REVIEWING."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit(
                "p-safe",
                ChangeType.CODE_CHANGE,
                "Improve cache",
                "Add LRU",
                affected_modules=["translator_cache"],
            )
        assert r["state"] == ApprovalState.REVIEWING.value
        assert r["protected_core"] is False

    def test_keyword_in_description_escalates(self, tmp_path):
        """Keyword 'approval_workflow' in free-text description triggers escalation."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit(
                "p-kw",
                ChangeType.CODE_CHANGE,
                "Improve performance",
                "This touches the approval_workflow internals to speed up review.",
            )
        assert r["protected_core"] is True
        assert r["state"] == ApprovalState.ELEVATED_REVIEW.value

    def test_elevated_review_requires_human_to_approve(self, tmp_path):
        """ELEVATED_REVIEW → APPROVED requires is_human=True."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit(
                "p-elev-gate",
                ChangeType.CODE_CHANGE,
                "T",
                "D",
                affected_modules=["consensus_engine"],
            )
            assert r["state"] == ApprovalState.ELEVATED_REVIEW.value
            # System cannot approve elevated review
            with pytest.raises(ValueError, match="human authorization"):
                ApprovalWorkflow.transition(
                    r["approval_id"],
                    ApprovalState.APPROVED,
                    actor="system",
                    reason="auto",
                    is_human=False,
                )
            # Human can
            r2 = ApprovalWorkflow.approve(r["approval_id"], reviewer="lena")
        assert r2["state"] == ApprovalState.APPROVED.value

    def test_approval_workflow_is_in_protected_modules(self):
        """approval_workflow is registered in ProtectedCoreRegistry.PROTECTED_MODULES."""
        assert "approval_workflow" in ProtectedCoreRegistry.PROTECTED_MODULES


# ---------------------------------------------------------------------------
# 5. Append-Only Approval History
# ---------------------------------------------------------------------------

class TestAppendOnlyHistory:
    def test_events_grow_monotonically(self, tmp_path):
        """Event count strictly increases with each transition."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-events", ChangeType.CODE_CHANGE, "T", "D")
            aid = r["approval_id"]
            assert len(ApprovalWorkflow.get_events(aid)) == 2  # SUBMITTED + ADVANCED

            ApprovalWorkflow.approve(aid, reviewer="mike")
            assert len(ApprovalWorkflow.get_events(aid)) == 3

            ApprovalWorkflow.advance_to_testing(aid)
            assert len(ApprovalWorkflow.get_events(aid)) == 4

            ApprovalWorkflow.deploy(aid, reviewer="mike")
            assert len(ApprovalWorkflow.get_events(aid)) == 5

    def test_events_preserve_all_actors(self, tmp_path):
        """Every event preserves the actor who performed it."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-actors", ChangeType.CODE_CHANGE, "T", "D",
                                        submitter="pipeline")
            aid = r["approval_id"]
            ApprovalWorkflow.approve(aid, reviewer="nina")
            ApprovalWorkflow.advance_to_testing(aid)
            ApprovalWorkflow.deploy(aid, reviewer="oscar")

            events = ApprovalWorkflow.get_events(aid)
            actors = [e["actor"] for e in events]
            assert "pipeline" in actors
            assert "nina" in actors
            assert "system" in actors
            assert "oscar" in actors

    def test_rejection_event_recorded_with_reason(self, tmp_path):
        """Rejection records the reason in the event ledger."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-reject-reason", ChangeType.CODE_CHANGE, "T", "D")
            aid = r["approval_id"]
            ApprovalWorkflow.reject(aid, reviewer="pam", reason="Too risky.")

            events = ApprovalWorkflow.get_events(aid)
            reject_events = [e for e in events if "REJECTED" in e["event"]]
            assert len(reject_events) == 1
            assert reject_events[0]["reason"] == "Too risky."

    def test_events_list_is_immutable_across_reads(self, tmp_path):
        """Loading the same record twice returns identical events."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-immutable", ChangeType.CODE_CHANGE, "T", "D")
            aid = r["approval_id"]
            ApprovalWorkflow.approve(aid, reviewer="quinn")

            events_a = ApprovalWorkflow.get_events(aid)
            events_b = ApprovalWorkflow.get_events(aid)
            assert json.dumps(events_a) == json.dumps(events_b)

    def test_no_update_operation_on_existing_events(self, tmp_path):
        """An event once written never disappears from the ledger."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-no-update", ChangeType.CODE_CHANGE, "T", "D")
            aid = r["approval_id"]
            first_events = ApprovalWorkflow.get_events(aid).copy()

            ApprovalWorkflow.approve(aid, reviewer="rita")
            second_events = ApprovalWorkflow.get_events(aid)

            # All original events must still be present
            for e in first_events:
                assert e in second_events


# ---------------------------------------------------------------------------
# 6. Change-Type-Specific Requirements
# ---------------------------------------------------------------------------

class TestChangeTypeRequirements:
    @pytest.mark.parametrize("change_type", [
        ChangeType.MEMORY_SCHEMA_CHANGE,
        ChangeType.AGENT_MODIFICATION,
        ChangeType.CODE_CHANGE,
    ])
    def test_human_gated_types_require_human_approval(self, change_type, tmp_path):
        """All three human-gated types cannot be approved by the system."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit(
                f"p-{change_type.value}", change_type, "T", "D"
            )
            with pytest.raises(ValueError, match="human authorization"):
                ApprovalWorkflow.transition(
                    r["approval_id"],
                    ApprovalState.APPROVED,
                    actor="system",
                    reason="auto",
                    is_human=False,
                )

    def test_memory_schema_change_full_workflow(self, tmp_path):
        """A MEMORY_SCHEMA_CHANGE can complete the full workflow with human gates."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit(
                "p-mem-schema",
                ChangeType.MEMORY_SCHEMA_CHANGE,
                "Add new index",
                "Add composite index to episodic_memory",
            )
            assert r["change_type"] == "MEMORY_SCHEMA_CHANGE"
            ApprovalWorkflow.approve(r["approval_id"], reviewer="sam")
            ApprovalWorkflow.advance_to_testing(r["approval_id"])
            result = ApprovalWorkflow.deploy(r["approval_id"], reviewer="sam")
        assert result["state"] == ApprovalState.DEPLOYED.value

    def test_agent_modification_full_workflow(self, tmp_path):
        """An AGENT_MODIFICATION can complete the full workflow with human gates."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit(
                "p-agent-mod",
                ChangeType.AGENT_MODIFICATION,
                "Tune reflection agent",
                "Adjust significance threshold",
            )
            assert r["change_type"] == "AGENT_MODIFICATION"
            ApprovalWorkflow.approve(r["approval_id"], reviewer="tara")
            ApprovalWorkflow.advance_to_testing(r["approval_id"])
            result = ApprovalWorkflow.deploy(r["approval_id"], reviewer="tara")
        assert result["state"] == ApprovalState.DEPLOYED.value

    def test_change_type_stored_in_record(self, tmp_path):
        """change_type is persisted in the approval record."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit(
                "p-ct-persist", ChangeType.DOCUMENTATION, "Update docs", "Fix typo"
            )
        assert r["change_type"] == ChangeType.DOCUMENTATION.value


# ---------------------------------------------------------------------------
# 7. Terminal State Immutability
# ---------------------------------------------------------------------------

class TestTerminalStateImmutability:
    def test_deployed_is_terminal(self, tmp_path):
        """No transition out of DEPLOYED is allowed."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-term-deployed", ChangeType.CODE_CHANGE, "T", "D")
            ApprovalWorkflow.approve(r["approval_id"], reviewer="uma")
            ApprovalWorkflow.advance_to_testing(r["approval_id"])
            ApprovalWorkflow.deploy(r["approval_id"], reviewer="uma")

            with pytest.raises(ValueError, match="terminal"):
                ApprovalWorkflow.approve(r["approval_id"], reviewer="uma")

    def test_rejected_is_terminal(self, tmp_path):
        """No transition out of REJECTED is allowed."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-term-rejected", ChangeType.CODE_CHANGE, "T", "D")
            ApprovalWorkflow.reject(r["approval_id"], reviewer="vic")
            with pytest.raises(ValueError, match="terminal"):
                ApprovalWorkflow.approve(r["approval_id"], reviewer="vic")

    def test_deployed_and_rejected_are_terminal_states(self):
        """ApprovalState.is_terminal reflects the design."""
        assert ApprovalState.DEPLOYED.is_terminal is True
        assert ApprovalState.REJECTED.is_terminal is True
        assert ApprovalState.APPROVED.is_terminal is False
        assert ApprovalState.REVIEWING.is_terminal is False
        assert ApprovalState.TESTING.is_terminal is False


# ---------------------------------------------------------------------------
# 8. Concurrent Approval Safety
# ---------------------------------------------------------------------------

class TestConcurrentApprovalSafety:
    def test_concurrent_submissions_produce_distinct_ids(self, tmp_path):
        """Concurrent submissions produce distinct approval IDs."""
        ids: list[str] = []
        errors: list[Exception] = []

        def _submit(i: int) -> None:
            try:
                r = ApprovalWorkflow.submit(
                    f"p-conc-{i}", ChangeType.CODE_CHANGE, f"Title {i}", "Desc"
                )
                ids.append(r["approval_id"])
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_submit, args=(i,)) for i in range(10)]
        with _fresh_store(tmp_path):
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        assert not errors, f"Concurrent submit errors: {errors}"
        assert len(ids) == 10
        assert len(set(ids)) == 10, "Duplicate approval IDs detected"

    def test_concurrent_approvals_do_not_corrupt_history(self, tmp_path):
        """Approving two different records concurrently preserves both event ledgers."""
        aids: list[str] = []
        with _fresh_store(tmp_path):
            for i in range(4):
                r = ApprovalWorkflow.submit(
                    f"p-concr-{i}", ChangeType.CONFIG_CHANGE, "T", "D"
                )
                aids.append(r["approval_id"])

            errors: list[Exception] = []

            def _approve(aid: str) -> None:
                try:
                    ApprovalWorkflow.approve(aid, reviewer="wendy")
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=_approve, args=(aid,)) for aid in aids]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

            assert not errors, f"Concurrent approval errors: {errors}"
            for aid in aids:
                record = ApprovalWorkflow.get(aid)
                assert record is not None
                assert record["state"] == ApprovalState.APPROVED.value
                assert len(ApprovalWorkflow.get_events(aid)) >= 3


# ---------------------------------------------------------------------------
# 9. Metrics
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_empty_metrics_returns_none_ratios(self, tmp_path):
        with _fresh_store(tmp_path):
            m = ApprovalWorkflow.metrics()
        assert m["AAR"] is None
        assert m["DAR"] is None
        assert m["RAR"] is None
        assert m["TTR_seconds_mean"] is None
        assert m["total"] == 0

    def test_aar_after_one_approval(self, tmp_path):
        """AAR = 1.0 when one record is reviewed and approved."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-aar", ChangeType.CONFIG_CHANGE, "T", "D")
            ApprovalWorkflow.approve(r["approval_id"], reviewer="xavier")
            m = ApprovalWorkflow.metrics()
        assert m["AAR"] == 1.0

    def test_dar_after_deployment(self, tmp_path):
        """DAR = 1.0 when one approved record is deployed."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-dar", ChangeType.CONFIG_CHANGE, "T", "D")
            ApprovalWorkflow.approve(r["approval_id"], reviewer="yvonne")
            ApprovalWorkflow.advance_to_testing(r["approval_id"])
            ApprovalWorkflow.deploy(r["approval_id"], reviewer="yvonne")
            m = ApprovalWorkflow.metrics()
        assert m["DAR"] == 1.0

    def test_rar_after_rejection_from_testing(self, tmp_path):
        """RAR = 1.0 when every tested record is subsequently rejected."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-rar", ChangeType.CODE_CHANGE, "T", "D")
            ApprovalWorkflow.approve(r["approval_id"], reviewer="zoe")
            ApprovalWorkflow.advance_to_testing(r["approval_id"])
            ApprovalWorkflow.reject(r["approval_id"], reviewer="zoe", reason="Perf regression.")
            m = ApprovalWorkflow.metrics()
        assert m["RAR"] == 1.0

    def test_ttr_mean_computed(self, tmp_path):
        """TTR mean is a non-negative number after one review cycle."""
        with _fresh_store(tmp_path):
            r = ApprovalWorkflow.submit("p-ttr", ChangeType.CONFIG_CHANGE, "T", "D")
            # Small delay to create measurable TTR
            time.sleep(0.05)
            ApprovalWorkflow.approve(r["approval_id"], reviewer="abel")
            m = ApprovalWorkflow.metrics()
        assert m["TTR_seconds_mean"] is not None
        assert m["TTR_seconds_mean"] >= 0.0

    def test_metrics_counts_match_reality(self, tmp_path):
        """total, approved, deployed counts match the actual records."""
        with _fresh_store(tmp_path):
            for i in range(3):
                r = ApprovalWorkflow.submit(f"p-cnt-{i}", ChangeType.CONFIG_CHANGE, "T", "D")
                ApprovalWorkflow.approve(r["approval_id"], reviewer="bea")
            # Deploy one
            all_records = ApprovalWorkflow.list_all(state="APPROVED")
            ApprovalWorkflow.advance_to_testing(all_records[0]["approval_id"])
            ApprovalWorkflow.deploy(all_records[0]["approval_id"], reviewer="bea")

            m = ApprovalWorkflow.metrics()
        assert m["total"] == 3
        assert m["deployed"] == 1


# ---------------------------------------------------------------------------
# 10. API Endpoint Validation
# ---------------------------------------------------------------------------

class TestApprovalAPI:
    """End-to-end tests against the FastAPI application."""

    def test_submit_endpoint(self, tmp_path):
        with _fresh_store(tmp_path):
            client = TestClient(app)
            resp = client.post("/approval/submit", json={
                "proposal_id": "p-api-sub",
                "change_type": "CODE_CHANGE",
                "title": "API Test Proposal",
                "description": "Testing submission via API",
                "affected_modules": [],
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "submitted"
        assert data["record"]["state"] in {"REVIEWING", "ELEVATED_REVIEW"}

    def test_approve_endpoint(self, tmp_path):
        with _fresh_store(tmp_path):
            client = TestClient(app)
            sub = client.post("/approval/submit", json={
                "proposal_id": "p-api-app",
                "change_type": "CONFIG_CHANGE",
                "title": "T",
                "description": "D",
            }).json()
            aid = sub["record"]["approval_id"]

            resp = client.post(f"/approval/approve/{aid}", json={
                "reviewer": "api-human",
                "reason": "Looks good.",
            })
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"
        assert resp.json()["record"]["state"] == "APPROVED"

    def test_reject_endpoint(self, tmp_path):
        with _fresh_store(tmp_path):
            client = TestClient(app)
            sub = client.post("/approval/submit", json={
                "proposal_id": "p-api-rej",
                "change_type": "CODE_CHANGE",
                "title": "T",
                "description": "D",
            }).json()
            aid = sub["record"]["approval_id"]

            resp = client.post(f"/approval/reject/{aid}", json={
                "reviewer": "api-human",
                "reason": "Not ready.",
            })
        assert resp.status_code == 200
        assert resp.json()["record"]["state"] == "REJECTED"

    def test_full_pipeline_via_api(self, tmp_path):
        """Submit → Approve → AdvanceToTesting → Deploy via API."""
        with _fresh_store(tmp_path):
            client = TestClient(app)
            sub = client.post("/approval/submit", json={
                "proposal_id": "p-api-full",
                "change_type": "CODE_CHANGE",
                "title": "Full Pipeline",
                "description": "All four API steps",
            }).json()
            aid = sub["record"]["approval_id"]

            client.post(f"/approval/approve/{aid}", json={"reviewer": "api-human"})
            client.post(f"/approval/advance-to-testing/{aid}")
            deploy_resp = client.post(f"/approval/deploy/{aid}", json={
                "reviewer": "api-deployer",
                "reason": "Staging passed.",
            })
        assert deploy_resp.status_code == 200
        assert deploy_resp.json()["record"]["state"] == "DEPLOYED"
        assert deploy_resp.json()["record"]["reviewer"] == "api-deployer"

    def test_deploy_with_system_reviewer_returns_error(self, tmp_path):
        """API deploy with reviewer='system' must return an error."""
        with _fresh_store(tmp_path):
            client = TestClient(app)
            sub = client.post("/approval/submit", json={
                "proposal_id": "p-api-sysrev",
                "change_type": "CODE_CHANGE",
                "title": "T",
                "description": "D",
            }).json()
            aid = sub["record"]["approval_id"]

            client.post(f"/approval/approve/{aid}", json={"reviewer": "human"})
            client.post(f"/approval/advance-to-testing/{aid}")
            resp = client.post(f"/approval/deploy/{aid}", json={"reviewer": "system"})

        assert resp.json()["status"] == "error"
        assert "human reviewer identity" in resp.json()["message"]

    def test_get_endpoint(self, tmp_path):
        with _fresh_store(tmp_path):
            client = TestClient(app)
            sub = client.post("/approval/submit", json={
                "proposal_id": "p-api-get",
                "change_type": "DOCUMENTATION",
                "title": "T",
                "description": "D",
            }).json()
            aid = sub["record"]["approval_id"]

            resp = client.get(f"/approval/get/{aid}")
        assert resp.status_code == 200
        assert resp.json()["record"]["approval_id"] == aid

    def test_list_endpoint_filters_by_state(self, tmp_path):
        with _fresh_store(tmp_path):
            client = TestClient(app)
            for i in range(3):
                client.post("/approval/submit", json={
                    "proposal_id": f"p-api-list-{i}",
                    "change_type": "CONFIG_CHANGE",
                    "title": "T",
                    "description": "D",
                })
            resp = client.get("/approval/list?state=REVIEWING")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert all(r["state"] == "REVIEWING" for r in data["records"])

    def test_events_endpoint(self, tmp_path):
        with _fresh_store(tmp_path):
            client = TestClient(app)
            sub = client.post("/approval/submit", json={
                "proposal_id": "p-api-events",
                "change_type": "CODE_CHANGE",
                "title": "T",
                "description": "D",
            }).json()
            aid = sub["record"]["approval_id"]

            resp = client.get(f"/approval/events/{aid}")
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert len(events) >= 2
        assert events[0]["event"] == "SUBMITTED"

    def test_metrics_endpoint(self, tmp_path):
        with _fresh_store(tmp_path):
            client = TestClient(app)
            resp = client.get("/approval/metrics")
        assert resp.status_code == 200
        m = resp.json()["metrics"]
        assert "AAR" in m
        assert "TTR_seconds_mean" in m
        assert "DAR" in m
        assert "RAR" in m

    def test_get_nonexistent_returns_not_found(self, tmp_path):
        with _fresh_store(tmp_path):
            client = TestClient(app)
            resp = client.get("/approval/get/appr_doesnotexist")
        assert resp.json()["status"] == "not_found"
