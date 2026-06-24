"""Council of Perspectives (Step 15.5 + Council v2).

A structured, measurable multi-perspective deliberation layer built on top of
the existing ConsensusEngine. Does NOT replace or modify ConsensusEngine.

Design rules:
- 12 perspectives = cognitive functions, NOT competing personalities.
- Each perspective returns structured JSON, not a paragraph.
- Auditor is adversarial meta-role: finds flaws, never votes.
- ConsensusEngine.decide() handles all math unchanged.
- Every session is persisted to SQLite (decision ledger).
- Council is OPT-IN: caller must pass use_council=True.
- Nothing auto-applies. Human approval gate is unchanged.

Full deliberation: up to 13 LLM calls (12 perspectives + 1 Auditor).
Quick deliberation: top-N by weight + 1 Auditor (default N=3 → 4 calls max).
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root
from backend.core.logger import log_event


# ─────────────────────────────────────────────────────────────────────────────
# Council Roster
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CouncilPerspective:
    role: str
    function: str                       # cognitive function label
    domains: tuple[str, ...]           # question_types where this role is amplified
    base_weight: float                  # static fallback weight
    is_auditor: bool = False            # Auditor never votes — adversarial meta-role only

    def amplified_weight(self, question_type: str) -> float:
        """Return weight multiplied by context-adaptive factor."""
        mult = CONTEXT_WEIGHT_AMPLIFIERS.get(question_type, {}).get(self.role, 1.0)
        return self.base_weight * mult


# 12 perspectives mapping to distinct cognitive functions
COUNCIL_ROSTER: list[CouncilPerspective] = [
    CouncilPerspective("Rama",        "Long-term planning",       ("architecture", "planning"),    1.2),
    CouncilPerspective("Krishna",     "Strategy and tradeoffs",   ("planning", "decisions"),       1.2),
    CouncilPerspective("Shiva",       "Simplification & pruning", ("architecture", "refactoring"), 1.2),
    CouncilPerspective("Brahma",      "Idea generation",          ("research", "design"),          1.0),
    CouncilPerspective("Hanuman",     "Execution feasibility",    ("implementation",),             1.0),
    CouncilPerspective("Kattappa",    "User alignment",           ("user_impact", "ethics"),       1.5),
    CouncilPerspective("Scientist",   "Evidence evaluation",      ("research", "benchmarks"),      1.5),
    CouncilPerspective("Engineer",    "Implementation review",    ("code", "performance"),         1.3),
    CouncilPerspective("Teacher",     "Explanation quality",      ("documentation", "user_impact"),1.0),
    CouncilPerspective("Security",    "Safety review",            ("safety", "memory", "data"),    1.5),
    CouncilPerspective("MemoryKeeper","Memory consistency",       ("memory", "storage"),           1.0),
    CouncilPerspective("Auditor",     "Adversarial critique",     (),                              0.0,
                       is_auditor=True),
]

ROSTER_BY_ROLE: dict[str, CouncilPerspective] = {p.role: p for p in COUNCIL_ROSTER}
VOTING_ROSTER: list[CouncilPerspective] = [p for p in COUNCIL_ROSTER if not p.is_auditor]

# Context-adaptive weight amplifiers per question_type per role.
# Values >1.0 amplify; 1.0 = no change.
CONTEXT_WEIGHT_AMPLIFIERS: dict[str, dict[str, float]] = {
    "safety": {
        "Security": 1.5, "Kattappa": 1.5, "Scientist": 1.5,
        "MemoryKeeper": 1.3, "Engineer": 1.1,
    },
    "research": {
        "Scientist": 1.5, "Engineer": 1.3, "Rama": 1.2,
        "Brahma": 1.3, "Krishna": 1.1,
    },
    "user_impact": {
        "Kattappa": 1.5, "Krishna": 1.3, "Teacher": 1.2,
        "Rama": 1.1, "Hanuman": 1.1,
    },
    "architecture": {
        "Shiva": 1.3, "Engineer": 1.3, "Brahma": 1.2,
        "Rama": 1.2, "Krishna": 1.1,
    },
    "general": {},   # no amplification; use base weights
}

ALL_QUESTION_TYPES: frozenset[str] = frozenset(CONTEXT_WEIGHT_AMPLIFIERS)


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CouncilResult:
    decision_id: str
    question: str
    question_type: str
    consensus_status: str               # 'approved'|'rejected'|'escalate'|'no_feasible_solution'
    requires_human_approval: bool
    selected_recommendation: str | None
    approve_mass: float
    reject_mass: float
    margin: float | None
    votes: list[dict[str, Any]]         # one entry per voting perspective
    audit_findings: list[dict[str, Any]] # Auditor CriticFindings
    reasons: list[str]
    created_at: float
    governance_proposal_id: str | None = None
    strategic_decision_id: str | None = None
    mode_profile: str = "system_default"
    dissent: list[dict[str, Any]] = field(default_factory=list)
    arbiter_findings: list[dict[str, Any]] = field(default_factory=list)
    calibration_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# SQLite schema & helpers
# ─────────────────────────────────────────────────────────────────────────────

_WRITE_LOCK = threading.Lock()
_schema_ensured: set[str] = set()


def _db_path() -> Path:
    p = runtime_data_root() / "backend" / "data" / "council_decisions.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS council_decisions (
    id                      TEXT PRIMARY KEY,
    question                TEXT NOT NULL,
    question_type           TEXT NOT NULL,
    context_json            TEXT NOT NULL DEFAULT '{}',
    created_at              REAL NOT NULL,
    completed_at            REAL,
    consensus_status        TEXT,
    requires_human          INTEGER NOT NULL DEFAULT 0,
    selected_recommendation TEXT,
    approve_mass            REAL,
    reject_mass             REAL,
    margin                  REAL,
    reasons_json            TEXT NOT NULL DEFAULT '[]',
    governance_proposal_id  TEXT,
    strategic_decision_id   TEXT,
    active_mode_profile     TEXT NOT NULL DEFAULT 'system_default',
    mode_set_by             TEXT NOT NULL DEFAULT 'SYSTEM',
    arbiter_findings_json   TEXT NOT NULL DEFAULT '[]',
    dissent_json            TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_cd_created ON council_decisions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cd_status  ON council_decisions(consensus_status);

CREATE TABLE IF NOT EXISTS council_votes (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id             TEXT NOT NULL,
    perspective             TEXT NOT NULL,
    vote                    TEXT NOT NULL,
    confidence              REAL NOT NULL,
    evidence_type           TEXT,
    rationale               TEXT,
    risks_json              TEXT NOT NULL DEFAULT '[]',
    benefits_json           TEXT NOT NULL DEFAULT '[]',
    vote_weight             REAL,
    logged_at               REAL NOT NULL,
    calibrated_confidence   REAL,
    evidence_refs_json      TEXT NOT NULL DEFAULT '[]',
    calibration_factor      REAL
);
CREATE INDEX IF NOT EXISTS idx_cv_decision ON council_votes(decision_id);

CREATE TABLE IF NOT EXISTS council_audit_findings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id      TEXT NOT NULL,
    finding_category TEXT NOT NULL,
    description      TEXT NOT NULL,
    logged_at        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_caf_decision ON council_audit_findings(decision_id);

CREATE TABLE IF NOT EXISTS council_benchmarks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id     TEXT NOT NULL,
    outcome         TEXT,
    outcome_score   REAL,
    evaluated_at    REAL,
    predicted_success REAL,
    actual_success  REAL,
    notes           TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_cb_decision ON council_benchmarks(decision_id);

CREATE TABLE IF NOT EXISTS agent_accuracy_history (
    history_id           TEXT PRIMARY KEY,
    agent_name           TEXT NOT NULL,
    session_id           TEXT,
    outcome_id           TEXT,
    predicted_success    REAL,
    actual_success       REAL,
    prediction_correct   INTEGER,
    created_at           REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aah_agent ON agent_accuracy_history(agent_name);

CREATE TABLE IF NOT EXISTS council_dissent_archive (
    dissent_id           TEXT PRIMARY KEY,
    decision_id          TEXT NOT NULL,
    perspective          TEXT NOT NULL,
    vote                 TEXT NOT NULL,
    confidence           REAL NOT NULL,
    evidence_type        TEXT,
    rationale            TEXT,
    risks_json           TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json   TEXT NOT NULL DEFAULT '[]',
    archived_at          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cda_decision ON council_dissent_archive(decision_id);
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
                
                # Apply updates to existing tables if they already exist without these columns:
                for col, ty in [
                    ("active_mode_profile", "TEXT NOT NULL DEFAULT 'system_default'"),
                    ("mode_set_by", "TEXT NOT NULL DEFAULT 'SYSTEM'"),
                    ("arbiter_findings_json", "TEXT NOT NULL DEFAULT '[]'"),
                    ("dissent_json", "TEXT NOT NULL DEFAULT '[]'")
                ]:
                    try:
                        conn.execute(f"ALTER TABLE council_decisions ADD COLUMN {col} {ty}")
                    except sqlite3.OperationalError:
                        pass
                
                for col, ty in [
                    ("calibrated_confidence", "REAL"),
                    ("evidence_refs_json", "TEXT NOT NULL DEFAULT '[]'"),
                    ("calibration_factor", "REAL")
                ]:
                    try:
                        conn.execute(f"ALTER TABLE council_votes ADD COLUMN {col} {ty}")
                    except sqlite3.OperationalError:
                        pass
                
                for col, ty in [
                    ("predicted_success", "REAL"),
                    ("actual_success", "REAL"),
                    ("notes", "TEXT NOT NULL DEFAULT ''")
                ]:
                    try:
                        conn.execute(f"ALTER TABLE council_benchmarks ADD COLUMN {col} {ty}")
                    except sqlite3.OperationalError:
                        pass
                
                conn.commit()
            finally:
                conn.close()
            _schema_ensured.add(key)


# ─────────────────────────────────────────────────────────────────────────────
# LLM prompt helpers
# ─────────────────────────────────────────────────────────────────────────────

_PERSPECTIVE_SYSTEM = (
    "You are a structured decision advisor. "
    "Respond ONLY with valid JSON. No markdown, no prose."
)

_PERSPECTIVE_PROMPT = """You are {role}, the "{function}" perspective in Kattappa's Council of Perspectives.

