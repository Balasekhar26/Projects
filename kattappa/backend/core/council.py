"""Step 20 deterministic Personality Council.

This module implements the hardened council design:

* facts are verified by evidence validators, not voted on;
* structural risks become hard vetoes that cannot be outweighed;
* validated, non-vetoed value tradeoffs are ranked deterministically;
* no LLM arbiter, no automatic task-text mode selection, and no auto-apply.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root
from backend.core.value_engine import PlanSignals, ValueEngine, ValueProfile


def _now() -> float:
    return time.time()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _json(data: Any) -> str:
    return json.dumps(data, sort_keys=True)


def _loads(raw: str | None, fallback: Any = None) -> Any:
    if raw in (None, ""):
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _db_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "personality_council.db"


class LensName(str, Enum):
    RAMA = "RAMA"
    KRISHNA = "KRISHNA"
    SHIVA = "SHIVA"
    BRAHMA = "BRAHMA"
    HANUMAN = "HANUMAN"
    KATTAPPA = "KATTAPPA"


class ModeProfile(str, Enum):
    SYSTEM_DEFAULT = "SYSTEM_DEFAULT"
    ENGINEERING_STANDARD = "ENGINEERING_STANDARD"
    HIGH_RISK_CRITICAL_FIX = "HIGH_RISK_CRITICAL_FIX"
    INNOVATION = "INNOVATION"


class ModeSetBy(str, Enum):
    SYSTEM = "SYSTEM"
    HUMAN = "HUMAN"


class ProposalType(str, Enum):
    FACTUAL_CLAIM = "FACTUAL_CLAIM"
    RISK_FINDING = "RISK_FINDING"
    VALUE_TRADEOFF = "VALUE_TRADEOFF"


class ResolutionPath(str, Enum):
    VALUE_RANKED = "VALUE_RANKED"
    VETOED = "VETOED"
    ESCALATED_TO_HUMAN = "ESCALATED_TO_HUMAN"


MODE_WEIGHTS: dict[str, dict[str, float]] = {
    ModeProfile.SYSTEM_DEFAULT.value: {
        LensName.RAMA.value: 0.25,
        LensName.KRISHNA.value: 0.05,
        LensName.SHIVA.value: 0.05,
        LensName.BRAHMA.value: 0.25,
        LensName.HANUMAN.value: 0.10,
        LensName.KATTAPPA.value: 0.30,
    },
    ModeProfile.ENGINEERING_STANDARD.value: {
        LensName.RAMA.value: 0.20,
        LensName.KRISHNA.value: 0.15,
        LensName.SHIVA.value: 0.15,
        LensName.BRAHMA.value: 0.20,
        LensName.HANUMAN.value: 0.15,
        LensName.KATTAPPA.value: 0.15,
    },
    ModeProfile.HIGH_RISK_CRITICAL_FIX.value: {
        LensName.RAMA.value: 0.40,
        LensName.KRISHNA.value: 0.10,
        LensName.SHIVA.value: 0.30,
        LensName.BRAHMA.value: 0.00,
        LensName.HANUMAN.value: 0.20,
        LensName.KATTAPPA.value: 0.00,
    },
    ModeProfile.INNOVATION.value: {
        LensName.RAMA.value: 0.10,
        LensName.KRISHNA.value: 0.15,
        LensName.SHIVA.value: 0.05,
        LensName.BRAHMA.value: 0.40,
        LensName.HANUMAN.value: 0.10,
        LensName.KATTAPPA.value: 0.20,
    },
}

VALUE_PROFILE_BY_MODE: dict[str, ValueProfile] = {
    ModeProfile.SYSTEM_DEFAULT.value: ValueProfile.DEFAULT,
    ModeProfile.ENGINEERING_STANDARD.value: ValueProfile.PRODUCTION,
    ModeProfile.HIGH_RISK_CRITICAL_FIX.value: ValueProfile.INCIDENT,
    ModeProfile.INNOVATION.value: ValueProfile.GREENFIELD,
}


@dataclass(frozen=True)
class ModeDecision:
    requested_mode: str
    requested_set_by: str
    active_mode: str
    trusted: bool
    reason: str


@dataclass
class CouncilProposal:
    session_id: str
    agent_name: str
    proposal_text: str
    proposal_type: str = ProposalType.VALUE_TRADEOFF.value
    raw_confidence: float = 0.6
    evidence_episode_ids: list[str] = field(default_factory=list)
    evidence_semantic_ids: list[str] = field(default_factory=list)
    evidence_relation_ids: list[str] = field(default_factory=list)
    evidence_world_ids: list[str] = field(default_factory=list)
    risk_flag: bool = False
    option_id: str | None = None
    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=_now)

    @property
    def all_evidence_ids(self) -> list[str]:
        return [
            *self.evidence_episode_ids,
            *self.evidence_semantic_ids,
            *self.evidence_relation_ids,
            *self.evidence_world_ids,
        ]

    @classmethod
    def from_dict(
        cls,
        session_id: str,
        data: dict[str, Any],
        fallback_evidence: dict[str, list[str]],
    ) -> "CouncilProposal":
        agent = str(data.get("agent_name") or data.get("lens") or data.get("agent") or "").upper()
        if agent not in {lens.value for lens in LensName}:
            agent = LensName.KATTAPPA.value
        proposal_type = str(data.get("proposal_type") or data.get("type") or ProposalType.VALUE_TRADEOFF.value).upper()
        if proposal_type not in {item.value for item in ProposalType}:
            proposal_type = ProposalType.VALUE_TRADEOFF.value
        return cls(
            session_id=session_id,
            agent_name=agent,
            proposal_text=str(data.get("proposal_text") or data.get("text") or data.get("claim") or ""),
            proposal_type=proposal_type,
            raw_confidence=_clamp(float(data.get("raw_confidence", data.get("confidence", 0.6)))),
            evidence_episode_ids=list(data.get("evidence_episode_ids", fallback_evidence["episode"])),
            evidence_semantic_ids=list(data.get("evidence_semantic_ids", fallback_evidence["semantic"])),
            evidence_relation_ids=list(data.get("evidence_relation_ids", fallback_evidence["relation"])),
            evidence_world_ids=list(data.get("evidence_world_ids", fallback_evidence["world"])),
            risk_flag=bool(data.get("risk_flag", proposal_type == ProposalType.RISK_FINDING.value)),
            option_id=str(data.get("option_id") or "") or None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "proposal_type": self.proposal_type,
            "proposal_text": self.proposal_text,
            "raw_confidence": self.raw_confidence,
            "evidence_episode_ids": self.evidence_episode_ids,
            "evidence_semantic_ids": self.evidence_semantic_ids,
            "evidence_relation_ids": self.evidence_relation_ids,
            "evidence_world_ids": self.evidence_world_ids,
            "risk_flag": self.risk_flag,
            "option_id": self.option_id,
            "created_at": self.created_at,
        }


class PersonalityCouncilStore:
    """SQLite persistence for Step 20 council sessions."""

    _lock = threading.Lock()
    _schema_ensured = False

    @classmethod
    def connect(cls) -> sqlite3.Connection:
        path = _db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def ensure_schema(cls) -> None:
        if cls._schema_ensured:
            return
        with cls._lock:
            if cls._schema_ensured:
                return
            with cls.connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS council_sessions (
                        session_id TEXT PRIMARY KEY,
                        question TEXT NOT NULL,
                        requested_mode_profile TEXT NOT NULL,
                        active_mode_profile TEXT NOT NULL,
                        mode_set_by TEXT NOT NULL,
                        context_json TEXT NOT NULL,
                        mode_weights_json TEXT NOT NULL,
                        consensus_strength REAL NOT NULL,
                        final_decision TEXT NOT NULL,
                        resolution_path TEXT NOT NULL,
                        human_approval_required INTEGER NOT NULL,
                        auto_applied INTEGER NOT NULL,
                        arbiter_findings_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS council_proposals (
                        proposal_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        agent_name TEXT NOT NULL,
                        proposal_type TEXT NOT NULL,
                        proposal_text TEXT NOT NULL,
                        raw_confidence REAL NOT NULL,
                        calibrated_confidence REAL NOT NULL,
                        evidence_refs_json TEXT NOT NULL,
                        risk_flag INTEGER NOT NULL,
                        option_id TEXT,
                        created_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS council_validations (
                        validation_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        proposal_id TEXT NOT NULL,
                        claim_text TEXT NOT NULL,
                        is_verified INTEGER NOT NULL,
                        verified_evidence_ids_json TEXT NOT NULL,
                        fabricated_evidence_ids_json TEXT NOT NULL,
                        verified_density REAL NOT NULL,
                        validator_module TEXT NOT NULL,
                        validated_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS council_vetoes (
                        veto_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        proposal_id TEXT NOT NULL,
                        veto_source TEXT NOT NULL,
                        veto_reason TEXT NOT NULL,
                        structural_evidence_json TEXT NOT NULL,
                        overridden_by_human INTEGER NOT NULL DEFAULT 0,
                        override_justification TEXT NOT NULL DEFAULT '',
                        created_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS council_rankings (
                        ranking_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        proposal_id TEXT NOT NULL,
                        option_text TEXT NOT NULL,
                        rank_index INTEGER NOT NULL,
                        score REAL NOT NULL,
                        value_engine_score REAL NOT NULL,
                        mode_weight REAL NOT NULL,
                        calibrated_confidence REAL NOT NULL,
                        evidence_density REAL NOT NULL,
                        lens_scores_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS council_outcomes (
                        outcome_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        predicted_success REAL,
                        actual_success REAL,
                        final_decision TEXT NOT NULL,
                        supporting_agents_json TEXT NOT NULL,
                        opposing_agents_json TEXT NOT NULL,
                        source_episode_id TEXT,
                        notes TEXT NOT NULL DEFAULT '',
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS council_dissent_archive (
                        dissent_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        proposal_id TEXT NOT NULL,
                        agent_name TEXT NOT NULL,
                        dissent_text TEXT NOT NULL,
                        rationale TEXT NOT NULL,
                        risks_json TEXT NOT NULL,
                        evidence_type TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        evidence_refs_json TEXT NOT NULL,
                        archived_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS agent_accuracy_history (
                        history_id TEXT PRIMARY KEY,
                        agent_name TEXT NOT NULL,
                        session_id TEXT,
                        proposal_id TEXT,
                        outcome_id TEXT,
                        predicted_success REAL,
                        actual_success REAL,
                        prediction_correct INTEGER,
                        created_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS council_outcome_validation (
                        validation_id TEXT PRIMARY KEY,
                        outcome_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        predicted_success REAL,
                        actual_success REAL,
                        source_episode_id TEXT,
                        notes TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    """
                )
            cls._schema_ensured = True


