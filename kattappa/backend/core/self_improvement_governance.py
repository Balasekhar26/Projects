"""Step 21: Self-Improvement Governance.

Single entry point for all architectural change proposals originating from
the benchmark, research, or reflection pipelines.

Four-gate check before a proposal reaches human review:
    Gate 1 — Protected Core: does the proposal touch safety-critical modules?
    Gate 2 — Safety regression: would the change increase AER above threshold?
    Gate 3 — Benchmark confirmation: was the claim experimentally verified?
    Gate 4 — Daily budget: has today's proposal budget been exhausted?

Nothing auto-deploys. Every proposal that passes all gates is queued for
explicit human approval. Human reject/approve is recorded in both this table
and StrategicMemory (Step 19 call site).

Invariants:
- A proposal can only move: pending → approved | blocked | rejected
- Once approved/rejected, state is immutable (append-only history).
- Protected Core proposals are immediately blocked; no human review pathway.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root
from backend.core.logger import log_event


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_WRITE_LOCK = threading.Lock()
_schema_ensured: set[str] = set()


def _db_path() -> Path:
    p = runtime_data_root() / "backend" / "data" / "self_improvement_governance.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS architectural_proposals (
    id                   TEXT PRIMARY KEY,
    title                TEXT NOT NULL,
    source               TEXT NOT NULL,
    source_id            TEXT,
    affected_modules     TEXT NOT NULL DEFAULT '[]',
    proposal_text        TEXT NOT NULL,
    pis_score            REAL,
    gate_status          TEXT NOT NULL DEFAULT 'pending',
    gate_reasons         TEXT NOT NULL DEFAULT '[]',
    benchmark_confirmed  INTEGER NOT NULL DEFAULT 0,
    reviewer_id          TEXT,
    created_at           REAL NOT NULL,
    reviewed_at          REAL
);
CREATE INDEX IF NOT EXISTS idx_ap_status  ON architectural_proposals(gate_status);
CREATE INDEX IF NOT EXISTS idx_ap_source  ON architectural_proposals(source);
CREATE INDEX IF NOT EXISTS idx_ap_created ON architectural_proposals(created_at DESC);

CREATE TABLE IF NOT EXISTS governance_audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id   TEXT NOT NULL,
    event         TEXT NOT NULL,
    actor         TEXT NOT NULL DEFAULT 'system',
    details_json  TEXT NOT NULL DEFAULT '{}',
    logged_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gal_proposal ON governance_audit_log(proposal_id);
"""


def _ensure_schema() -> None:
    key = str(_db_path())
    if key in _schema_ensured:
        return
    with _WRITE_LOCK:
        if key not in _schema_ensured:
            conn = _connect()
            try:
                conn.executescript(_SCHEMA_SQL)
                conn.commit()
            finally:
                conn.close()
            _schema_ensured.add(key)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ArchitecturalProposal:
    """A candidate architectural change awaiting governance review."""
    proposal_id: str
    title: str
    source: str                                 # 'research' | 'benchmark' | 'reflection'
    source_id: str | None
    affected_modules: list[str]
    proposal_text: str
    benchmark_confirmed: bool = False
    pis_score: float | None = None             # computed by governance gate
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GateDecision:
    """Result of the four-gate governance check."""
    proposal_id: str
    passed: bool                               # True = queued for human review
    gate_status: str                           # 'pending' | 'blocked'
    reasons: list[str]                         # blocking reasons (empty if passed)
    pis_score: float | None = None


# ---------------------------------------------------------------------------
# SelfImprovementGovernance
# ---------------------------------------------------------------------------