Question: {question}
Question type: {question_type}
Context: {context}

Your role's primary concern: {function}.
Analyze the question strictly from your perspective.

Respond ONLY with this JSON structure:
{{
  "decision": "APPROVE" | "REJECT" | "ABSTAIN",
  "confidence": <float 0.0–1.0>,
  "evidence_type": "reasoning" | "test_results" | "historical" | "simulation" | "tool_verified",
  "risks": [<string>, ...],
  "benefits": [<string>, ...],
  "rationale": "<one concise sentence>"
}}

ABSTAIN if this question is outside your domain of expertise.
Do not repeat other perspectives' views."""

_AUDITOR_SYSTEM = (
    "You are the Auditor, a critical adversarial reviewer. "
    "Respond ONLY with valid JSON. No markdown, no prose."
)

_AUDITOR_PROMPT = """You are the Auditor in Kattappa's Council of Perspectives.
Your role: find flaws in the other perspectives' reasoning. You are adversarial. You do NOT vote.

Question: {question}
Other perspectives' outputs:
{perspectives_summary}

Find: flawed assumptions, missing evidence, failure modes, contradictions, groupthink patterns.

Respond ONLY with this JSON structure:
{{
  "findings": [
    {{
      "category": "blocking" | "advisory",
      "description": "<specific flaw or gap found>"
    }}
  ]
}}

A "blocking" finding means a critical flaw that must be addressed before approval.
An "advisory" finding is a risk to note but not necessarily blocking.
Return an empty findings list if reasoning is sound."""