class ModeProfileEnforcer:
    """Accept only human-set known profiles; everything else falls back safely."""

    _schema_ensured = False

    @classmethod
    def resolve(cls, mode_profile: str | None, mode_set_by: str | None = ModeSetBy.SYSTEM.value) -> ModeDecision:
        requested_mode = str(mode_profile or ModeProfile.SYSTEM_DEFAULT.value).strip().upper()
        requested_set_by = str(mode_set_by or ModeSetBy.SYSTEM.value).strip().upper()
        if requested_mode not in MODE_WEIGHTS:
            return ModeDecision(
                requested_mode=requested_mode,
                requested_set_by=requested_set_by,
                active_mode=ModeProfile.SYSTEM_DEFAULT.value,
                trusted=False,
                reason="unknown_mode_defaulted_to_system_default",
            )
        if requested_set_by != ModeSetBy.HUMAN.value:
            if requested_mode == ModeProfile.SYSTEM_DEFAULT.value:
                reason = "system_default"
            else:
                reason = "untrusted_mode_change_rejected"
            return ModeDecision(
                requested_mode=requested_mode,
                requested_set_by=requested_set_by,
                active_mode=ModeProfile.SYSTEM_DEFAULT.value,
                trusted=requested_mode == ModeProfile.SYSTEM_DEFAULT.value,
                reason=reason,
            )
        return ModeDecision(
            requested_mode=requested_mode,
            requested_set_by=requested_set_by,
            active_mode=requested_mode,
            trusted=True,
            reason="human_set_mode_accepted",
        )


