"""
Approval Workflow — Step 7.2

Implements the human-gated approval pipeline that bridges
"interesting idea" and "allowed to affect the system".

Architecture contract:
  - ONLY humans may transition REVIEWING → APPROVED/REJECTED
  - ONLY humans may transition TESTING → DEPLOYED
  - The system may NEVER autonomously transition any state
  - The Approval Workflow is itself Protected Core (self-modification blocked)
  - All records are append-only; history is never overwritten

State machine (terminal states: REJECTED, DEPLOYED):

  PROPOSED → REVIEWING → APPROVED → TESTING → DEPLOYED
                       ↘ REJECTED          ↘ REJECTED

  Protected-core proposals additionally require:
  REVIEWING → ELEVATED_REVIEW → APPROVED

Change types that require human approval at Gate H1 (REVIEWING→APPROVED)
and Gate H2 (TESTING→DEPLOYED):
  CODE_CHANGE
  MEMORY_SCHEMA_CHANGE
  AGENT_MODIFICATION

All other change types (CONFIG_CHANGE, DOCUMENTATION) pass Gate H1 with
system-generated recommendation but still require an explicit human call
for Gate H2.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root
from backend.core.logger import log_event
from backend.core.proposal_governance import ProtectedCoreRegistry


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ApprovalState(str, Enum):
    PROPOSED        = "PROPOSED"
    REVIEWING       = "REVIEWING"
    ELEVATED_REVIEW = "ELEVATED_REVIEW"   # protected-core escalation only
    APPROVED        = "APPROVED"
    REJECTED        = "REJECTED"          # terminal
    TESTING         = "TESTING"
    DEPLOYED        = "DEPLOYED"          # terminal

    @property
    def is_terminal(self) -> bool:
        return self in {ApprovalState.REJECTED, ApprovalState.DEPLOYED}


class ChangeType(str, Enum):
    CODE_CHANGE           = "CODE_CHANGE"
    MEMORY_SCHEMA_CHANGE  = "MEMORY_SCHEMA_CHANGE"
    AGENT_MODIFICATION    = "AGENT_MODIFICATION"
    CONFIG_CHANGE         = "CONFIG_CHANGE"
    DOCUMENTATION         = "DOCUMENTATION"


# Change types that require mandatory human approval at both H1 and H2
HUMAN_GATED_TYPES: frozenset[ChangeType] = frozenset({
    ChangeType.CODE_CHANGE,
    ChangeType.MEMORY_SCHEMA_CHANGE,
    ChangeType.AGENT_MODIFICATION,
})

# Protected-core modules that trigger ELEVATED_REVIEW
ELEVATED_REVIEW_MODULES: frozenset[str] = frozenset({
    "proposal_governance",
    "consensus_engine",
    "execution_policy",
    "validators",
    "value_engine",
    "approval_workflow",
    "experiment_sandbox",
})


# ---------------------------------------------------------------------------
# Allowed transitions
# ---------------------------------------------------------------------------

# (from_state, to_state) → who_may_trigger  ("human" | "system")
_ALLOWED_TRANSITIONS: dict[tuple[ApprovalState, ApprovalState], str] = {
    # System-initiated (automatic)
    (ApprovalState.PROPOSED, ApprovalState.REVIEWING):            "system",
    (ApprovalState.PROPOSED, ApprovalState.ELEVATED_REVIEW):      "system",
    (ApprovalState.APPROVED, ApprovalState.TESTING):              "system",

    # Human-only
    (ApprovalState.REVIEWING,       ApprovalState.APPROVED):  "human",
    (ApprovalState.REVIEWING,       ApprovalState.REJECTED):  "human",
    (ApprovalState.ELEVATED_REVIEW, ApprovalState.APPROVED):  "human",
    (ApprovalState.ELEVATED_REVIEW, ApprovalState.REJECTED):  "human",
    (ApprovalState.TESTING,         ApprovalState.DEPLOYED):  "human",
    (ApprovalState.TESTING,         ApprovalState.REJECTED):  "human",
}

# Forbidden short-circuits (never allowed, regardless of who asks)
_FORBIDDEN_TRANSITIONS: set[tuple[ApprovalState, ApprovalState]] = {
    (ApprovalState.PROPOSED,  ApprovalState.DEPLOYED),
    (ApprovalState.REVIEWING, ApprovalState.DEPLOYED),
    (ApprovalState.APPROVED,  ApprovalState.DEPLOYED),
}


# ---------------------------------------------------------------------------
# Storage path
# ---------------------------------------------------------------------------

def _approval_store_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "approval_workflow.json"


# ---------------------------------------------------------------------------
# Core Engine
# ---------------------------------------------------------------------------

class ApprovalWorkflow:
    """
    Append-only approval ledger and state-machine enforcer.

    Rules enforced here (not just documented):
      1. No forbidden short-circuit transitions ever succeed.
      2. Human-only transitions reject system callers unconditionally.
      3. Protected-core proposals are escalated to ELEVATED_REVIEW automatically.
      4. Every state change appends a new event; history is never mutated.
      5. ApprovalWorkflow is Protected Core — nothing may self-modify it.
    """

    _lock = threading.RLock()

    # -- Storage -------------------------------------------------------------

    @classmethod
    def _load(cls) -> list[dict[str, Any]]:
        with cls._lock:
            path = _approval_store_path()
            if not path.exists():
                return []
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []

    @classmethod
    def _save(cls, records: list[dict[str, Any]]) -> None:
        with cls._lock:
            path = _approval_store_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    # -- Helpers -------------------------------------------------------------

    @classmethod
    def _requires_elevated_review(
        cls,
        affected_modules: list[str],
        proposal_text: str,
    ) -> bool:
        """Return True if proposal touches a protected-core module."""
        for mod in affected_modules:
            cleaned = mod.strip().lower().removesuffix(".py")
            if cleaned in ELEVATED_REVIEW_MODULES:
                return True
            if ProtectedCoreRegistry.is_transitively_protected(cleaned):
                return True
        # Also check free-text keyword scan
        text_lower = proposal_text.lower()
        for kw in ELEVATED_REVIEW_MODULES:
            if kw in text_lower:
                return True
        return False

    @classmethod
    def _validate_transition(
        cls,
        current: ApprovalState,
        target: ApprovalState,
        is_human: bool,
    ) -> str | None:
        """Return an error string if transition is invalid, else None."""
        if current.is_terminal:
            return f"Cannot transition from terminal state {current.value}."

        if (current, target) in _FORBIDDEN_TRANSITIONS:
            return (
                f"Transition {current.value} → {target.value} is explicitly forbidden. "
                "No autonomous path to DEPLOYED exists."
            )

        allowed = _ALLOWED_TRANSITIONS.get((current, target))
        if allowed is None:
            return f"Transition {current.value} → {target.value} is not a defined workflow step."

        if allowed == "human" and not is_human:
            return (
                f"Transition {current.value} → {target.value} requires human authorization. "
                "The system may never autonomously execute this transition."
            )

        return None

    # -- Public API ----------------------------------------------------------

    @classmethod
    def submit(
        cls,
        proposal_id: str,
        change_type: ChangeType | str,
        title: str,
        description: str,
        affected_modules: list[str] | None = None,
        submitter: str = "system",
    ) -> dict[str, Any]:
        """Create a new approval request in PROPOSED state.

        Immediately advances to REVIEWING or ELEVATED_REVIEW (system action).
        """
        with cls._lock:
            change_type = ChangeType(change_type)
            affected_modules = affected_modules or []

            approval_id = f"appr_{uuid.uuid4().hex[:12]}"
            now = time.time()

            # Determine initial review tier
            needs_elevated = cls._requires_elevated_review(
                affected_modules,
                f"{title} {description}",
            )
            review_state = (
                ApprovalState.ELEVATED_REVIEW
                if needs_elevated
                else ApprovalState.REVIEWING
            )

            record: dict[str, Any] = {
                "approval_id": approval_id,
                "proposal_id": proposal_id,
                "change_type": change_type.value,
                "title": title,
                "description": description,
                "affected_modules": affected_modules,
                "protected_core": needs_elevated,
                "state": ApprovalState.PROPOSED.value,
                "reviewer": None,
                "reason": None,
                "created_at": now,
                "updated_at": now,
                # Metrics timestamps
                "review_started_at": None,
                "review_ended_at": None,
                "testing_started_at": None,
                "deployed_at": None,
                # Immutable event ledger
                "events": [
                    {
                        "event": "SUBMITTED",
                        "from_state": None,
                        "to_state": ApprovalState.PROPOSED.value,
                        "actor": submitter,
                        "timestamp": now,
                        "reason": "Initial submission",
                    }
                ],
            }

            # System auto-advances PROPOSED → REVIEWING / ELEVATED_REVIEW
            transition_err = cls._validate_transition(
                ApprovalState.PROPOSED, review_state, is_human=False
            )
            if transition_err:
                log_event(f"approval_workflow: auto-advance blocked: {transition_err}")
            else:
                record["state"] = review_state.value
                record["review_started_at"] = now
                record["events"].append({
                    "event": "ADVANCED",
                    "from_state": ApprovalState.PROPOSED.value,
                    "to_state": review_state.value,
                    "actor": "system",
                    "timestamp": now,
                    "reason": (
                        "Automatic escalation: protected core touch detected."
                        if needs_elevated
                        else "Automatic advancement to REVIEWING."
                    ),
                })

            records = cls._load()
            records.append(record)
            cls._save(records)

            log_event(
                f"approval_workflow: submitted {approval_id} "
                f"(proposal={proposal_id}, type={change_type.value}, "
                f"state={record['state']}, elevated={needs_elevated})"
            )
            return record

    @classmethod
    def transition(
        cls,
        approval_id: str,
        target_state: ApprovalState | str,
        actor: str,
        reason: str,
        is_human: bool,
    ) -> dict[str, Any]:
        """Attempt a state transition. Returns the updated record or raises ValueError."""
        with cls._lock:
            target_state = ApprovalState(target_state)
            records = cls._load()

            record = next(
                (r for r in records if r["approval_id"] == approval_id), None
            )
            if record is None:
                raise ValueError(f"Approval record not found: {approval_id}")

            current = ApprovalState(record["state"])

            error = cls._validate_transition(current, target_state, is_human=is_human)
            if error:
                raise ValueError(error)

            now = time.time()
            record["state"] = target_state.value
            record["updated_at"] = now

            # Gate-specific timestamp bookkeeping
            if target_state == ApprovalState.APPROVED:
                record["review_ended_at"] = now
                record["reviewer"] = actor
            elif target_state == ApprovalState.REJECTED:
                record["review_ended_at"] = record.get("review_ended_at") or now
                record["reviewer"] = actor
            elif target_state == ApprovalState.TESTING:
                record["testing_started_at"] = now
            elif target_state == ApprovalState.DEPLOYED:
                record["deployed_at"] = now
                record["reviewer"] = actor  # must be a named human

            record["reason"] = reason

            # Append-only event — NEVER overwrite previous events
            record["events"].append({
                "event": f"TRANSITION_{current.value}_TO_{target_state.value}",
                "from_state": current.value,
                "to_state": target_state.value,
                "actor": actor,
                "is_human": is_human,
                "timestamp": now,
                "reason": reason,
            })

            cls._save(records)
            log_event(
                f"approval_workflow: {approval_id} "
                f"{current.value} → {target_state.value} "
                f"(actor={actor}, human={is_human})"
            )
            return record

    @classmethod
    def approve(
        cls,
        approval_id: str,
        reviewer: str,
        reason: str = "Human approved.",
    ) -> dict[str, Any]:
        """Human Gate H1: REVIEWING/ELEVATED_REVIEW → APPROVED."""
        return cls.transition(
            approval_id,
            ApprovalState.APPROVED,
            actor=reviewer,
            reason=reason,
            is_human=True,
        )

    @classmethod
    def reject(
        cls,
        approval_id: str,
        reviewer: str,
        reason: str = "Human rejected.",
    ) -> dict[str, Any]:
        """Human rejection from REVIEWING, ELEVATED_REVIEW, or TESTING."""
        return cls.transition(
            approval_id,
            ApprovalState.REJECTED,
            actor=reviewer,
            reason=reason,
            is_human=True,
        )

    @classmethod
    def advance_to_testing(
        cls,
        approval_id: str,
    ) -> dict[str, Any]:
        """System-side: APPROVED → TESTING (system action, no human needed)."""
        return cls.transition(
            approval_id,
            ApprovalState.TESTING,
            actor="system",
            reason="Sandbox passed. Advancing to TESTING.",
            is_human=False,
        )

    @classmethod
    def deploy(
        cls,
        approval_id: str,
        reviewer: str,
        reason: str = "Human authorized deployment.",
    ) -> dict[str, Any]:
        """Human Gate H2: TESTING → DEPLOYED.

        This is the ONLY authorized path to DEPLOYED.
        A named human reviewer identity is mandatory.
        """
        from backend.core.burn_in_governance import BurnInGovernance
        if BurnInGovernance.is_frozen():
            raise PermissionError("Governance Freeze: Deployment requests are disabled in Audit Mode.")

        if not reviewer or reviewer.strip().lower() in {"system", "auto", ""}:
            raise ValueError(
                "DEPLOYED requires an explicit human reviewer identity. "
                "System actors may never authorize deployment."
            )
        return cls.transition(
            approval_id,
            ApprovalState.DEPLOYED,
            actor=reviewer,
            reason=reason,
            is_human=True,
        )

    # -- Query ---------------------------------------------------------------

    @classmethod
    def get(cls, approval_id: str) -> dict[str, Any] | None:
        with cls._lock:
            return next(
                (r for r in cls._load() if r["approval_id"] == approval_id),
                None,
            )

    @classmethod
    def list_all(
        cls,
        state: str | None = None,
        change_type: str | None = None,
    ) -> list[dict[str, Any]]:
        with cls._lock:
            records = cls._load()
            if state:
                records = [r for r in records if r["state"] == state.upper()]
            if change_type:
                records = [r for r in records if r["change_type"] == change_type.upper()]
            return records

    @classmethod
    def get_events(cls, approval_id: str) -> list[dict[str, Any]]:
        """Return the full immutable event ledger for one approval."""
        record = cls.get(approval_id)
        if record is None:
            return []
        return record.get("events", [])

    # -- Metrics -------------------------------------------------------------

    @classmethod
    def metrics(cls) -> dict[str, Any]:
        """
        Compute burn-in metrics:
          AAR  Approval Acceptance Rate   = ever_approved / reviewed
          TTR  Time To Review             = mean(review_ended_at - review_started_at)
          DAR  Deployment Approval Rate   = deployed / ever_approved
          RAR  Rejection After Testing    = rejected_after_testing / ever_tested

        Note: "ever_approved" and "ever_tested" are derived from the event ledger
        because records advance past APPROVED -> TESTING -> DEPLOYED and their
        current state no longer reads APPROVED/TESTING.
        """
        with cls._lock:
            records = cls._load()

        def _states_visited(record: dict[str, Any]) -> set[str]:
            visited: set[str] = set()
            for ev in record.get("events", []):
                if ev.get("from_state"):
                    visited.add(ev["from_state"])
                if ev.get("to_state"):
                    visited.add(ev["to_state"])
            visited.add(record["state"])
            return visited

        reviewed = [
            r for r in records
            if r["state"] in {
                ApprovalState.APPROVED.value,
                ApprovalState.REJECTED.value,
                ApprovalState.TESTING.value,
                ApprovalState.DEPLOYED.value,
            }
            or any(
                e.get("to_state") in {
                    ApprovalState.APPROVED.value,
                    ApprovalState.REJECTED.value,
                }
                for e in r.get("events", [])
            )
        ]

        # Records that ever reached APPROVED (regardless of current state)
        ever_approved = [
            r for r in records
            if ApprovalState.APPROVED.value in _states_visited(r)
        ]

        # Records currently deployed (terminal, so current state is reliable)
        deployed = [r for r in records if r["state"] == ApprovalState.DEPLOYED.value]

        # Records that ever reached TESTING (regardless of current state)
        ever_tested = [
            r for r in records
            if ApprovalState.TESTING.value in _states_visited(r)
        ]

        # Rejected after reaching TESTING
        rejected_after_testing: list[dict[str, Any]] = []
        for r in records:
            if r["state"] == ApprovalState.REJECTED.value:
                if ApprovalState.TESTING.value in _states_visited(r):
                    rejected_after_testing.append(r)

        # TTR calculation
        ttr_values: list[float] = []
        for r in records:
            start = r.get("review_started_at")
            end   = r.get("review_ended_at")
            if start and end and end > start:
                ttr_values.append(end - start)
        ttr_mean = sum(ttr_values) / len(ttr_values) if ttr_values else None

        return {
            "total":                  len(records),
            "reviewed":               len(reviewed),
            "ever_approved":          len(ever_approved),
            "deployed":               len(deployed),
            "ever_tested":            len(ever_tested),
            "rejected_after_testing": len(rejected_after_testing),
            "AAR": round(len(ever_approved) / len(reviewed), 4) if reviewed else None,
            "TTR_seconds_mean": round(ttr_mean, 2) if ttr_mean is not None else None,
            "DAR": round(len(deployed) / len(ever_approved), 4) if ever_approved else None,
            "RAR": round(len(rejected_after_testing) / len(ever_tested), 4) if ever_tested else None,
        }