def _parse_structured_json(raw: str) -> dict[str, Any] | None:
    """Extract and parse the first JSON object from an LLM response."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# CouncilSession
# ─────────────────────────────────────────────────────────────────────────────

class CouncilCalibration:
    @classmethod
    def get_calibration_factor(cls, agent_name: str) -> float:
        # Compute calibration_factor = 1.0 until at least 3 judged votes,
        # then correct / judged, clamped to 0.25..1.0
        conn = _connect()
        try:
            row = conn.execute(
                """
                SELECT COUNT(*) as judged,
                       SUM(case when prediction_correct = 1 then 1 else 0 end) as correct
                FROM agent_accuracy_history
                WHERE agent_name = ? AND prediction_correct IS NOT NULL
                """,
                (agent_name,)
            ).fetchone()
            judged = row["judged"] if row else 0
            correct = row["correct"] if row and row["correct"] is not None else 0
            if judged < 3:
                return 1.0
            factor = float(correct) / float(judged)
            return max(0.25, min(1.0, factor))
        except Exception:
            return 1.0
        finally:
            conn.close()


class CouncilArbiter:
    @classmethod
    def evaluate(
        cls,
        *,
        question: str,
        votes: list[dict[str, Any]],
        available_refs: set[str],
        consensus_status: str,
        consensus_strength: float,
        requires_human_approval: bool,
    ) -> list[dict[str, Any]]:
        findings = []
        
        # 1. Unverified evidence & Missing traceability
        for v in votes:
            perspective = v["perspective"]
            cited = v.get("evidence_refs", [])
            # check unverified
            unverified = [ref for ref in cited if ref not in available_refs]
            if unverified:
                findings.append({
                    "rule": "unverified_evidence",
                    "severity": "blocking",
                    "perspective": perspective,
                    "message": f"Perspective {perspective} cited unverified evidence: {unverified}"
                })
            # check missing traceability
            if not cited and v.get("vote") != "ABSTAIN":
                findings.append({
                    "rule": "missing_traceability",
                    "severity": "advisory",
                    "perspective": perspective,
                    "message": f"Perspective {perspective} has no evidence references linked."
                })
                
        # 2. Unsupported high confidence
        for v in votes:
            perspective = v["perspective"]
            raw_conf = v.get("confidence", 0.0)
            judged = v.get("historical_judged", 0)
            if raw_conf > 0.95 and judged < 3:
                findings.append({
                    "rule": "unsupported_high_confidence",
                    "severity": "blocking",
                    "perspective": perspective,
                    "message": f"Perspective {perspective} claimed confidence {raw_conf} > 0.95 before 3 calibration records exist."
                })
                
        # 3. Vote stacking
        seen_perspectives = set()
        for v in votes:
            perspective = v["perspective"]
            if perspective in seen_perspectives:
                findings.append({
                    "rule": "vote_stacking",
                    "severity": "blocking",
                    "perspective": perspective,
                    "message": f"Perspective {perspective} voted multiple times in the same session."
                })
            seen_perspectives.add(perspective)
            
        # 4. Circular reasoning
        for v in votes:
            perspective = v["perspective"]
            rat = v.get("rationale", "")
            if rat and len(rat.split()) > 3:
                words = rat.lower().split()
                # Check for simple repetition of words
                if len(set(words)) < len(words) * 0.5:
                    findings.append({
                        "rule": "circular_reasoning",
                        "severity": "advisory",
                        "perspective": perspective,
                        "message": f"Perspective {perspective} has potential circular reasoning in rationale: '{rat}'"
                    })
                    
        # 5. Low consensus / deadlock (if winner doesn't clear 60% threshold)
        if consensus_status == "approved" and consensus_strength < 0.60:
            findings.append({
                "rule": "deadlock",
                "severity": "blocking",
                "message": f"Consensus strength {consensus_strength:.2f} is below the 0.60 threshold."
            })
            
        return findings


MODE_PROFILES = {
    "system_default": {
        "Rama": 2.5, "Krishna": 0.5, "Shiva": 0.5, "Brahma": 2.5, "Hanuman": 1.0, "Kattappa": 3.0
    },
    "engineering_standard": {
        "Rama": 2.0, "Krishna": 1.5, "Shiva": 1.5, "Brahma": 2.0, "Hanuman": 1.5, "Kattappa": 1.5
    },
    "critical_fix": {
        "Rama": 4.0, "Krishna": 1.0, "Shiva": 3.0, "Brahma": 0.0, "Hanuman": 2.0, "Kattappa": 0.0
    },
    "innovation": {
        "Rama": 1.0, "Krishna": 1.5, "Shiva": 0.5, "Brahma": 4.0, "Hanuman": 1.0, "Kattappa": 2.0
    }
}


def select_mode_profile(question: str, question_type: str, context: dict[str, Any]) -> str:
    q = question.lower()
    qt = question_type.lower()
    
    is_safety = (
        qt == "safety" or
        context.get("production") is True or
        context.get("production_system") is True or
        any(k in q for k in ("safety", "production", "outage", "secrets", "destructive", "delete", "destroy", "drop", "truncate", "credential", "api_key", "password", "token"))
    )
    if is_safety:
        return "critical_fix"
        
    is_eng = (
        qt in ("architecture", "refactoring", "code", "implementation") or
        context.get("code_change") is True or
        any(k in q for k in ("architecture", "refactor", "code", "implementation", "rewrite", "compile", "class", "function", "modify", "database", "schema", "performance"))
    )
    if is_eng:
        return "engineering_standard"
        
    is_innov = (
        qt in ("research", "design", "brainstorm") or
        any(k in q for k in ("brainstorm", "design", "future", "research", "ideas", "suggest", "concept", "creative", "new feature"))
    )
    if is_innov:
        return "innovation"
        
    return "system_default"


class CouncilSession:
    """Orchestrates a full or quick council deliberation.

    Public API
    ----------
    deliberate(question, question_type, context, code_change, production, mode_profile)
        Full deliberation: all 11 voting perspectives + Auditor.

    quick_deliberate(question, question_type, context, n, code_change, production, mode_profile)
        Fast path: top-N perspectives by amplified weight + Auditor.
    """

    @classmethod
    def deliberate(
        cls,
        question: str,
        question_type: str = "general",
        context: dict[str, Any] | None = None,
        *,
        code_change: bool = False,
        production: bool = False,
        mode_profile: str = "auto",
    ) -> CouncilResult:
        """Full deliberation: all 11 voting perspectives + 1 Auditor call."""
        return cls._run(
            question=question,
            question_type=question_type,
            context=context or {},
            perspectives=VOTING_ROSTER,
            code_change=code_change,
            production=production,
            mode_profile=mode_profile,
        )

    @classmethod
    def quick_deliberate(
        cls,
        question: str,
        question_type: str = "general",
        context: dict[str, Any] | None = None,
        n: int = 3,
        *,
        code_change: bool = False,
        production: bool = False,
        mode_profile: str = "auto",
    ) -> CouncilResult:
        """Fast-path deliberation: top-N perspectives by amplified weight + Auditor.

        Default n=3 → max 4 LLM calls.
        Always includes Security if question_type='safety'.
        """
        qt = question_type if question_type in ALL_QUESTION_TYPES else "general"

        # Sort by amplified weight desc; break ties by base_weight
        ranked = sorted(
            VOTING_ROSTER,
            key=lambda p: (-p.amplified_weight(qt), -p.base_weight, p.role),
        )
        # Always include Security for safety questions
        selected: list[CouncilPerspective] = []
        if qt == "safety":
            security = ROSTER_BY_ROLE.get("Security")
            if security:
                selected.append(security)
                ranked = [p for p in ranked if p.role != "Security"]

        n_remaining = max(0, n - len(selected))
        selected.extend(ranked[:n_remaining])

        return cls._run(
            question=question,
            question_type=qt,
            context=context or {},
            perspectives=selected,
            code_change=code_change,
            production=production,
            mode_profile=mode_profile,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Core execution
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def _run(
        cls,
        question: str,
        question_type: str,
        context: dict[str, Any],
        perspectives: list[CouncilPerspective],
        *,
        code_change: bool,
        production: bool,
        mode_profile: str = "auto",
    ) -> CouncilResult:
        from backend.core.consensus_engine import (
            AgentOutput, ConsensusEngine, DecisionContext,
            CriticFinding, FindingCategory,
        )

        _ensure_schema()
        decision_id = str(uuid.uuid4())
        created_at = time.time()
        qt = question_type if question_type in ALL_QUESTION_TYPES else "general"

        # Resolve mode profile
        profile = mode_profile.strip().lower()
        mode_set_by = "HUMAN" if profile != "auto" else "SYSTEM"
        if profile == "auto":
            profile = select_mode_profile(question, question_type, context)
        elif profile not in MODE_PROFILES:
            profile = "system_default"

        # 1. Build weights map for these perspectives
        active_weights = {}
        for p in perspectives:
            if p.role in MODE_PROFILES[profile]:
                active_weights[p.role] = MODE_PROFILES[profile][p.role]
            else:
                active_weights[p.role] = p.amplified_weight(qt)

        # Build available refs
        available_refs = set()
        for key in ("episodic_ids", "semantic_ids", "relationship_ids", "world_model_ids", "evidence_ids",
                    "evidence_episode_ids", "evidence_semantic_ids", "evidence_relation_ids", "evidence_world_ids"):
            val = context.get(key)
            if isinstance(val, list):
                available_refs.update(str(item) for item in val if item)
            elif isinstance(val, str) and val:
                available_refs.add(val)
        available_refs_str = ", ".join(sorted(available_refs)) if available_refs else "None"

        # 2. Elicit each perspective
        agent_outputs: list[AgentOutput] = []
        vote_records: list[dict[str, Any]] = []

        for perspective in perspectives:
            output, vote_rec = cls._elicit_perspective(
                perspective=perspective,
                question=question,
                question_type=qt,
                context=context,
                available_refs_str=available_refs_str,
                available_refs=available_refs,
                active_weights=active_weights,
            )
            agent_outputs.append(output)
            vote_records.append(vote_rec)

        # 3. Auditor adversarial pass
        audit_findings: list[dict[str, Any]] = []
        auditor_role = ROSTER_BY_ROLE.get("Auditor")
        if auditor_role:
            critic_findings, audit_findings = cls._run_auditor(
                question=question, outputs=agent_outputs
            )
            if critic_findings:
                auditor_ao = AgentOutput(
                    agent="Auditor",
                    critic_findings=tuple(critic_findings),
                    source_id="auditor_model",
                )
                agent_outputs.append(auditor_ao)

        # Pass calibrated dynamic weights to decide()
        decide_weights = {}
        for ao, vr in zip(agent_outputs, vote_records):
            role = ao.agent
            m_weight = active_weights.get(role, 1.0)
            cal_factor = vr.get("calibration_factor", 1.0)
            # (m_weight * raw_confidence * calibration_factor) / 10.0
            decide_weights[role] = (m_weight * ao.confidence * cal_factor) / 10.0

        # 4. ConsensusEngine.decide()
        dc = DecisionContext(
            project=context.get("project", ""),
            code_change=code_change,
            high_cost_change=context.get("high_cost_change", False),
            production_system=production,
        )
        decision = ConsensusEngine.decide(agent_outputs, dc, decide_weights)

        completed_at = time.time()
        selected_text = (
            decision.selected.message if decision.selected else None
        )

        # Compute consensus strength
        consensus_strength = decision.approve_mass / (decision.approve_mass + decision.reject_mass) if (decision.approve_mass + decision.reject_mass) > 0 else 0.0

        # Arbiter checks
        arbiter_findings = CouncilArbiter.evaluate(
            question=question,
            votes=vote_records,
            available_refs=available_refs,
            consensus_status=decision.status.value,
            consensus_strength=consensus_strength,
            requires_human_approval=decision.requires_human_approval,
        )
        
        status_value = decision.status.value
        human_approval = decision.requires_human_approval
        
        # If there is any blocking arbiter finding, force escalate
        if any(f["severity"] == "blocking" for f in arbiter_findings):
            status_value = "escalate"
            human_approval = True

        # Dissent preservation
        dissent_records = []
        if status_value in ("approved", "rejected"):
            for vr in vote_records:
                role = vr["perspective"]
                vote = vr["vote"]
                is_dissent = (
                    (status_value == "approved" and vote == "REJECT") or
                    (status_value == "rejected" and vote == "APPROVE")
                )
                if is_dissent:
                    dissent_id = str(uuid.uuid4())
                    dissent_row = {
                        "dissent_id": dissent_id,
                        "decision_id": decision_id,
                        "perspective": role,
                        "vote": vote,
                        "confidence": vr.get("confidence", 0.5),
                        "evidence_type": vr.get("evidence_type", "reasoning"),
                        "rationale": vr.get("rationale", ""),
                        "risks": vr.get("risks", []),
                        "evidence_refs": vr.get("evidence_refs", []),
                        "calibration_factor": vr.get("calibration_factor", 1.0)
                    }
                    dissent_records.append(dissent_row)

        gov_proposal_id = cls._maybe_submit_governance(
            decision, question, question_type, context
        )
        strategic_id = cls._record_to_strategic_memory(
            decision_id, question, question_type, decision, gov_proposal_id
        )

        cls._persist(
            decision_id=decision_id,
            question=question,
            question_type=qt,
            context_json=json.dumps(context),
            created_at=created_at,
            completed_at=completed_at,
            decision=decision,
            vote_records=vote_records,
            audit_findings=audit_findings,
            governance_proposal_id=gov_proposal_id,
            strategic_decision_id=strategic_id,
            active_mode_profile=profile,
            mode_set_by=mode_set_by,
            arbiter_findings_json=json.dumps(arbiter_findings),
            dissent_json=json.dumps(dissent_records),
        )

        log_event("COUNCIL_DELIBERATION_COMPLETE", {
            "decision_id": decision_id,
            "question_type": qt,
            "perspectives_count": len(perspectives),
            "consensus_status": status_value,
            "requires_human": human_approval,
        })

        # Fetch calibration snapshot
        cal_snap = {}
        for vr in vote_records:
            cal_snap[vr["perspective"]] = {
                "judged": vr.get("historical_judged", 0),
                "correct": vr.get("historical_correct", 0),
                "calibration_factor": vr.get("calibration_factor", 1.0)
            }

        return CouncilResult(
            decision_id=decision_id,
            question=question,
            question_type=qt,
            consensus_status=status_value,
            requires_human_approval=human_approval,
            selected_recommendation=selected_text,
            approve_mass=round(decision.approve_mass, 4),
            reject_mass=round(decision.reject_mass, 4),
            margin=round(decision.margin, 4) if decision.margin is not None else None,
            votes=vote_records,
            audit_findings=audit_findings,
            reasons=decision.reasons,
            created_at=created_at,
            governance_proposal_id=gov_proposal_id,
            strategic_decision_id=strategic_id,
            mode_profile=profile,
            dissent=dissent_records,
            arbiter_findings=arbiter_findings,
            calibration_snapshot=cal_snap,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Perspective elicitation
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def _elicit_perspective(
        cls,
        perspective: CouncilPerspective,
        question: str,
        question_type: str,
        context: dict[str, Any],
        available_refs_str: str,
        available_refs: set[str],
        active_weights: dict[str, float],
    ) -> tuple[Any, dict[str, Any]]:
        """Call the LLM for one perspective. Returns (AgentOutput, vote_record)."""
        from backend.core.consensus_engine import (
            AgentOutput, Decision, EvidenceType, Recommendation,
        )
        from backend.core.model_router import ask_model

        prompt = _PERSPECTIVE_PROMPT.format(
            role=perspective.role,
            function=perspective.function,
            question=question,
            question_type=question_type,
            context=json.dumps(context),
        )

        traceability_instructions = (
            f"\n\nAvailable memory evidence references you can cite: {available_refs_str}\n"
            "Your JSON response MUST include an \"evidence_refs\" key, which is a list of references "
            "selected from the available references above that support your reasoning. "
            "Do not cite any other references."
        )
        prompt += traceability_instructions

        raw: str = ""
        parsed: dict[str, Any] | None = None
        try:
            raw = ask_model(prompt, role="fast", system=_PERSPECTIVE_SYSTEM)
            parsed = _parse_structured_json(raw)
        except Exception:
            pass

        # Defaults on parse failure → ABSTAIN with reasoning evidence
        if not parsed:
            parsed = {
                "decision": "ABSTAIN",
                "confidence": 0.5,
                "evidence_type": "reasoning",
                "risks": [],
                "benefits": [],
                "rationale": "Parse failure — defaulting to ABSTAIN.",
                "evidence_refs": [],
            }

        decision_str = str(parsed.get("decision", "ABSTAIN")).strip().upper()
        confidence = float(parsed.get("confidence", 0.5))
        ev_type_str = str(parsed.get("evidence_type", "reasoning")).lower()
        risks: list[str] = parsed.get("risks", []) or []
        benefits: list[str] = parsed.get("benefits", []) or []
        rationale: str = str(parsed.get("rationale", ""))

        # evidence refs verification
        cited_refs = parsed.get("evidence_refs") or parsed.get("evidence_ids") or []
        if isinstance(cited_refs, str):
            cited_refs = [cited_refs]
        elif not isinstance(cited_refs, list):
            cited_refs = []
        verified_refs = [ref for ref in cited_refs if ref in available_refs]

        try:
            decision_enum = Decision.coerce(decision_str)
        except Exception:
            decision_enum = Decision.ABSTAIN

        try:
            ev_enum = EvidenceType.coerce(ev_type_str)
        except Exception:
            ev_enum = EvidenceType.REASONING

        weight = active_weights.get(perspective.role, perspective.base_weight)

        # Get historical accuracy and calculate calibration factor
        calibration_factor = CouncilCalibration.get_calibration_factor(perspective.role)
        calibrated_confidence = confidence * calibration_factor

        # Get judged / correct totals for logging
        conn = _connect()
        try:
            row = conn.execute(
                """
                SELECT COUNT(*) as judged,
                       SUM(case when prediction_correct = 1 then 1 else 0 end) as correct
                FROM agent_accuracy_history
                WHERE agent_name = ? AND prediction_correct IS NOT NULL
                """,
                (perspective.role,)
            ).fetchone()
            judged = row["judged"] if row else 0
            correct = row["correct"] if row and row["correct"] is not None else 0
        except Exception:
            judged = 0
            correct = 0
        finally:
            conn.close()

        vote_weight = weight * confidence * calibration_factor * ev_enum.multiplier

        ao = AgentOutput(
            agent=perspective.role,
            decision=decision_enum,
            confidence=confidence,
            evidence=(ev_enum,),
            recommendations=(
                Recommendation(
                    source=perspective.role,
                    message=rationale,
                    weight=weight,
                ),
            ) if rationale else (),
            source_id=f"council_{perspective.role.lower()}",
            rationale=rationale,
        )

        vote_rec = {
            "perspective": perspective.role,
            "vote": decision_enum.value,
            "confidence": confidence,
            "calibrated_confidence": calibrated_confidence,
            "calibration_factor": calibration_factor,
            "historical_judged": judged,
            "historical_correct": correct,
            "evidence_type": ev_enum.value,
            "rationale": rationale,
            "risks": risks,
            "benefits": benefits,
            "vote_weight": round(vote_weight, 4),
            "evidence_refs": verified_refs,
        }
        return ao, vote_rec

    # ──────────────────────────────────────────────────────────────────────────
    # Auditor adversarial pass
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def _run_auditor(
        cls,
        question: str,
        outputs: list[Any],
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        """Run the Auditor's adversarial critique pass.

        Returns (list[CriticFinding], list[dict]) for ledger and engine injection.
        Never raises — audit failure is non-blocking.
        """
        from backend.core.consensus_engine import CriticFinding, FindingCategory
        from backend.core.model_router import ask_model

        # Summarise other perspectives for the Auditor
        summary_rows: list[str] = []
        for ao in outputs:
            summary_rows.append(
                f"- {ao.agent}: {ao.decision.value} "
                f"(confidence={ao.confidence:.2f}) — {ao.rationale or '(no rationale)'}"
            )
        perspectives_summary = "\n".join(summary_rows) or "(no perspectives)"

        prompt = _AUDITOR_PROMPT.format(
            question=question,
            perspectives_summary=perspectives_summary,
        )

        findings_raw: list[dict[str, Any]] = []
        try:
            raw = ask_model(prompt, role="fast", system=_AUDITOR_SYSTEM)
            parsed = _parse_structured_json(raw)
            if parsed and isinstance(parsed.get("findings"), list):
                findings_raw = parsed["findings"]
        except Exception:
            pass

        critic_findings: list[CriticFinding] = []
        ledger_findings: list[dict[str, Any]] = []

        for f in findings_raw:
            if not isinstance(f, dict):
                continue
            cat_str = str(f.get("category", "advisory")).lower()
            desc = str(f.get("description", "")).strip()
            if not desc:
                continue
            try:
                category = FindingCategory.coerce(cat_str)
            except Exception:
                category = FindingCategory.ADVISORY

            cf = CriticFinding(
                source="Auditor",
                category=category,
                description=desc,
            )
            critic_findings.append(cf)
            ledger_findings.append({
                "finding_category": category.value,
                "description": desc,
            })

        return critic_findings, ledger_findings

    # ──────────────────────────────────────────────────────────────────────────
    # Integration call sites
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _maybe_submit_governance(
        decision: Any,
        question: str,
        question_type: str,
        context: dict[str, Any],
    ) -> str | None:
        """Submit to SelfImprovementGovernance if APPROVED + requires_human_approval."""
        from backend.core.consensus_engine import ConsensusStatus
        if decision.status is not ConsensusStatus.APPROVED:
            return None
        if not decision.requires_human_approval:
            return None
        try:
            from backend.core.self_improvement_governance import (
                ArchitecturalProposal, SelfImprovementGovernance,
            )
            proposal = ArchitecturalProposal(
                proposal_id=str(uuid.uuid4()),
                title=f"Council-approved: {question[:80]}",
                source="council",
                source_id=None,
                affected_modules=context.get("affected_modules", [question_type]),
                proposal_text=(
                    decision.selected.message
                    if decision.selected else question
                ),
                benchmark_confirmed=context.get("benchmark_confirmed", False),
                created_at=time.time(),
            )
            gate = SelfImprovementGovernance.submit(proposal)
            return proposal.proposal_id
        except Exception:
            return None

    @staticmethod
    def _record_to_strategic_memory(
        decision_id: str,
        question: str,
        question_type: str,
        decision: Any,
        gov_proposal_id: str | None,
    ) -> str | None:
        """Write council consensus to StrategicMemory."""
        try:
            from backend.core.strategic_memory import StrategicMemory
            StrategicMemory.record_decision(
                decision=f"Council deliberated: {question[:100]}",
                context=(
                    f"Decision ID: {decision_id}. "
                    f"Question type: {question_type}. "
                    f"Consensus: {decision.status.value}. "
                    f"Approve mass: {decision.approve_mass:.2f}, "
                    f"Reject mass: {decision.reject_mass:.2f}."
                    + (f" Governance proposal: {gov_proposal_id}." if gov_proposal_id else "")
                ),
                rationale=(
                    (decision.selected.message if decision.selected
                     else "No recommendation selected.") +
                    " Reasons: " + "; ".join(decision.reasons[:3])
                ),
                alternatives=[r for r in decision.reasons if r],
                created_by="council_session",
            )
            return None
        except Exception:
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def _persist(
        cls,
        *,
        decision_id: str,
        question: str,
        question_type: str,
        context_json: str,
        created_at: float,
        completed_at: float,
        decision: Any,
        vote_records: list[dict[str, Any]],
        audit_findings: list[dict[str, Any]],
        governance_proposal_id: str | None,
        strategic_decision_id: str | None,
        active_mode_profile: str,
        mode_set_by: str,
        arbiter_findings_json: str,
        dissent_json: str,
    ) -> None:
        selected_text = decision.selected.message if decision.selected else None
        margin = round(decision.margin, 4) if decision.margin is not None else None

        with _WRITE_LOCK:
            conn = _connect()
            try:
                conn.execute(
                    """
                    INSERT INTO council_decisions
                        (id, question, question_type, context_json,
                         created_at, completed_at, consensus_status, requires_human,
                         selected_recommendation, approve_mass, reject_mass, margin,
                         reasons_json, governance_proposal_id, strategic_decision_id,
                         active_mode_profile, mode_set_by, arbiter_findings_json, dissent_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        decision_id, question, question_type, context_json,
                        created_at, completed_at, decision.status.value,
                        1 if decision.requires_human_approval else 0,
                        selected_text,
                        decision.approve_mass, decision.reject_mass, margin,
                        json.dumps(decision.reasons),
                        governance_proposal_id, strategic_decision_id,
                        active_mode_profile, mode_set_by, arbiter_findings_json, dissent_json,
                    ),
                )
                now = time.time()
                for vr in vote_records:
                    conn.execute(
                        """
                        INSERT INTO council_votes
                            (decision_id, perspective, vote, confidence, evidence_type,
                             rationale, risks_json, benefits_json, vote_weight, logged_at,
                             calibrated_confidence, evidence_refs_json, calibration_factor)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            decision_id,
                            vr["perspective"],
                            vr["vote"],
                            vr["confidence"],
                            vr.get("evidence_type", "reasoning"),
                            vr.get("rationale", ""),
                            json.dumps(vr.get("risks", [])),
                            json.dumps(vr.get("benefits", [])),
                            vr.get("vote_weight", 0.0),
                            now,
                            vr.get("calibrated_confidence"),
                            json.dumps(vr.get("evidence_refs", [])),
                            vr.get("calibration_factor", 1.0),
                        ),
                    )
                # Dissent archiving
                dissent_records = json.loads(dissent_json)
                for dr in dissent_records:
                    conn.execute(
                        """
                        INSERT INTO council_dissent_archive
                            (dissent_id, decision_id, perspective, vote, confidence,
                             evidence_type, rationale, risks_json, evidence_refs_json, archived_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            dr["dissent_id"],
                            decision_id,
                            dr["perspective"],
                            dr["vote"],
                            dr["confidence"],
                            dr["evidence_type"],
                            dr["rationale"],
                            json.dumps(dr["risks"]),
                            json.dumps(dr["evidence_refs"]),
                            now,
                        ),
                    )
                for af in audit_findings:
                    conn.execute(
                        """
                        INSERT INTO council_audit_findings
                            (decision_id, finding_category, description, logged_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            decision_id,
                            af["finding_category"],
                            af["description"],
                            now,
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

    # ──────────────────────────────────────────────────────────────────────────
    # Query API
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def get_decision(cls, decision_id: str) -> dict[str, Any] | None:
        _ensure_schema()
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM council_decisions WHERE id = ?", (decision_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d["reasons"] = json.loads(d.pop("reasons_json", "[]"))
            d["votes"] = cls._votes_for(conn, decision_id)
            d["audit_findings"] = cls._findings_for(conn, decision_id)
            
            d["mode_profile"] = d.get("active_mode_profile", "system_default")
            d["arbiter_findings"] = json.loads(d.pop("arbiter_findings_json", "[]"))
            d["dissent"] = json.loads(d.pop("dissent_json", "[]"))
            
            cal_snap = {}
            for v in d["votes"]:
                cal_snap[v["perspective"]] = {
                    "calibration_factor": v.get("calibration_factor", 1.0)
                }
            d["calibration_snapshot"] = cal_snap
            return d
        finally:
            conn.close()

    @classmethod
    def list_decisions(cls, limit: int = 50) -> list[dict[str, Any]]:
        _ensure_schema()
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM council_decisions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d["reasons"] = json.loads(d.pop("reasons_json", "[]"))
                d["mode_profile"] = d.get("active_mode_profile", "system_default")
                results.append(d)
            return results
        finally:
            conn.close()

    @classmethod
    def record_outcome(
        cls,
        decision_id: str,
        outcome: str,
        outcome_score: float,
        predicted_success: float | None = None,
        actual_success: float | None = None,
        notes: str = "",
    ) -> None:
        """Record Arena verification outcome for benchmarking."""
        _ensure_schema()
        eff_actual = actual_success
        if eff_actual is None:
            eff_actual = 1.0 if outcome == "correct" else 0.0
            
        with _WRITE_LOCK:
            conn = _connect()
            try:
                decision_row = conn.execute(
                    "SELECT consensus_status, approve_mass, reject_mass FROM council_decisions WHERE id = ?",
                    (decision_id,)
                ).fetchone()
                
                if not decision_row:
                    conn.execute(
                        """
                        INSERT INTO council_benchmarks
                            (decision_id, outcome, outcome_score, evaluated_at, predicted_success, actual_success, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (decision_id, outcome, float(outcome_score), time.time(), predicted_success, eff_actual, notes),
                    )
                    conn.commit()
                    return
                
                status = decision_row["consensus_status"]
                approve_mass = decision_row["approve_mass"] or 0.0
                reject_mass = decision_row["reject_mass"] or 0.0
                
                eff_predicted = predicted_success
                if eff_predicted is None:
                    total_mass = approve_mass + reject_mass
                    eff_predicted = approve_mass / total_mass if total_mass > 0 else 0.5
                
                conn.execute(
                    """
                    INSERT INTO council_benchmarks
                        (decision_id, outcome, outcome_score, evaluated_at, predicted_success, actual_success, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (decision_id, outcome, float(outcome_score), time.time(), eff_predicted, eff_actual, notes),
                )
                
                votes = conn.execute(
                    "SELECT perspective, vote FROM council_votes WHERE decision_id = ?",
                    (decision_id,)
                ).fetchall()
                
                actual_bool = eff_actual >= 0.5
                outcome_id = str(uuid.uuid4())
                
                for v in votes:
                    agent = v["perspective"]
                    vote = v["vote"]
                    
                    prediction_correct = None
                    if status == "approved":
                        if vote == "APPROVE":
                            prediction_correct = 1 if actual_bool else 0
                        elif vote == "REJECT":
                            prediction_correct = 0 if actual_bool else 1
                    elif status == "rejected":
                        if vote == "REJECT":
                            prediction_correct = 0 if actual_bool else 1
                        elif vote == "APPROVE":
                            prediction_correct = 1 if actual_bool else 0
                            
                    if prediction_correct is not None:
                        conn.execute(
                            """
                            INSERT INTO agent_accuracy_history
                                (history_id, agent_name, session_id, outcome_id, predicted_success, actual_success, prediction_correct, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                str(uuid.uuid4()),
                                agent,
                                decision_id,
                                outcome_id,
                                eff_predicted,
                                eff_actual,
                                prediction_correct,
                                time.time(),
                            )
                        )
                
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _votes_for(conn: sqlite3.Connection, decision_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT * FROM council_votes WHERE decision_id = ? ORDER BY logged_at",
            (decision_id,),
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["risks"] = json.loads(d.pop("risks_json", "[]"))
            d["benefits"] = json.loads(d.pop("benefits_json", "[]"))
            d["evidence_refs"] = json.loads(d.pop("evidence_refs_json", "[]"))
            results.append(d)
        return results

    @staticmethod
    def _findings_for(conn: sqlite3.Connection, decision_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT * FROM council_audit_findings WHERE decision_id = ? ORDER BY logged_at",
            (decision_id,),
        ).fetchall()
        return [dict(row) for row in rows]


# ─────────────────────────────────────────────────────────────────────────────
# CouncilPerformanceReport
# ─────────────────────────────────────────────────────────────────────────────

class CouncilPerformanceReport:
    """Compares council decisions against Arena outcomes."""

    @classmethod
    def generate(cls) -> dict[str, Any]:
        """Return comparative performance statistics from the decision ledger."""
        _ensure_schema()
        conn = _connect()
        try:
            total = conn.execute("SELECT COUNT(*) FROM council_decisions").fetchone()[0]
            approved = conn.execute(
                "SELECT COUNT(*) FROM council_decisions WHERE consensus_status = 'approved'"
            ).fetchone()[0]
            rejected = conn.execute(
                "SELECT COUNT(*) FROM council_decisions WHERE consensus_status = 'rejected'"
            ).fetchone()[0]
            escalated = conn.execute(
                "SELECT COUNT(*) FROM council_decisions WHERE consensus_status = 'escalate'"
            ).fetchone()[0]

            benchmarked = conn.execute(
                "SELECT COUNT(*) FROM council_benchmarks"
            ).fetchone()[0]
            avg_score_row = conn.execute(
                "SELECT AVG(outcome_score) FROM council_benchmarks WHERE outcome_score IS NOT NULL"
            ).fetchone()
            avg_score = float(avg_score_row[0]) if avg_score_row[0] is not None else None

            correct_row = conn.execute(
                "SELECT COUNT(*) FROM council_benchmarks WHERE outcome = 'correct'"
            ).fetchone()
            correct = correct_row[0] if correct_row else 0

            by_type_rows = conn.execute(
                "SELECT question_type, COUNT(*) AS cnt, AVG(approve_mass) AS avg_approve "
                "FROM council_decisions GROUP BY question_type"
            ).fetchall()
            by_type = [
                {
                    "question_type": r["question_type"],
                    "count": r["cnt"],
                    "avg_approve_mass": round(r["avg_approve"] or 0.0, 4),
                }
                for r in by_type_rows
            ]

            calibration = {}
            for p in COUNCIL_ROSTER:
                if p.is_auditor:
                    continue
                row = conn.execute(
                    """
                    SELECT COUNT(*) as judged,
                           SUM(case when prediction_correct = 1 then 1 else 0 end) as correct
                    FROM agent_accuracy_history
                    WHERE agent_name = ? AND prediction_correct IS NOT NULL
                    """,
                    (p.role,)
                ).fetchone()
                judged = row["judged"] if row else 0
                correct_count = row["correct"] if row and row["correct"] is not None else 0
                factor = 1.0 if judged < 3 else float(correct_count) / float(judged)
                calibration[p.role] = {
                    "judged": judged,
                    "correct": correct_count,
                    "calibration_factor": round(max(0.25, min(1.0, factor)), 4)
                }

            return {
                "total_deliberations": total,
                "approved": approved,
                "rejected": rejected,
                "escalated": escalated,
                "benchmarked_outcomes": benchmarked,
                "avg_outcome_score": round(avg_score, 4) if avg_score is not None else None,
                "correct_outcomes": correct,
                "accuracy": round(correct / benchmarked, 4) if benchmarked > 0 else None,
                "by_question_type": by_type,
                "calibration": calibration,
            }
        finally:
            conn.close()