class CouncilCalibration:
    """Historical confidence calibration: C'(A) = C_raw * historical accuracy."""

    _schema_ensured = False
    min_records = 10
    cold_start_factor = 0.5

    @classmethod
    def calibration_factor(cls, agent_name: str) -> float:
        PersonalityCouncilStore.ensure_schema()
        with PersonalityCouncilStore.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS judged,
                    COALESCE(SUM(CASE WHEN prediction_correct = 1 THEN 1 ELSE 0 END), 0) AS correct
                FROM agent_accuracy_history
                WHERE agent_name = ? AND prediction_correct IS NOT NULL
                """,
                (agent_name,),
            ).fetchone()
        judged = int(row["judged"] or 0)
        if judged < cls.min_records:
            return cls.cold_start_factor
        return _clamp(float(row["correct"] or 0) / float(judged))

    @classmethod
    def calibrated_confidence(cls, agent_name: str, raw_confidence: float) -> float:
        return round(_clamp(raw_confidence) * cls.calibration_factor(agent_name), 4)

    @classmethod
    def snapshot(cls, agents: list[str] | None = None) -> dict[str, dict[str, float | int]]:
        PersonalityCouncilStore.ensure_schema()
        agents = agents or [lens.value for lens in LensName]
        out: dict[str, dict[str, float | int]] = {}
        with PersonalityCouncilStore.connect() as conn:
            for agent in agents:
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS judged,
                        COALESCE(SUM(CASE WHEN prediction_correct = 1 THEN 1 ELSE 0 END), 0) AS correct
                    FROM agent_accuracy_history
                    WHERE agent_name = ? AND prediction_correct IS NOT NULL
                    """,
                    (agent,),
                ).fetchone()
                judged = int(row["judged"] or 0)
                correct = int(row["correct"] or 0)
                factor = cls.cold_start_factor if judged < cls.min_records else _clamp(correct / judged)
                out[agent] = {"judged": judged, "correct": correct, "calibration_factor": round(factor, 4)}
        return out


class CouncilEvidenceVerifier:
    """Verifies proposal evidence against supplied memory-layer references."""

    _schema_ensured = False

    @classmethod
    def _accepted_ids(cls, context: dict[str, Any]) -> set[str]:
        accepted: set[str] = set()
        for key in (
            "verified_evidence_ids",
            "evidence_ids",
            "evidence_episode_ids",
            "evidence_semantic_ids",
            "evidence_relation_ids",
            "evidence_world_ids",
        ):
            value = context.get(key, [])
            if isinstance(value, str):
                accepted.add(value)
            elif isinstance(value, list):
                accepted.update(str(item) for item in value)

        available = context.get("available_evidence", {})
        if isinstance(available, dict):
            for value in available.values():
                if isinstance(value, str):
                    accepted.add(value)
                elif isinstance(value, list):
                    accepted.update(str(item) for item in value)
                elif isinstance(value, dict):
                    accepted.update(str(item) for item in value.keys())
        return {item for item in accepted if item}

    @classmethod
    def verify(cls, proposal: CouncilProposal, context: dict[str, Any]) -> dict[str, Any]:
        claimed = proposal.all_evidence_ids
        accepted = cls._accepted_ids(context)
        verified = [item for item in claimed if item in accepted]
        fabricated = [item for item in claimed if item not in accepted]
        density = 0.0 if not claimed else len(verified) / len(claimed)
        return {
            "validation_id": str(uuid.uuid4()),
            "session_id": proposal.session_id,
            "proposal_id": proposal.proposal_id,
            "claim_text": proposal.proposal_text,
            "is_verified": bool(claimed and len(fabricated) == 0),
            "verified_evidence_ids": verified,
            "fabricated_evidence_ids": fabricated,
            "verified_density": round(density, 4),
            "validator_module": cls.__name__,
            "validated_at": _now(),
        }