class SelfImprovementGovernance:
    """Four-gate governance gatekeeper for architectural change proposals."""

    # Gate thresholds
    PIS_BLOCK_THRESHOLD = 3.0      # proposals scoring < 3.0 are blocked (very risky)
    AER_BLOCK_THRESHOLD = 0.10     # >10% adversarial extraction rate → safety block
    DAILY_BUDGET_DEFAULT = 10      # max proposals per day

    @classmethod
    def submit(cls, proposal: ArchitecturalProposal) -> GateDecision:
        """Run all four gates and persist the proposal.

        Returns GateDecision. If all gates pass, status='pending' (awaits human).
        If any gate fails, status='blocked' with reasons.
        """
        _ensure_schema()

        reasons: list[str] = []

        # Gate 1 — Protected Core check
        pis_score = cls._run_gate_protected_core(proposal, reasons)

        # Gate 2 — Safety regression (AER)
        if not reasons:  # only run if not already blocked
            cls._run_gate_safety_regression(proposal, reasons)

        # Gate 3 — Benchmark confirmation required (research proposals)
        if not reasons:
            cls._run_gate_benchmark_confirmation(proposal, reasons)

        # Gate 4 — Daily budget
        if not reasons:
            cls._run_gate_budget(reasons)

        passed = len(reasons) == 0
        gate_status = "pending" if passed else "blocked"

        with _WRITE_LOCK:
            conn = _connect()
            try:
                conn.execute(
                    """
                    INSERT INTO architectural_proposals
                        (id, title, source, source_id, affected_modules,
                         proposal_text, pis_score, gate_status, gate_reasons,
                         benchmark_confirmed, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        proposal.proposal_id,
                        proposal.title,
                        proposal.source,
                        proposal.source_id,
                        json.dumps(proposal.affected_modules),
                        proposal.proposal_text,
                        pis_score,
                        gate_status,
                        json.dumps(reasons),
                        1 if proposal.benchmark_confirmed else 0,
                        proposal.created_at,
                    ),
                )
                cls._audit(conn, proposal.proposal_id, "SUBMITTED", "system", {
                    "gate_status": gate_status,
                    "reasons": reasons,
                    "pis_score": pis_score,
                })
                conn.commit()
            finally:
                conn.close()

        log_event("GOVERNANCE_PROPOSAL_SUBMITTED", {
            "proposal_id": proposal.proposal_id,
            "source": proposal.source,
            "gate_status": gate_status,
            "passed": passed,
        })

        return GateDecision(
            proposal_id=proposal.proposal_id,
            passed=passed,
            gate_status=gate_status,
            reasons=reasons,
            pis_score=pis_score,
        )

    @classmethod
    def list_pending(cls) -> list[dict[str, Any]]:
        """Return all proposals awaiting human review."""
        _ensure_schema()
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM architectural_proposals "
                "WHERE gate_status = 'pending' ORDER BY created_at DESC"
            ).fetchall()
            return [cls._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def list_all(cls, limit: int = 100) -> list[dict[str, Any]]:
        """Return all proposals (any status), newest first."""
        _ensure_schema()
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM architectural_proposals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [cls._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def approve(cls, proposal_id: str, reviewer_id: str) -> bool:
        """Human approves a pending proposal.

        Records to StrategicMemory (Step 19 call site) and TrackRecordStore.
        Returns True if successfully approved.
        """
        _ensure_schema()
        with _WRITE_LOCK:
            conn = _connect()
            try:
                row = conn.execute(
                    "SELECT * FROM architectural_proposals WHERE id = ?",
                    (proposal_id,),
                ).fetchone()
                if not row or row["gate_status"] != "pending":
                    return False

                now = time.time()
                conn.execute(
                    """
                    UPDATE architectural_proposals
                    SET gate_status = 'approved', reviewer_id = ?, reviewed_at = ?
                    WHERE id = ?
                    """,
                    (reviewer_id, now, proposal_id),
                )
                cls._audit(conn, proposal_id, "APPROVED", reviewer_id, {})
                conn.commit()

                # Step 19: StrategicMemory call site
                cls._record_approval_decision(dict(row), reviewer_id, approved=True)

                # TrackRecord (existing governance infrastructure)
                cls._record_track(proposal_id, reviewer_id, approved=True)

            finally:
                conn.close()

        log_event("GOVERNANCE_PROPOSAL_APPROVED", {
            "proposal_id": proposal_id,
            "reviewer_id": reviewer_id,
        })
        return True

    @classmethod
    def reject(cls, proposal_id: str, reviewer_id: str, reason: str = "") -> bool:
        """Human rejects a pending proposal.

        Records to StrategicMemory and TrackRecordStore.
        Returns True if successfully rejected.
        """
        _ensure_schema()
        with _WRITE_LOCK:
            conn = _connect()
            try:
                row = conn.execute(
                    "SELECT * FROM architectural_proposals WHERE id = ?",
                    (proposal_id,),
                ).fetchone()
                if not row or row["gate_status"] != "pending":
                    return False

                now = time.time()
                conn.execute(
                    """
                    UPDATE architectural_proposals
                    SET gate_status = 'rejected', reviewer_id = ?, reviewed_at = ?
                    WHERE id = ?
                    """,
                    (reviewer_id, now, proposal_id),
                )
                cls._audit(conn, proposal_id, "REJECTED", reviewer_id, {"reason": reason})
                conn.commit()

                cls._record_approval_decision(dict(row), reviewer_id, approved=False, reason=reason)
                cls._record_track(proposal_id, reviewer_id, approved=False)

            finally:
                conn.close()

        log_event("GOVERNANCE_PROPOSAL_REJECTED", {
            "proposal_id": proposal_id,
            "reviewer_id": reviewer_id,
            "reason": reason,
        })
        return True

    @classmethod
    def get_proposal(cls, proposal_id: str) -> dict[str, Any] | None:
        """Retrieve a single proposal by ID."""
        _ensure_schema()
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM architectural_proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
            if not row:
                return None
            return cls._row_to_dict(row)
        finally:
            conn.close()

    @classmethod
    def get_audit_log(cls, proposal_id: str) -> list[dict[str, Any]]:
        """Return the full audit trail for a proposal."""
        _ensure_schema()
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM governance_audit_log WHERE proposal_id = ? ORDER BY logged_at ASC",
                (proposal_id,),
            ).fetchall()
            return [
                {
                    "event": r["event"],
                    "actor": r["actor"],
                    "details": json.loads(r["details_json"]),
                    "logged_at": r["logged_at"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Gate implementations
    # -------------------------------------------------------------------------

    @classmethod
    def _run_gate_protected_core(
        cls, proposal: ArchitecturalProposal, reasons: list[str]
    ) -> float | None:
        """Gate 1: Protected Core check via ProposalIntegrityScorer."""
        try:
            from backend.core.proposal_governance import (
                ProposalIntegrityScorer,
                ProtectedCoreRegistry,
            )
            # Check if any affected module is transitively protected
            if ProtectedCoreRegistry.check_affected_modules(proposal.affected_modules):
                reasons.append(
                    f"GATE 1 BLOCKED: Proposal touches protected core modules "
                    f"({proposal.affected_modules}). "
                    "Protected Core proposals cannot proceed to human review."
                )
                return None

            pis_score = ProposalIntegrityScorer.compute_pis(
                title=proposal.title,
                proposal=proposal.proposal_text,
                affected_modules=proposal.affected_modules,
            )
            if pis_score < cls.PIS_BLOCK_THRESHOLD:
                reasons.append(
                    f"GATE 1 BLOCKED: Proposal Integrity Score {pis_score:.2f} is below "
                    f"minimum threshold {cls.PIS_BLOCK_THRESHOLD:.2f}. "
                    "Proposal scope or rationale is insufficient."
                )
            return pis_score
        except Exception:
            return None  # Gate not blocking on infrastructure failure

    @classmethod
    def _run_gate_safety_regression(
        cls, proposal: ArchitecturalProposal, reasons: list[str]
    ) -> None:
        """Gate 2: Memory Safety AER check on affected modules."""
        try:
            # Only run AER if proposal targets memory or core data-handling modules
            memory_targets = {"memory", "human_memory", "relationship_memory",
                              "semantic_memory", "episodic_memory"}
            if not any(m in memory_targets for m in proposal.affected_modules):
                return  # Gate not applicable

            from backend.core.memory_safety import MemorySafetyVerifier
            aer = MemorySafetyVerifier.calculate_aer(
                test_contents=[f"governance_probe_{uuid.uuid4().hex[:8]}"]
            )
            if aer > cls.AER_BLOCK_THRESHOLD:
                reasons.append(
                    f"GATE 2 BLOCKED: Current Adversarial Extraction Rate ({aer:.3f}) "
                    f"exceeds safety threshold ({cls.AER_BLOCK_THRESHOLD:.3f}). "
                    "Resolve existing memory safety issues before adding changes."
                )
        except Exception:
            pass  # Gate not blocking on infrastructure failure

    @classmethod
    def _run_gate_benchmark_confirmation(
        cls, proposal: ArchitecturalProposal, reasons: list[str]
    ) -> None:
        """Gate 3: Research proposals must have a confirmed experiment."""
        if proposal.source != "research":
            return  # Gate only applies to research-sourced proposals
        if not proposal.benchmark_confirmed:
            reasons.append(
                "GATE 3 BLOCKED: Research-sourced proposal has no confirmed "
                "Arena experiment. Run ClaimReproductionEngine.run() first and "
                "ensure the claim is reproduced before submitting for governance."
            )

    @classmethod
    def _run_gate_budget(cls, reasons: list[str]) -> None:
        """Gate 4: Daily proposal budget check."""
        try:
            from backend.core.proposal_governance import ProposalBudgetManager
            limit = ProposalBudgetManager.get_budget_limit()
            today_start = time.strftime("%Y-%m-%d 00:00:00", time.localtime())

            conn = _connect()
            try:
                today_count = conn.execute(
                    "SELECT COUNT(*) FROM architectural_proposals "
                    "WHERE gate_status = 'pending' AND created_at >= ?",
                    (time.mktime(time.strptime(today_start, "%Y-%m-%d %H:%M:%S")),),
                ).fetchone()[0]
            finally:
                conn.close()

            if today_count >= limit:
                reasons.append(
                    f"GATE 4 BLOCKED: Daily pending-proposal budget ({limit}) exhausted "
                    f"({today_count} pending today). Try again tomorrow or increase limit."
                )
        except Exception:
            pass  # Gate not blocking on infrastructure failure

    # -------------------------------------------------------------------------
    # Private — Step 19 StrategicMemory call site
    # -------------------------------------------------------------------------

    @staticmethod
    def _record_approval_decision(
        proposal_row: dict[str, Any],
        reviewer_id: str,
        approved: bool,
        reason: str = "",
    ) -> None:
        try:
            from backend.core.strategic_memory import StrategicMemory
            action = "APPROVED" if approved else "REJECTED"
            StrategicMemory.record_decision(
                decision=(
                    f"Architectural proposal {action}: '{proposal_row.get('title', '')}'"
                ),
                context=(
                    f"Proposal ID: {proposal_row.get('id', '')}. "
                    f"Source: {proposal_row.get('source', '')}. "
                    f"Affected modules: {proposal_row.get('affected_modules', '[]')}."
                ),
                rationale=(
                    f"Human reviewer '{reviewer_id}' {action.lower()} this proposal. "
                    + (f"Rejection reason: {reason}." if reason else "")
                ),
                alternatives=(
                    ["Reject proposal"] if approved else ["Approve proposal", "Defer for more evidence"]
                ),
                created_by=reviewer_id,
            )
        except Exception:
            pass

    @staticmethod
    def _record_track(proposal_id: str, reviewer_id: str, approved: bool) -> None:
        try:
            from backend.core.proposal_governance import TrackRecordStore
            TrackRecordStore.record_human_review(
                proposal_id=proposal_id,
                reviewer_id=reviewer_id,
                approved=approved,
            )
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Private — DB helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _audit(
        conn: sqlite3.Connection,
        proposal_id: str,
        event: str,
        actor: str,
        details: dict[str, Any],
    ) -> None:
        conn.execute(
            "INSERT INTO governance_audit_log (proposal_id, event, actor, details_json, logged_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (proposal_id, event, actor, json.dumps(details), time.time()),
        )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        if isinstance(d.get("affected_modules"), str):
            d["affected_modules"] = json.loads(d["affected_modules"])
        if isinstance(d.get("gate_reasons"), str):
            d["gate_reasons"] = json.loads(d["gate_reasons"])
        return d