class CouncilRiskVetoLayer:
    """Turns verified structural risk findings into hard vetoes."""

    _schema_ensured = False

    @classmethod
    def evaluate(cls, proposal: CouncilProposal, validation: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
        structural_risk = bool(proposal.risk_flag or proposal.proposal_type == ProposalType.RISK_FINDING.value)
        if not structural_risk:
            return None
        if not validation.get("is_verified"):
            return None
        return {
            "veto_id": str(uuid.uuid4()),
            "session_id": proposal.session_id,
            "proposal_id": proposal.proposal_id,
            "veto_source": proposal.agent_name,
            "veto_reason": proposal.proposal_text or "verified_structural_risk",
            "structural_evidence": {
                "verified_evidence_ids": validation.get("verified_evidence_ids", []),
                "context_risk_markers": context.get("risk_markers", []),
            },
            "overridden_by_human": False,
            "override_justification": "",
            "created_at": _now(),
        }


class CouncilArbiter:
    """Rule-only process checks. It never re-judges content and never calls a model."""

    _schema_ensured = False

    @classmethod
    def evaluate(
        cls,
        *,
        proposals: list[CouncilProposal],
        validations: list[dict[str, Any]],
        vetoes: list[dict[str, Any]],
        ranked_options: list[dict[str, Any]],
        consensus_strength: float,
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        by_proposal = {item["proposal_id"]: item for item in validations}

        for proposal in proposals:
            validation = by_proposal.get(proposal.proposal_id, {})
            if proposal.all_evidence_ids and validation.get("fabricated_evidence_ids"):
                findings.append({
                    "rule": "unverified_evidence",
                    "severity": "blocking",
                    "proposal_id": proposal.proposal_id,
                    "message": "proposal cited evidence not present in supplied memory refs",
                })
            if not proposal.all_evidence_ids:
                findings.append({
                    "rule": "missing_traceability",
                    "severity": "advisory",
                    "proposal_id": proposal.proposal_id,
                    "message": "proposal did not cite evidence refs",
                })

        vetoed_ids = {item["proposal_id"] for item in vetoes}
        for ranked in ranked_options:
            if ranked["proposal_id"] in vetoed_ids:
                findings.append({
                    "rule": "bypassed_veto",
                    "severity": "blocking",
                    "proposal_id": ranked["proposal_id"],
                    "message": "vetoed proposal appeared in value ranking",
                })

        if consensus_strength < 0.60:
            findings.append({
                "rule": "deadlock",
                "severity": "blocking",
                "message": "no validated value option reached the 60% resolution threshold",
            })

        agent_counts: dict[str, int] = {}
        for proposal in proposals:
            agent_counts[proposal.agent_name] = agent_counts.get(proposal.agent_name, 0) + 1
        stacked = [agent for agent, count in agent_counts.items() if count > 1]
        if stacked:
            findings.append({
                "rule": "vote_stacking",
                "severity": "blocking",
                "agents": stacked,
                "message": "one or more lenses supplied multiple proposals in the same session",
            })

        risk_agents = {proposal.agent_name for proposal in proposals if proposal.risk_flag}
        if len(risk_agents) > 1 and len(vetoes) == len(risk_agents):
            findings.append({
                "rule": "correlated_blocks",
                "severity": "advisory",
                "agents": sorted(risk_agents),
                "message": "multiple lenses independently produced verified risk blocks",
            })

        return findings


class PersonalityCouncil:
    """Entry point for the Step 20 deterministic council layer."""

    _schema_ensured = False

    @classmethod
    def _ensure_schema(cls) -> None:
        PersonalityCouncilStore.ensure_schema()

    @classmethod
    def _fallback_evidence(
        cls,
        evidence_episode_ids: list[str] | None,
        evidence_semantic_ids: list[str] | None,
        evidence_relation_ids: list[str] | None,
        evidence_world_ids: list[str] | None,
    ) -> dict[str, list[str]]:
        return {
            "episode": list(evidence_episode_ids or []),
            "semantic": list(evidence_semantic_ids or []),
            "relation": list(evidence_relation_ids or []),
            "world": list(evidence_world_ids or []),
        }

    @classmethod
    def _context_with_evidence(
        cls,
        context: dict[str, Any] | None,
        fallback_evidence: dict[str, list[str]],
    ) -> dict[str, Any]:
        merged = dict(context or {})
        merged.setdefault("evidence_episode_ids", fallback_evidence["episode"])
        merged.setdefault("evidence_semantic_ids", fallback_evidence["semantic"])
        merged.setdefault("evidence_relation_ids", fallback_evidence["relation"])
        merged.setdefault("evidence_world_ids", fallback_evidence["world"])
        return merged

    @classmethod
    def _make_default_proposals(
        cls,
        session_id: str,
        question: str,
        fallback_evidence: dict[str, list[str]],
    ) -> list[CouncilProposal]:
        all_evidence = [
            *fallback_evidence["episode"],
            *fallback_evidence["semantic"],
            *fallback_evidence["relation"],
            *fallback_evidence["world"],
        ]
        primary_semantic = fallback_evidence["semantic"] or all_evidence
        primary_episode = fallback_evidence["episode"] or all_evidence
        primary_world = fallback_evidence["world"] or all_evidence
        primary_relation = fallback_evidence["relation"] or all_evidence
        return [
            CouncilProposal(
                session_id=session_id,
                agent_name=LensName.RAMA.value,
                proposal_type=ProposalType.FACTUAL_CLAIM.value,
                proposal_text=f"Validate the factual basis before deciding: {question}",
                raw_confidence=0.6,
                evidence_semantic_ids=list(primary_semantic[:1]),
            ),
            CouncilProposal(
                session_id=session_id,
                agent_name=LensName.KRISHNA.value,
                proposal_type=ProposalType.VALUE_TRADEOFF.value,
                proposal_text=f"Prefer the option that preserves reversible strategic moves for: {question}",
                raw_confidence=0.6,
                evidence_episode_ids=list(primary_episode[:1]),
            ),
            CouncilProposal(
                session_id=session_id,
                agent_name=LensName.SHIVA.value,
                proposal_type=ProposalType.RISK_FINDING.value,
                proposal_text="No structural risk confirmed from supplied evidence.",
                raw_confidence=0.4,
                evidence_world_ids=list(primary_world[:1]),
                risk_flag=False,
            ),
            CouncilProposal(
                session_id=session_id,
                agent_name=LensName.BRAHMA.value,
                proposal_type=ProposalType.VALUE_TRADEOFF.value,
                proposal_text=f"Keep one exploratory alternative available for: {question}",
                raw_confidence=0.6,
                evidence_semantic_ids=list(primary_semantic[:1]),
            ),
            CouncilProposal(
                session_id=session_id,
                agent_name=LensName.HANUMAN.value,
                proposal_type=ProposalType.VALUE_TRADEOFF.value,
                proposal_text=f"Choose the option with the clearest execution path for: {question}",
                raw_confidence=0.6,
                evidence_relation_ids=list(primary_relation[:1]),
            ),
            CouncilProposal(
                session_id=session_id,
                agent_name=LensName.KATTAPPA.value,
                proposal_type=ProposalType.VALUE_TRADEOFF.value,
                proposal_text=f"Align the decision with the user's stated objective for: {question}",
                raw_confidence=0.6,
                evidence_episode_ids=list(primary_episode[:1]),
            ),
        ]

    @classmethod
    def _make_proposals(
        cls,
        session_id: str,
        question: str,
        context: dict[str, Any],
        fallback_evidence: dict[str, list[str]],
    ) -> list[CouncilProposal]:
        raw = context.get("lens_proposals") or context.get("proposals")
        if isinstance(raw, list) and raw:
            return [
                CouncilProposal.from_dict(session_id, item, fallback_evidence)
                for item in raw
                if isinstance(item, dict)
            ]
        return cls._make_default_proposals(session_id, question, fallback_evidence)

    @classmethod
    def _value_plan_for(cls, proposal: CouncilProposal, validation: dict[str, Any], active_veto: bool) -> PlanSignals:
        density = float(validation.get("verified_density", 0.0))
        no_veto = 0.0 if active_veto else 1.0
        return PlanSignals(
            name=proposal.proposal_id,
            validator_score=density,
            reliability_score=density,
            test_score=density,
            safety_score=no_veto,
            novelty=0.7 if proposal.agent_name == LensName.BRAHMA.value else 0.4,
            steps=2 if proposal.agent_name == LensName.HANUMAN.value else 4,
            components=1,
            dependencies=1,
            reversible=proposal.agent_name in {LensName.KRISHNA.value, LensName.HANUMAN.value},
            optionality=0.8 if proposal.agent_name == LensName.KRISHNA.value else 0.5,
            resource_preservation=0.7 if proposal.agent_name == LensName.SHIVA.value else 0.5,
            goal_match=0.8 if proposal.agent_name == LensName.KATTAPPA.value else 0.5,
            capability_coverage=0.8 if proposal.agent_name == LensName.HANUMAN.value else 0.5,
            sim_success=density,
            cost_score=0.6,
            trust_score=density,
        )

    @classmethod
    def _persist_proposal(cls, conn: sqlite3.Connection, proposal: CouncilProposal, calibrated_confidence: float) -> None:
        conn.execute(
            """
            INSERT INTO council_proposals (
                proposal_id, session_id, agent_name, proposal_type, proposal_text,
                raw_confidence, calibrated_confidence, evidence_refs_json, risk_flag,
                option_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal.proposal_id,
                proposal.session_id,
                proposal.agent_name,
                proposal.proposal_type,
                proposal.proposal_text,
                proposal.raw_confidence,
                calibrated_confidence,
                _json({
                    "episode": proposal.evidence_episode_ids,
                    "semantic": proposal.evidence_semantic_ids,
                    "relation": proposal.evidence_relation_ids,
                    "world": proposal.evidence_world_ids,
                }),
                1 if proposal.risk_flag else 0,
                proposal.option_id,
                proposal.created_at,
            ),
        )

    @classmethod
    def _persist_validation(cls, conn: sqlite3.Connection, validation: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO council_validations (
                validation_id, session_id, proposal_id, claim_text, is_verified,
                verified_evidence_ids_json, fabricated_evidence_ids_json,
                verified_density, validator_module, validated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                validation["validation_id"],
                validation["session_id"],
                validation["proposal_id"],
                validation["claim_text"],
                1 if validation["is_verified"] else 0,
                _json(validation["verified_evidence_ids"]),
                _json(validation["fabricated_evidence_ids"]),
                validation["verified_density"],
                validation["validator_module"],
                validation["validated_at"],
            ),
        )

    @classmethod
    def _persist_veto(cls, conn: sqlite3.Connection, veto: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO council_vetoes (
                veto_id, session_id, proposal_id, veto_source, veto_reason,
                structural_evidence_json, overridden_by_human, override_justification, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                veto["veto_id"],
                veto["session_id"],
                veto["proposal_id"],
                veto["veto_source"],
                veto["veto_reason"],
                _json(veto["structural_evidence"]),
                1 if veto.get("overridden_by_human") else 0,
                veto.get("override_justification", ""),
                veto["created_at"],
            ),
        )

    @classmethod
    def deliberate(
        cls,
        *,
        question: str,
        mode_profile: str = ModeProfile.SYSTEM_DEFAULT.value,
        mode_set_by: str = ModeSetBy.SYSTEM.value,
        context: dict[str, Any] | None = None,
        evidence_episode_ids: list[str] | None = None,
        evidence_semantic_ids: list[str] | None = None,
        evidence_relation_ids: list[str] | None = None,
        evidence_world_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        cls._ensure_schema()
        session_id = str(uuid.uuid4())
        outcome_id = str(uuid.uuid4())
        fallback_evidence = cls._fallback_evidence(
            evidence_episode_ids,
            evidence_semantic_ids,
            evidence_relation_ids,
            evidence_world_ids,
        )
        context = cls._context_with_evidence(context, fallback_evidence)
        mode_decision = ModeProfileEnforcer.resolve(mode_profile, mode_set_by)
        mode_weights = MODE_WEIGHTS[mode_decision.active_mode]
        proposals = cls._make_proposals(session_id, question, context, fallback_evidence)

        validations: list[dict[str, Any]] = []
        vetoes: list[dict[str, Any]] = []
        calibrated_by_proposal: dict[str, float] = {}

        with PersonalityCouncilStore.connect() as conn:
            for proposal in proposals:
                calibrated = CouncilCalibration.calibrated_confidence(proposal.agent_name, proposal.raw_confidence)
                calibrated_by_proposal[proposal.proposal_id] = calibrated
                cls._persist_proposal(conn, proposal, calibrated)

                validation = CouncilEvidenceVerifier.verify(proposal, context)
                validations.append(validation)
                cls._persist_validation(conn, validation)

                veto = CouncilRiskVetoLayer.evaluate(proposal, validation, context)
                if veto is not None:
                    vetoes.append(veto)
                    cls._persist_veto(conn, veto)

            vetoed_ids = {item["proposal_id"] for item in vetoes}
            validation_by_proposal = {item["proposal_id"]: item for item in validations}
            candidate_items: list[tuple[CouncilProposal, dict[str, Any], float, dict[str, Any], float, dict[str, float]]] = []
            value_profile = VALUE_PROFILE_BY_MODE[mode_decision.active_mode]

            for proposal in proposals:
                validation = validation_by_proposal[proposal.proposal_id]
                if proposal.proposal_type != ProposalType.VALUE_TRADEOFF.value:
                    continue
                if not validation["is_verified"]:
                    continue
                if proposal.proposal_id in vetoed_ids:
                    continue
                plan = cls._value_plan_for(proposal, validation, active_veto=False)
                value_score = ValueEngine.rank([plan], value_profile).selected.final_score
                lens_scores = ValueEngine.score_plan(plan)
                mode_weight = mode_weights.get(proposal.agent_name, 0.0)
                final_score = round(
                    value_score
                    * mode_weight
                    * calibrated_by_proposal[proposal.proposal_id]
                    * float(validation["verified_density"]),
                    4,
                )
                candidate_items.append((proposal, validation, final_score, plan.__dict__, value_score, lens_scores))

            candidate_items.sort(key=lambda item: (-item[2], item[0].agent_name, item[0].proposal_id))
            ranked_options: list[dict[str, Any]] = []
            for rank_index, (proposal, validation, score, _plan_dict, value_score, lens_scores) in enumerate(candidate_items, start=1):
                ranked = {
                    "ranking_id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "proposal_id": proposal.proposal_id,
                    "agent_name": proposal.agent_name,
                    "option_text": proposal.proposal_text,
                    "rank_index": rank_index,
                    "score": score,
                    "value_engine_score": value_score,
                    "mode_weight": mode_weights.get(proposal.agent_name, 0.0),
                    "raw_confidence": proposal.raw_confidence,
                    "calibrated_confidence": calibrated_by_proposal[proposal.proposal_id],
                    "evidence_density": validation["verified_density"],
                    "lens_scores": lens_scores,
                }
                ranked_options.append(ranked)
                conn.execute(
                    """
                    INSERT INTO council_rankings (
                        ranking_id, session_id, proposal_id, option_text, rank_index, score,
                        value_engine_score, mode_weight, calibrated_confidence,
                        evidence_density, lens_scores_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ranked["ranking_id"],
                        session_id,
                        proposal.proposal_id,
                        proposal.proposal_text,
                        rank_index,
                        score,
                        value_score,
                        ranked["mode_weight"],
                        ranked["calibrated_confidence"],
                        validation["verified_density"],
                        _json(lens_scores),
                        _now(),
                    ),
                )

            consensus_strength = ranked_options[0]["score"] if ranked_options else 0.0
            final_decision = ranked_options[0]["option_text"] if ranked_options else "HUMAN_ESCALATION_REQUIRED"
            if vetoes:
                resolution_path = ResolutionPath.VETOED.value
                final_decision = "VETO_BLOCKED_DECISION"
            elif consensus_strength < 0.60:
                resolution_path = ResolutionPath.ESCALATED_TO_HUMAN.value
            else:
                resolution_path = ResolutionPath.VALUE_RANKED.value

            dissent: list[dict[str, Any]] = []
            winning_id = ranked_options[0]["proposal_id"] if ranked_options else ""
            for proposal in proposals:
                validation = validation_by_proposal[proposal.proposal_id]
                if proposal.proposal_id == winning_id:
                    continue
                if not validation["is_verified"]:
                    continue
                if proposal.proposal_type == ProposalType.FACTUAL_CLAIM.value:
                    continue
                if proposal.proposal_type == ProposalType.RISK_FINDING.value and not vetoes:
                    continue
                dissent_row = {
                    "dissent_id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "proposal_id": proposal.proposal_id,
                    "agent_name": proposal.agent_name,
                    "dissent_text": proposal.proposal_text,
                    "rationale": "preserved_non_selected_validated_perspective",
                    "risks": [proposal.proposal_text] if proposal.risk_flag else [],
                    "evidence_type": "verified" if validation["is_verified"] else "unverified",
                    "confidence": calibrated_by_proposal[proposal.proposal_id],
                    "evidence_refs": validation["verified_evidence_ids"],
                    "archived_at": _now(),
                }
                dissent.append(dissent_row)
                conn.execute(
                    """
                    INSERT INTO council_dissent_archive (
                        dissent_id, session_id, proposal_id, agent_name, dissent_text,
                        rationale, risks_json, evidence_type, confidence,
                        evidence_refs_json, archived_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dissent_row["dissent_id"],
                        session_id,
                        proposal.proposal_id,
                        proposal.agent_name,
                        proposal.proposal_text,
                        dissent_row["rationale"],
                        _json(dissent_row["risks"]),
                        dissent_row["evidence_type"],
                        dissent_row["confidence"],
                        _json(dissent_row["evidence_refs"]),
                        dissent_row["archived_at"],
                    ),
                )

            arbiter_findings = CouncilArbiter.evaluate(
                proposals=proposals,
                validations=validations,
                vetoes=vetoes,
                ranked_options=ranked_options,
                consensus_strength=consensus_strength,
            )

            blocking = any(item.get("severity") == "blocking" for item in arbiter_findings)
            if blocking and resolution_path == ResolutionPath.VALUE_RANKED.value:
                resolution_path = ResolutionPath.ESCALATED_TO_HUMAN.value
            human_approval_required = True
            auto_applied = False

            supporting_agents = []
            if winning_id:
                supporting_agents = [
                    proposal.agent_name for proposal in proposals if proposal.proposal_id == winning_id
                ]
            opposing_agents = [item["agent_name"] for item in dissent]

            conn.execute(
                """
                INSERT INTO council_sessions (
                    session_id, question, requested_mode_profile, active_mode_profile,
                    mode_set_by, context_json, mode_weights_json, consensus_strength,
                    final_decision, resolution_path, human_approval_required,
                    auto_applied, arbiter_findings_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    question,
                    mode_decision.requested_mode,
                    mode_decision.active_mode,
                    mode_decision.requested_set_by,
                    _json(context),
                    _json(mode_weights),
                    consensus_strength,
                    final_decision,
                    resolution_path,
                    1 if human_approval_required else 0,
                    1 if auto_applied else 0,
                    _json(arbiter_findings),
                    _now(),
                ),
            )
            conn.execute(
                """
                INSERT INTO council_outcomes (
                    outcome_id, session_id, predicted_success, actual_success,
                    final_decision, supporting_agents_json, opposing_agents_json,
                    source_episode_id, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome_id,
                    session_id,
                    consensus_strength,
                    None,
                    final_decision,
                    _json(supporting_agents),
                    _json(opposing_agents),
                    None,
                    "",
                    _now(),
                    _now(),
                ),
            )

        manifest = {
            "session_id": session_id,
            "outcome_id": outcome_id,
            "question": question,
            "requested_mode_profile": mode_decision.requested_mode,
            "active_mode_profile": mode_decision.active_mode,
            "mode_profile": mode_decision.active_mode,
            "mode_set_by": mode_decision.requested_set_by,
            "mode_reason": mode_decision.reason,
            "final_decision": final_decision,
            "consensus_strength": consensus_strength,
            "resolution_path": resolution_path,
            "validator_results": validations,
            "active_vetoes": vetoes,
            "ranked_options": ranked_options,
            "dissent": dissent,
            "arbiter_findings": arbiter_findings,
            "calibration_snapshot": CouncilCalibration.snapshot([proposal.agent_name for proposal in proposals]),
            "human_approval_required": human_approval_required,
            "auto_applied": auto_applied,
        }
        return {"decision_manifest": manifest, **manifest}

    @classmethod
    def get_session(cls, session_id: str) -> dict[str, Any] | None:
        cls._ensure_schema()
        with PersonalityCouncilStore.connect() as conn:
            session = conn.execute("SELECT * FROM council_sessions WHERE session_id = ?", (session_id,)).fetchone()
            if not session:
                return None
            proposals = conn.execute("SELECT * FROM council_proposals WHERE session_id = ?", (session_id,)).fetchall()
            validations = conn.execute("SELECT * FROM council_validations WHERE session_id = ?", (session_id,)).fetchall()
            vetoes = conn.execute("SELECT * FROM council_vetoes WHERE session_id = ?", (session_id,)).fetchall()
            rankings = conn.execute("SELECT * FROM council_rankings WHERE session_id = ? ORDER BY rank_index", (session_id,)).fetchall()
            dissent = conn.execute("SELECT * FROM council_dissent_archive WHERE session_id = ?", (session_id,)).fetchall()
        return {
            "session": dict(session),
            "proposals": [dict(row) for row in proposals],
            "validations": [dict(row) for row in validations],
            "vetoes": [dict(row) for row in vetoes],
            "rankings": [dict(row) for row in rankings],
            "dissent": [dict(row) for row in dissent],
        }

    @classmethod
    def performance(cls) -> dict[str, Any]:
        cls._ensure_schema()
        with PersonalityCouncilStore.connect() as conn:
            sessions = conn.execute("SELECT COUNT(*) AS c FROM council_sessions").fetchone()["c"]
            outcomes = conn.execute("SELECT COUNT(*) AS c FROM council_outcome_validation").fetchone()["c"]
        return {
            "sessions": int(sessions or 0),
            "outcome_validations": int(outcomes or 0),
            "calibration": CouncilCalibration.snapshot(),
        }


class CouncilOutcomeLoop:
    """Records actual results and updates lens calibration history."""

    _schema_ensured = False

    @classmethod
    def record_outcome(
        cls,
        *,
        outcome_id: str,
        predicted_success: float | None = None,
        actual_success: float | None = None,
        source_episode_id: str | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        PersonalityCouncilStore.ensure_schema()
        with PersonalityCouncilStore.connect() as conn:
            outcome = conn.execute("SELECT * FROM council_outcomes WHERE outcome_id = ?", (outcome_id,)).fetchone()
            if not outcome:
                raise KeyError(f"Council outcome {outcome_id} not found")

            session_id = outcome["session_id"]
            effective_predicted = predicted_success if predicted_success is not None else outcome["predicted_success"]
            validation_id = str(uuid.uuid4())
            now = _now()
            conn.execute(
                """
                INSERT INTO council_outcome_validation (
                    validation_id, outcome_id, session_id, predicted_success,
                    actual_success, source_episode_id, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    validation_id,
                    outcome_id,
                    session_id,
                    effective_predicted,
                    actual_success,
                    source_episode_id,
                    notes,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE council_outcomes
                SET predicted_success = ?, actual_success = ?, source_episode_id = ?,
                    notes = ?, updated_at = ?
                WHERE outcome_id = ?
                """,
                (effective_predicted, actual_success, source_episode_id, notes, now, outcome_id),
            )

            updated_agents: list[dict[str, Any]] = []
            if actual_success is not None:
                actual_bool = float(actual_success) >= 0.5
                supporting = _loads(outcome["supporting_agents_json"], [])
                opposing = _loads(outcome["opposing_agents_json"], [])
                for agent in supporting:
                    correct = actual_bool
                    conn.execute(
                        """
                        INSERT INTO agent_accuracy_history (
                            history_id, agent_name, session_id, proposal_id, outcome_id,
                            predicted_success, actual_success, prediction_correct, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            agent,
                            session_id,
                            None,
                            outcome_id,
                            effective_predicted,
                            actual_success,
                            1 if correct else 0,
                            now,
                        ),
                    )
                    updated_agents.append({"agent_name": agent, "prediction_correct": bool(correct)})
                for agent in opposing:
                    correct = not actual_bool
                    conn.execute(
                        """
                        INSERT INTO agent_accuracy_history (
                            history_id, agent_name, session_id, proposal_id, outcome_id,
                            predicted_success, actual_success, prediction_correct, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            agent,
                            session_id,
                            None,
                            outcome_id,
                            effective_predicted,
                            actual_success,
                            1 if correct else 0,
                            now,
                        ),
                    )
                    updated_agents.append({"agent_name": agent, "prediction_correct": bool(correct)})

        return {
            "validation_id": validation_id,
            "outcome_id": outcome_id,
            "session_id": session_id,
            "predicted_success": effective_predicted,
            "actual_success": actual_success,
            "source_episode_id": source_episode_id,
            "updated_agents": updated_agents,
            "calibration_snapshot": CouncilCalibration.snapshot(),
        }
