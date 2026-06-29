"""Human Conversation Engine (HCE) — Social Cortex of Kattappa.

Position in cognitive stack:
    User → HCE → Memory Fabric → Goal System → PPM → Simulation Sandbox → Execution

Design philosophy:
    Not: Question → Answer
    But: Remember → Understand → Reflect → Respond

The HCE treats every interaction as a chapter in a continuous relationship,
never as an isolated session. It is a:
    * Relationship Manager
    * Context Synthesizer
    * Narrative Generator
    * Text-Signal Interpreter (never an emotional authority)

Constitutional guarantees (HCEConstitution):
    Rule 1 — Cannot create goals (proposes intents only)
    Rule 2 — Cannot write memory (produces candidates only)
    Rule 3 — Empathy cannot override truth (outputs friction signals, not emotional claims)
    Rule 4 — Personality cannot override safety (core constants frozen; posture never accumulated)
    Rule 5 — Relationship cannot override user intent (metrics feed retrieval only)
    Rule 6 — No relationship optimization (objective: truthful assistance, not user attachment)

Storage: shares the existing kattappa.db (load_config().sqlite_path).
         Nine new tables prefixed hce_. No new database file.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.core.config import load_config
from backend.core.logger import log_event


# ---------------------------------------------------------------------------
# Constitutional safety object
# ---------------------------------------------------------------------------

class HCEConstitution:
    """Six hardcoded safety rules. Not configurable, not overridable."""

    # Rule 1
    HCE_CANNOT_CREATE_GOALS: bool = True
    HCE_CANNOT_CREATE_GOALS_DESCRIPTION: str = (
        "HCE cannot call GoalMemory.create_goal(). "
        "It produces ProposedIntent objects that require user confirmation."
    )

    # Rule 2
    HCE_CANNOT_WRITE_MEMORY: bool = True
    HCE_CANNOT_WRITE_MEMORY_DESCRIPTION: str = (
        "HCE cannot write directly to HumanMemoryStore, EpisodicMemory, or RelationshipMemory. "
        "It produces MemoryCandidate objects subject to MemoryGovernance gates."
    )

    # Rule 3
    HCE_EMPATHY_CANNOT_OVERRIDE_TRUTH: bool = True
    HCE_EMPATHY_CANNOT_OVERRIDE_TRUTH_DESCRIPTION: str = (
        "AcknowledgementEngine outputs friction_signal and ambiguity_score — "
        "properties of text, not claims about the human's internal state. "
        "Output: 'That sounds frustrating.' Never: 'You are frustrated.'"
    )

    # Rule 4
    HCE_PERSONALITY_CANNOT_OVERRIDE_SAFETY: bool = True
    HCE_PERSONALITY_CANNOT_OVERRIDE_SAFETY_DESCRIPTION: str = (
        "Core personality constants are frozen. Adaptive posture is derived fresh each chapter "
        "and never accumulated across chapters. No ratchet effect. No drift."
    )

    # Rule 5
    HCE_RELATIONSHIP_CANNOT_OVERRIDE_USER_INTENT: bool = True
    HCE_RELATIONSHIP_CANNOT_OVERRIDE_USER_INTENT_DESCRIPTION: str = (
        "Relationship health metrics (trust, continuity, understanding, helpfulness) "
        "influence memory retrieval priority only. They never influence approval, "
        "persuasion, goal acceptance, or execution authority."
    )

    # Rule 6
    HCE_NO_RELATIONSHIP_OPTIMIZATION: bool = True
    HCE_NO_RELATIONSHIP_OPTIMIZATION_DESCRIPTION: str = (
        "HCE is forbidden from optimizing for user attachment, dependence, conversation length, "
        "approval likelihood, or trust score growth. Objective: truthful assistance."
    )

    # Rule 7
    HCE_CAPABILITY_MUST_BE_VERIFIABLE: bool = True
    HCE_CAPABILITY_MUST_BE_VERIFIABLE_DESCRIPTION: str = (
        "Capability grows only when it remains verifiable. "
        "Every new autonomous behavior should be measurable, reproducible, and testable "
        "before it becomes part of Kattappa's permanent capabilities."
    )

    # Rule 8 (Eleventh Constitutional Law)
    HCE_REASON_BEFORE_ACTION: bool = True
    HCE_REASON_BEFORE_ACTION_DESCRIPTION: str = (
        "Reason before action. Every non-trivial action should be preceded "
        "by explicit understanding, evidence retrieval, planning, and risk evaluation. "
        "Execution is the final step of cognition, not the first."
    )

    # Rule 9 (Twelfth Constitutional Law)
    HCE_LAYERED_KNOWLEDGE: bool = True
    HCE_LAYERED_KNOWLEDGE_DESCRIPTION: str = (
        "Knowledge is layered, not singular. Kattappa should distinguish between "
        "observations (what happened), memories (what was recorded), beliefs (what is "
        "currently inferred), knowledge (what has been repeatedly verified), and wisdom "
        "(stable principles used to guide decisions)."
    )

    @classmethod
    def to_dict(cls) -> dict[str, Any]:
        return {
            "rule_1": {
                "name": "HCE_CANNOT_CREATE_GOALS",
                "enforced": cls.HCE_CANNOT_CREATE_GOALS,
                "description": cls.HCE_CANNOT_CREATE_GOALS_DESCRIPTION,
            },
            "rule_2": {
                "name": "HCE_CANNOT_WRITE_MEMORY",
                "enforced": cls.HCE_CANNOT_WRITE_MEMORY,
                "description": cls.HCE_CANNOT_WRITE_MEMORY_DESCRIPTION,
            },
            "rule_3": {
                "name": "HCE_EMPATHY_CANNOT_OVERRIDE_TRUTH",
                "enforced": cls.HCE_EMPATHY_CANNOT_OVERRIDE_TRUTH,
                "description": cls.HCE_EMPATHY_CANNOT_OVERRIDE_TRUTH_DESCRIPTION,
            },
            "rule_4": {
                "name": "HCE_PERSONALITY_CANNOT_OVERRIDE_SAFETY",
                "enforced": cls.HCE_PERSONALITY_CANNOT_OVERRIDE_SAFETY,
                "description": cls.HCE_PERSONALITY_CANNOT_OVERRIDE_SAFETY_DESCRIPTION,
            },
            "rule_5": {
                "name": "HCE_RELATIONSHIP_CANNOT_OVERRIDE_USER_INTENT",
                "enforced": cls.HCE_RELATIONSHIP_CANNOT_OVERRIDE_USER_INTENT,
                "description": cls.HCE_RELATIONSHIP_CANNOT_OVERRIDE_USER_INTENT_DESCRIPTION,
            },
            "rule_6": {
                "name": "HCE_NO_RELATIONSHIP_OPTIMIZATION",
                "enforced": cls.HCE_NO_RELATIONSHIP_OPTIMIZATION,
                "description": cls.HCE_NO_RELATIONSHIP_OPTIMIZATION_DESCRIPTION,
            },
            "rule_7": {
                "name": "HCE_CAPABILITY_MUST_BE_VERIFIABLE",
                "enforced": cls.HCE_CAPABILITY_MUST_BE_VERIFIABLE,
                "description": cls.HCE_CAPABILITY_MUST_BE_VERIFIABLE_DESCRIPTION,
            },
            "rule_8": {
                "name": "HCE_REASON_BEFORE_ACTION",
                "enforced": cls.HCE_REASON_BEFORE_ACTION,
                "description": cls.HCE_REASON_BEFORE_ACTION_DESCRIPTION,
            },
            "rule_9": {
                "name": "HCE_LAYERED_KNOWLEDGE",
                "enforced": cls.HCE_LAYERED_KNOWLEDGE,
                "description": cls.HCE_LAYERED_KNOWLEDGE_DESCRIPTION,
            },
        }


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RelationshipState(str, Enum):
    """Operational collaboration state — not emotional profiling.
    Drives context retrieval priorities.
    """
    LEARNING_MODE      = "LEARNING_MODE"       # absorbing new domain knowledge
    BUILDING_MODE      = "BUILDING_MODE"       # active project construction
    DEBUGGING_MODE     = "DEBUGGING_MODE"      # diagnosing failures
    PLANNING_MODE      = "PLANNING_MODE"       # architectural / strategic thinking
    EXPLORATION_MODE   = "EXPLORATION_MODE"    # open-ended discovery


class PersonalityPosture(str, Enum):
    """Derived fresh per chapter from RelationshipState + project context.
    Never accumulated. No ratchet effect.
    """
    TECHNICAL_EXECUTOR     = "TECHNICAL_EXECUTOR"      # precise, implementation-first
    STRATEGIC_COLLABORATOR = "STRATEGIC_COLLABORATOR"  # architecture-first, long-arc
    ACADEMIC_TEACHER       = "ACADEMIC_TEACHER"        # conceptual, step-by-step
    PLANNER                = "PLANNER"                 # timeline, milestone-focused


class MemoryTier(str, Enum):
    EPISODIC     = "EPISODIC"     # discrete historical checkpoints
    SEMANTIC     = "SEMANTIC"     # stable facts, preferences
    RELATIONSHIP = "RELATIONSHIP" # interpersonal interaction patterns


class IntentStatus(str, Enum):
    PENDING_USER_CONFIRMATION = "PENDING_USER_CONFIRMATION"
    COMMITTED_TO_GOAL_SYSTEM  = "COMMITTED_TO_GOAL_SYSTEM"
    REJECTED                  = "REJECTED"


class GovernanceStatus(str, Enum):
    PENDING   = "PENDING"
    COMMITTED = "COMMITTED"
    REJECTED  = "REJECTED"


class ContradictionResolution(str, Enum):
    CONFLICTED = "CONFLICTED"   # both facts held simultaneously; time-bound
    RESOLVED   = "RESOLVED"     # user explicitly resolved
    TIME_BOUND = "TIME_BOUND"   # valid at different points in time


# ---------------------------------------------------------------------------
# Core data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReflectionSummary:
    """Internal pre-response reasoning trace. Never shown verbatim to user."""
    intent_deduction: str
    recalled_context: list[dict[str, Any]]
    personality_posture: PersonalityPosture
    relationship_state: RelationshipState
    friction_signal: float         # [0,1] — property of the text, not the human
    ambiguity_score: float         # [0,1]
    blocker_density: float         # [0,1] — fraction of recalled items that are blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_deduction": self.intent_deduction,
            "recalled_context_count": len(self.recalled_context),
            "personality_posture": self.personality_posture.value,
            "relationship_state": self.relationship_state.value,
            "friction_signal": round(self.friction_signal, 3),
            "ambiguity_score": round(self.ambiguity_score, 3),
            "blocker_density": round(self.blocker_density, 3),
        }


@dataclass
class MemoryCandidate:
    """A proposed memory record. Never written directly to any memory store."""
    candidate_id: str
    utterance_id: str
    memory_tier: MemoryTier
    extracted_fact: str
    confidence: float
    decay_status: str = "ACTIVE"
    governance_status: GovernanceStatus = GovernanceStatus.PENDING
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "utterance_id": self.utterance_id,
            "memory_tier": self.memory_tier.value,
            "extracted_fact": self.extracted_fact,
            "confidence": round(self.confidence, 3),
            "decay_status": self.decay_status,
            "governance_status": self.governance_status.value,
            "created_at": self.created_at,
        }


@dataclass
class ProposedIntent:
    """A proposed goal extracted from conversation. Awaits user confirmation."""
    proposal_id: str
    utterance_id: str
    inferred_goal_structure: dict[str, Any]
    status: IntentStatus = IntentStatus.PENDING_USER_CONFIRMATION
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "utterance_id": self.utterance_id,
            "inferred_goal_structure": self.inferred_goal_structure,
            "status": self.status.value,
            "created_at": self.created_at,
        }


@dataclass
class ConversationContext:
    """Assembled context snapshot used for response composition."""
    active_goals: list[dict[str, Any]] = field(default_factory=list)
    active_projects: list[dict[str, Any]] = field(default_factory=list)
    recalled_memories: list[dict[str, Any]] = field(default_factory=list)
    relationship_history: list[dict[str, Any]] = field(default_factory=list)
    preferences: list[dict[str, Any]] = field(default_factory=list)
    relationship_state: RelationshipState = RelationshipState.BUILDING_MODE
    chapter_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_goals": self.active_goals,
            "active_projects": self.active_projects,
            "recalled_memories": self.recalled_memories,
            "relationship_history": self.relationship_history,
            "preferences": self.preferences,
            "relationship_state": self.relationship_state.value,
            "chapter_id": self.chapter_id,
        }


@dataclass
class HCEResponse:
    """Full response package from HCE.process(). Read-only contract.

    authorized_to_create_goals and authorized_to_write_memory are hardcoded False
    in to_dict() regardless of internal state — Rules 1 & 2.
    """
    utterance_id: str
    chapter_id: str
    relationship_id: str
    reflection: ReflectionSummary
    conversation_context: ConversationContext
    memory_candidates: list[MemoryCandidate] = field(default_factory=list)
    proposed_intents: list[ProposedIntent] = field(default_factory=list)
    contradictions_detected: list[dict[str, Any]] = field(default_factory=list)
    curiosity_questions: list[str] = field(default_factory=list)
    narrative_framing: str = ""
    integrity_flag: bool = False   # True if IntellectualIntegrityMonitor fires
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "utterance_id": self.utterance_id,
            "chapter_id": self.chapter_id,
            "relationship_id": self.relationship_id,
            "reflection": self.reflection.to_dict(),
            "conversation_context": self.conversation_context.to_dict(),
            "memory_candidates": [c.to_dict() for c in self.memory_candidates],
            "proposed_intents": [p.to_dict() for p in self.proposed_intents],
            "contradictions_detected": self.contradictions_detected,
            "curiosity_questions": self.curiosity_questions,
            "narrative_framing": self.narrative_framing,
            "integrity_flag": self.integrity_flag,
            "constitution_enforced": True,
            # Rules 1 & 2: hardcoded — never read from internal state
            "authorized_to_create_goals": False,
            "authorized_to_write_memory": False,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# SQLite storage (uses shared kattappa.db)
# ---------------------------------------------------------------------------

class HCEStore:
    """Single-writer SQLite store for all HCE conversation structure tables."""

    _lock = threading.RLock()
    _schema_ensured: bool = False

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        with cls._lock:
            if not cls._schema_ensured:
                cls._ensure_schema(conn)
                cls._schema_ensured = True
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            -- Relationship anchor (one per user entity)
            CREATE TABLE IF NOT EXISTS hce_relationships (
                relationship_id  TEXT PRIMARY KEY,
                user_entity_id   TEXT NOT NULL,
                display_name     TEXT NOT NULL,
                created_at       REAL NOT NULL,
                total_chapters   INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_hce_rel_entity
                ON hce_relationships(user_entity_id);

            -- Chapters: contextually contiguous interaction sequences
            CREATE TABLE IF NOT EXISTS hce_chapters (
                chapter_id                TEXT PRIMARY KEY,
                relationship_id           TEXT NOT NULL,
                opened_at                 REAL NOT NULL,
                closed_at                 REAL,
                relationship_state        TEXT NOT NULL DEFAULT 'BUILDING_MODE',
                chapter_summary_narrative TEXT,
                FOREIGN KEY (relationship_id)
                    REFERENCES hce_relationships(relationship_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_hce_chapter_rel
                ON hce_chapters(relationship_id);

            -- Utterances: one per (user_turn + system_turn) pair
            CREATE TABLE IF NOT EXISTS hce_utterances (
                utterance_id        TEXT PRIMARY KEY,
                chapter_id          TEXT NOT NULL,
                timestamp           REAL NOT NULL,
                user_message        TEXT NOT NULL,
                system_response     TEXT NOT NULL DEFAULT '',
                input_token_count   INTEGER DEFAULT 0,
                output_token_count  INTEGER DEFAULT 0,
                FOREIGN KEY (chapter_id)
                    REFERENCES hce_chapters(chapter_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_hce_utt_chapter
                ON hce_utterances(chapter_id);

            -- Reflection log: pre-response internal reasoning trace
            CREATE TABLE IF NOT EXISTS hce_reflections (
                reflection_id               TEXT PRIMARY KEY,
                utterance_id                TEXT NOT NULL UNIQUE,
                intent_deduction            TEXT NOT NULL,
                epistemic_context_recalled  TEXT NOT NULL DEFAULT '[]',
                personality_posture         TEXT NOT NULL DEFAULT 'TECHNICAL_EXECUTOR',
                relationship_state          TEXT NOT NULL DEFAULT 'BUILDING_MODE',
                friction_signal             REAL NOT NULL DEFAULT 0.0,
                ambiguity_score             REAL NOT NULL DEFAULT 0.0,
                blocker_density             REAL NOT NULL DEFAULT 0.0,
                curiosity_questions_asked   INTEGER DEFAULT 0,
                created_at                  REAL NOT NULL,
                FOREIGN KEY (utterance_id)
                    REFERENCES hce_utterances(utterance_id) ON DELETE CASCADE
            );

            -- Memory candidates: proposed only — never direct writes to memory stores
            CREATE TABLE IF NOT EXISTS hce_memory_candidates (
                candidate_id        TEXT PRIMARY KEY,
                utterance_id        TEXT NOT NULL,
                memory_tier         TEXT NOT NULL,
                extracted_fact      TEXT NOT NULL,
                confidence          REAL NOT NULL,
                decay_status        TEXT NOT NULL DEFAULT 'ACTIVE',
                governance_status   TEXT NOT NULL DEFAULT 'PENDING',
                created_at          REAL NOT NULL,
                FOREIGN KEY (utterance_id)
                    REFERENCES hce_utterances(utterance_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_hce_cand_utt
                ON hce_memory_candidates(utterance_id);
            CREATE INDEX IF NOT EXISTS idx_hce_cand_status
                ON hce_memory_candidates(governance_status);

            -- Proposed intents: extracted goal proposals — pending confirmation
            CREATE TABLE IF NOT EXISTS hce_proposed_intents (
                proposal_id             TEXT PRIMARY KEY,
                utterance_id            TEXT NOT NULL,
                inferred_goal_structure TEXT NOT NULL,
                status                  TEXT NOT NULL DEFAULT 'PENDING_USER_CONFIRMATION',
                created_at              REAL NOT NULL,
                FOREIGN KEY (utterance_id)
                    REFERENCES hce_utterances(utterance_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_hce_intent_status
                ON hce_proposed_intents(status);

            -- Relationship health metrics (retrieval-priority use only — never behavioral)
            CREATE TABLE IF NOT EXISTS hce_relationship_metrics (
                relationship_id      TEXT PRIMARY KEY,
                trust_score          REAL NOT NULL DEFAULT 50.0,
                continuity_score     REAL NOT NULL DEFAULT 50.0,
                understanding_score  REAL NOT NULL DEFAULT 50.0,
                helpfulness_velocity REAL NOT NULL DEFAULT 50.0,
                correction_rate      REAL NOT NULL DEFAULT 0.0,
                disagreement_rate    REAL NOT NULL DEFAULT 0.0,
                user_repetition_rate REAL NOT NULL DEFAULT 0.0,
                total_utterances     INTEGER DEFAULT 0,
                updated_at           REAL NOT NULL,
                FOREIGN KEY (relationship_id)
                    REFERENCES hce_relationships(relationship_id) ON DELETE CASCADE
            );

            -- Contradiction log: time-bound conflicting facts
            CREATE TABLE IF NOT EXISTS hce_contradictions (
                contradiction_id    TEXT PRIMARY KEY,
                entity_id           TEXT NOT NULL,
                fact_a              TEXT NOT NULL,
                fact_b              TEXT NOT NULL,
                detected_at         REAL NOT NULL,
                resolution_status   TEXT NOT NULL DEFAULT 'CONFLICTED'
            );
            CREATE INDEX IF NOT EXISTS idx_hce_contra_entity
                ON hce_contradictions(entity_id);

            -- Narrative arcs: long-term story threads (auto-detected)
            CREATE TABLE IF NOT EXISTS hce_narrative_arcs (
                arc_id           TEXT PRIMARY KEY,
                relationship_id  TEXT NOT NULL,
                arc_name         TEXT NOT NULL,
                arc_summary      TEXT NOT NULL DEFAULT '',
                chapter_ids      TEXT NOT NULL DEFAULT '[]',
                updated_at       REAL NOT NULL,
                FOREIGN KEY (relationship_id)
                    REFERENCES hce_relationships(relationship_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_hce_arc_rel
                ON hce_narrative_arcs(relationship_id);
        """)
        conn.commit()

    # ----- Relationships -----

    @classmethod
    def create_relationship(
        cls, user_entity_id: str, display_name: str
    ) -> dict[str, Any]:
        rel_id = str(uuid.uuid4())
        now = time.time()
        with cls._lock:
            conn = cls._get_conn()
            try:
                # Idempotent: return existing if already present
                row = conn.execute(
                    "SELECT * FROM hce_relationships WHERE user_entity_id = ?",
                    (user_entity_id,),
                ).fetchone()
                if row:
                    return dict(row)
                conn.execute(
                    "INSERT INTO hce_relationships "
                    "(relationship_id, user_entity_id, display_name, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (rel_id, user_entity_id, display_name, now),
                )
                # Seed metrics row
                conn.execute(
                    "INSERT OR IGNORE INTO hce_relationship_metrics "
                    "(relationship_id, updated_at) VALUES (?, ?)",
                    (rel_id, now),
                )
                conn.commit()
                return {
                    "relationship_id": rel_id,
                    "user_entity_id": user_entity_id,
                    "display_name": display_name,
                    "created_at": now,
                    "total_chapters": 0,
                }
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_relationship(cls, relationship_id: str) -> dict[str, Any] | None:
        conn = cls._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM hce_relationships WHERE relationship_id = ?",
                (relationship_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @classmethod
    def get_relationship_by_entity(cls, user_entity_id: str) -> dict[str, Any] | None:
        conn = cls._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM hce_relationships WHERE user_entity_id = ?",
                (user_entity_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ----- Chapters -----

    @classmethod
    def open_chapter(
        cls,
        relationship_id: str,
        relationship_state: RelationshipState = RelationshipState.BUILDING_MODE,
    ) -> dict[str, Any]:
        chapter_id = str(uuid.uuid4())
        now = time.time()
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute(
                    "INSERT INTO hce_chapters "
                    "(chapter_id, relationship_id, opened_at, relationship_state) "
                    "VALUES (?, ?, ?, ?)",
                    (chapter_id, relationship_id, now, relationship_state.value),
                )
                conn.execute(
                    "UPDATE hce_relationships "
                    "SET total_chapters = total_chapters + 1 "
                    "WHERE relationship_id = ?",
                    (relationship_id,),
                )
                conn.commit()
                return {
                    "chapter_id": chapter_id,
                    "relationship_id": relationship_id,
                    "opened_at": now,
                    "relationship_state": relationship_state.value,
                    "closed_at": None,
                }
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def close_chapter(cls, chapter_id: str, summary_narrative: str = "") -> bool:
        now = time.time()
        with cls._lock:
            conn = cls._get_conn()
            try:
                cur = conn.execute(
                    "UPDATE hce_chapters "
                    "SET closed_at = ?, chapter_summary_narrative = ? "
                    "WHERE chapter_id = ? AND closed_at IS NULL",
                    (now, summary_narrative, chapter_id),
                )
                conn.commit()
                return cur.rowcount > 0
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_active_chapter(cls, relationship_id: str) -> dict[str, Any] | None:
        conn = cls._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM hce_chapters "
                "WHERE relationship_id = ? AND closed_at IS NULL "
                "ORDER BY opened_at DESC LIMIT 1",
                (relationship_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @classmethod
    def get_chapter(cls, chapter_id: str) -> dict[str, Any] | None:
        conn = cls._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM hce_chapters WHERE chapter_id = ?", (chapter_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ----- Utterances -----

    @classmethod
    def create_utterance(
        cls,
        chapter_id: str,
        user_message: str,
    ) -> str:
        utterance_id = str(uuid.uuid4())
        now = time.time()
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute(
                    "INSERT INTO hce_utterances "
                    "(utterance_id, chapter_id, timestamp, user_message) "
                    "VALUES (?, ?, ?, ?)",
                    (utterance_id, chapter_id, now, user_message),
                )
                conn.commit()
                return utterance_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def finalize_utterance(
        cls, utterance_id: str, system_response: str,
        input_tokens: int = 0, output_tokens: int = 0
    ) -> None:
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute(
                    "UPDATE hce_utterances "
                    "SET system_response = ?, input_token_count = ?, output_token_count = ? "
                    "WHERE utterance_id = ?",
                    (system_response, input_tokens, output_tokens, utterance_id),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_recent_utterances(
        cls, chapter_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        conn = cls._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hce_utterances "
                "WHERE chapter_id = ? ORDER BY timestamp DESC LIMIT ?",
                (chapter_id, limit),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()

    # ----- Reflections -----

    @classmethod
    def log_reflection(
        cls,
        utterance_id: str,
        summary: ReflectionSummary,
        questions_asked: int = 0,
    ) -> str:
        reflection_id = str(uuid.uuid4())
        now = time.time()
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO hce_reflections "
                    "(reflection_id, utterance_id, intent_deduction, "
                    "epistemic_context_recalled, personality_posture, "
                    "relationship_state, friction_signal, ambiguity_score, "
                    "blocker_density, curiosity_questions_asked, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        reflection_id, utterance_id, summary.intent_deduction,
                        json.dumps([str(c) for c in summary.recalled_context]),
                        summary.personality_posture.value,
                        summary.relationship_state.value,
                        summary.friction_signal, summary.ambiguity_score,
                        summary.blocker_density, questions_asked, now,
                    ),
                )
                conn.commit()
                return reflection_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    # ----- Memory Candidates -----

    @classmethod
    def store_memory_candidate(cls, candidate: MemoryCandidate) -> None:
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute(
                    "INSERT INTO hce_memory_candidates "
                    "(candidate_id, utterance_id, memory_tier, extracted_fact, "
                    "confidence, decay_status, governance_status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        candidate.candidate_id, candidate.utterance_id,
                        candidate.memory_tier.value, candidate.extracted_fact,
                        candidate.confidence, candidate.decay_status,
                        candidate.governance_status.value, candidate.created_at,
                    ),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_memory_candidates(
        cls,
        governance_status: str = "PENDING",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        conn = cls._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hce_memory_candidates "
                "WHERE governance_status = ? ORDER BY created_at DESC LIMIT ?",
                (governance_status, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def update_candidate_status(
        cls, candidate_id: str, new_status: GovernanceStatus
    ) -> bool:
        with cls._lock:
            conn = cls._get_conn()
            try:
                cur = conn.execute(
                    "UPDATE hce_memory_candidates "
                    "SET governance_status = ? WHERE candidate_id = ?",
                    (new_status.value, candidate_id),
                )
                conn.commit()
                return cur.rowcount > 0
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    # ----- Proposed Intents -----

    @classmethod
    def store_proposed_intent(cls, intent: ProposedIntent) -> None:
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute(
                    "INSERT INTO hce_proposed_intents "
                    "(proposal_id, utterance_id, inferred_goal_structure, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        intent.proposal_id, intent.utterance_id,
                        json.dumps(intent.inferred_goal_structure),
                        intent.status.value, intent.created_at,
                    ),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_proposed_intents(
        cls, status: str = "PENDING_USER_CONFIRMATION", limit: int = 50
    ) -> list[dict[str, Any]]:
        conn = cls._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hce_proposed_intents "
                "WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["inferred_goal_structure"] = json.loads(d["inferred_goal_structure"])
                result.append(d)
            return result
        finally:
            conn.close()

    @classmethod
    def update_intent_status(cls, proposal_id: str, new_status: IntentStatus) -> bool:
        with cls._lock:
            conn = cls._get_conn()
            try:
                cur = conn.execute(
                    "UPDATE hce_proposed_intents SET status = ? WHERE proposal_id = ?",
                    (new_status.value, proposal_id),
                )
                conn.commit()
                return cur.rowcount > 0
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    # ----- Relationship Metrics -----

    @classmethod
    def get_metrics(cls, relationship_id: str) -> dict[str, Any] | None:
        conn = cls._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM hce_relationship_metrics WHERE relationship_id = ?",
                (relationship_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @classmethod
    def update_metrics(cls, relationship_id: str, **kwargs: float) -> None:
        allowed = {
            "trust_score", "continuity_score", "understanding_score",
            "helpfulness_velocity", "correction_rate", "disagreement_rate",
            "user_repetition_rate",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        now = time.time()
        updates["updated_at"] = now
        updates["total_utterances"] = None  # handled separately below

        with cls._lock:
            conn = cls._get_conn()
            try:
                # Increment total_utterances if requested
                increment_utt = kwargs.get("_increment_utterances", False)
                if increment_utt:
                    conn.execute(
                        "UPDATE hce_relationship_metrics "
                        "SET total_utterances = total_utterances + 1 "
                        "WHERE relationship_id = ?",
                        (relationship_id,),
                    )

                # Apply metric updates
                real_updates = {k: v for k, v in updates.items()
                                if k != "total_utterances" and v is not None}
                if real_updates:
                    set_clause = ", ".join(f"{k} = ?" for k in real_updates)
                    conn.execute(
                        f"UPDATE hce_relationship_metrics SET {set_clause} "
                        f"WHERE relationship_id = ?",
                        list(real_updates.values()) + [relationship_id],
                    )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    # ----- Contradictions -----

    @classmethod
    def store_contradiction(
        cls,
        entity_id: str,
        fact_a: str,
        fact_b: str,
        resolution: ContradictionResolution = ContradictionResolution.CONFLICTED,
    ) -> str:
        cid = str(uuid.uuid4())
        now = time.time()
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute(
                    "INSERT INTO hce_contradictions "
                    "(contradiction_id, entity_id, fact_a, fact_b, "
                    "detected_at, resolution_status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (cid, entity_id, fact_a, fact_b, now, resolution.value),
                )
                conn.commit()
                return cid
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_contradictions(
        cls, entity_id: str, unresolved_only: bool = True
    ) -> list[dict[str, Any]]:
        conn = cls._get_conn()
        try:
            if unresolved_only:
                rows = conn.execute(
                    "SELECT * FROM hce_contradictions "
                    "WHERE entity_id = ? AND resolution_status = 'CONFLICTED' "
                    "ORDER BY detected_at DESC",
                    (entity_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM hce_contradictions WHERE entity_id = ? "
                    "ORDER BY detected_at DESC",
                    (entity_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ----- Narrative Arcs -----

    @classmethod
    def upsert_narrative_arc(
        cls, relationship_id: str, arc_name: str,
        arc_summary: str, chapter_ids: list[str]
    ) -> str:
        now = time.time()
        with cls._lock:
            conn = cls._get_conn()
            try:
                row = conn.execute(
                    "SELECT arc_id FROM hce_narrative_arcs "
                    "WHERE relationship_id = ? AND arc_name = ?",
                    (relationship_id, arc_name),
                ).fetchone()
                if row:
                    arc_id = row["arc_id"]
                    conn.execute(
                        "UPDATE hce_narrative_arcs "
                        "SET arc_summary = ?, chapter_ids = ?, updated_at = ? "
                        "WHERE arc_id = ?",
                        (arc_summary, json.dumps(chapter_ids), now, arc_id),
                    )
                else:
                    arc_id = str(uuid.uuid4())
                    conn.execute(
                        "INSERT INTO hce_narrative_arcs "
                        "(arc_id, relationship_id, arc_name, arc_summary, "
                        "chapter_ids, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (arc_id, relationship_id, arc_name,
                         arc_summary, json.dumps(chapter_ids), now),
                    )
                conn.commit()
                return arc_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_narrative_arcs(cls, relationship_id: str) -> list[dict[str, Any]]:
        conn = cls._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hce_narrative_arcs WHERE relationship_id = ? "
                "ORDER BY updated_at DESC",
                (relationship_id,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["chapter_ids"] = json.loads(d["chapter_ids"])
                result.append(d)
            return result
        finally:
            conn.close()

    @classmethod
    def reset(cls) -> None:
        """Drop all HCE data (used by tests)."""
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.executescript("""
                    DELETE FROM hce_narrative_arcs;
                    DELETE FROM hce_contradictions;
                    DELETE FROM hce_relationship_metrics;
                    DELETE FROM hce_proposed_intents;
                    DELETE FROM hce_memory_candidates;
                    DELETE FROM hce_reflections;
                    DELETE FROM hce_utterances;
                    DELETE FROM hce_chapters;
                    DELETE FROM hce_relationships;
                """)
                conn.commit()
                cls._schema_ensured = False
            finally:
                conn.close()


# ---------------------------------------------------------------------------
# Text-signal helpers (no LLM on the hot path)
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an the and or but if then is are was were be been being to of in on at for "
    "with from by as it its this that these those i you he she we they me my your "
    "our do does did can could should would will just now please have has had not".split()
)

def _tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(text.lower()) if len(t) > 2 and t not in _STOPWORDS}


# Friction signal: vocabulary that indicates blocked / difficult state
_FRICTION_TERMS = frozenset((
    "stuck", "blocked", "confused", "broken", "error", "fail", "failed", "failing",
    "issue", "problem", "trouble", "struggle", "can't", "cannot", "not working",
    "frustrated", "exhausted", "lost", "wrong", "crash", "exception", "bug",
    "deadlock", "timeout", "mismatch", "corrupt", "invalid",
))

# Ambiguity signal: vocabulary that signals unclear intent or underspecification
_AMBIGUITY_TERMS = frozenset((
    "maybe", "perhaps", "not sure", "i think", "i guess", "somehow",
    "kind of", "sort of", "something like", "unclear", "unsure",
    "don't know", "which", "either", "or", "any", "some",
))

# Goal intent signals
_GOAL_INTENT_TERMS = frozenset((
    "want to", "i want", "i need", "i plan", "my goal", "goal is",
    "would like", "aiming to", "trying to", "hope to", "i will",
    "i am going to", "i intend", "i'm planning",
))

# Preference signals
_PREFERENCE_TERMS = frozenset((
    "prefer", "i like", "i love", "i hate", "i dislike", "always use",
    "never use", "favorite", "i usually", "tend to", "i find",
))


def _compute_friction_signal(text: str) -> float:
    lower = text.lower()
    hits = sum(1 for t in _FRICTION_TERMS if t in lower)
    return min(1.0, hits / 4.0)


def _compute_ambiguity_score(text: str) -> float:
    lower = text.lower()
    hits = sum(1 for t in _AMBIGUITY_TERMS if t in lower)
    # Also flag very short messages as ambiguous
    word_count = len(lower.split())
    short_penalty = 0.2 if word_count < 6 else 0.0
    return min(1.0, hits / 4.0 + short_penalty)


def _compute_blocker_density(recalled_context: list[dict[str, Any]]) -> float:
    if not recalled_context:
        return 0.0
    blocker_terms = {"blocked", "blocker", "failed", "stuck", "impediment", "BLOCKED"}
    count = sum(
        1 for c in recalled_context
        if any(t in str(c.get("content", "")) for t in blocker_terms)
    )
    return min(1.0, count / max(1, len(recalled_context)))


# ---------------------------------------------------------------------------
# Engine: AcknowledgementEngine (Rule 3 enforcer)
# ---------------------------------------------------------------------------

class AcknowledgementEngine:
    """Computes friction / ambiguity signals from text properties.

    NEVER outputs emotional claims about the human.
    NEVER stores results beyond the current turn.
    Outputs: friction_signal, ambiguity_score, blocker_density.
    These are properties of the MESSAGE TEXT, not of the person.
    """

    @staticmethod
    def compute(
        user_message: str,
        recalled_context: list[dict[str, Any]],
    ) -> tuple[float, float, float]:
        """Returns (friction_signal, ambiguity_score, blocker_density)."""
        return (
            _compute_friction_signal(user_message),
            _compute_ambiguity_score(user_message),
            _compute_blocker_density(recalled_context),
        )


# ---------------------------------------------------------------------------
# Engine: AttentionBudget
# ---------------------------------------------------------------------------

class AttentionBudget:
    """Per-utterance interrupt budget: max 2 combined (questions + reconfirmations).

    Curiosity + Reconfirmation combined must not exceed the budget.
    Most interactions should use 0 interruptions.
    """
    MAX_INTERRUPTIONS: int = 2

    def __init__(self) -> None:
        self._used: int = 0

    def can_ask(self) -> bool:
        return self._used < self.MAX_INTERRUPTIONS

    def consume(self, count: int = 1) -> int:
        allowed = min(count, self.MAX_INTERRUPTIONS - self._used)
        self._used += allowed
        return allowed

    @property
    def remaining(self) -> int:
        return max(0, self.MAX_INTERRUPTIONS - self._used)


# ---------------------------------------------------------------------------
# Engine: CuriosityEngine
# ---------------------------------------------------------------------------

class CuriosityEngine:
    """Generates 0–2 targeted clarifying questions when ambiguity is high.

    Rules:
    - Only fires when ambiguity_score > 0.3
    - Respects AttentionBudget strictly
    - Questions must reduce uncertainty about active goals/projects
    - Never open-ended or trivial
    """

    AMBIGUITY_THRESHOLD: float = 0.3

    @classmethod
    def generate(
        cls,
        user_message: str,
        ambiguity_score: float,
        budget: AttentionBudget,
        *,
        active_goals: list[dict[str, Any]] | None = None,
        active_projects: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        if ambiguity_score < cls.AMBIGUITY_THRESHOLD or not budget.can_ask():
            return []

        questions: list[str] = []
        lower = user_message.lower()

        # Question 1: project / scope clarification when context is ambiguous
        if budget.can_ask() and active_projects:
            project_names = [p.get("name", p.get("project_name", "")) for p in active_projects[:3]]
            if project_names and not any(n.lower() in lower for n in project_names if n):
                q = (
                    "Which of your active projects does this relate to — "
                    + ", ".join(project_names[:2])
                    + ("?" if len(project_names) <= 2 else ", or another?")
                )
                questions.append(q)
                budget.consume(1)

        # Question 2: goal clarification when goal intent is ambiguous
        if budget.can_ask() and ambiguity_score > 0.5:
            questions.append(
                "Can you clarify what outcome you're aiming for, "
                "so I can give you the most precise answer?"
            )
            budget.consume(1)

        return questions


# ---------------------------------------------------------------------------
# Engine: MemoryCandidateProducer (Rule 2 enforcer)
# ---------------------------------------------------------------------------

_MEMORY_CONFIDENCE_THRESHOLD = 0.45

class MemoryCandidateProducer:
    """Extracts MemoryCandidate objects from a user message.

    NEVER writes to HumanMemoryStore, EpisodicMemory, or RelationshipMemory.
    All candidates sit in hce_memory_candidates with governance_status=PENDING
    until explicitly committed by the user or the governance gate.
    """

    @classmethod
    def extract(
        cls,
        user_message: str,
        utterance_id: str,
    ) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []
        lower = user_message.lower()

        # EPISODIC candidate: discrete event signals
        event_cues = ("started", "finished", "deployed", "launched", "joined",
                       "completed", "designed", "built", "created", "wrote",
                       "published", "quit", "left", "moved", "got hired",
                       "got promoted", "earned", "learned")
        if any(c in lower for c in event_cues):
            candidates.append(MemoryCandidate(
                candidate_id=str(uuid.uuid4()),
                utterance_id=utterance_id,
                memory_tier=MemoryTier.EPISODIC,
                extracted_fact=user_message.strip(),
                confidence=0.65,
            ))

        # SEMANTIC candidate: stable facts / preferences
        if any(t in lower for t in _PREFERENCE_TERMS):
            candidates.append(MemoryCandidate(
                candidate_id=str(uuid.uuid4()),
                utterance_id=utterance_id,
                memory_tier=MemoryTier.SEMANTIC,
                extracted_fact=user_message.strip(),
                confidence=0.72,
            ))

        # RELATIONSHIP candidate: interaction style signals
        style_cues = ("always explain", "please be concise", "i prefer detailed",
                       "skip the basics", "just the code", "step by step",
                       "show me the architecture first", "give me the full picture",
                       "i learn better", "tldr", "in short")
        if any(c in lower for c in style_cues):
            candidates.append(MemoryCandidate(
                candidate_id=str(uuid.uuid4()),
                utterance_id=utterance_id,
                memory_tier=MemoryTier.RELATIONSHIP,
                extracted_fact=user_message.strip(),
                confidence=0.80,
            ))

        # Apply confidence threshold (Rule 2: only high-signal candidates)
        return [c for c in candidates if c.confidence >= _MEMORY_CONFIDENCE_THRESHOLD]


# ---------------------------------------------------------------------------
# Engine: IntentCandidateProducer (Rule 1 enforcer)
# ---------------------------------------------------------------------------

class IntentCandidateProducer:
    """Extracts ProposedIntent objects from user messages.

    NEVER calls GoalMemory.create_goal().
    All intents sit as PENDING_USER_CONFIRMATION until user explicitly commits.
    """

    @classmethod
    def extract(
        cls, user_message: str, utterance_id: str
    ) -> list[ProposedIntent]:
        lower = user_message.lower()
        intents: list[ProposedIntent] = []

        if not any(t in lower for t in _GOAL_INTENT_TERMS):
            return intents

        # Build a structured goal proposal (no write to GoalMemory)
        goal_structure = {
            "title": user_message.strip()[:120],
            "description": user_message.strip(),
            "provenance": "HCE_EXTRACTION",
            "status": "PENDING_USER_CONFIRMATION",
            "extracted_from_utterance": utterance_id,
        }
        intents.append(ProposedIntent(
            proposal_id=str(uuid.uuid4()),
            utterance_id=utterance_id,
            inferred_goal_structure=goal_structure,
        ))
        return intents


# ---------------------------------------------------------------------------
# Engine: ContradictionDetector
# ---------------------------------------------------------------------------

_CONTRADICTION_PAIRS = [
    (frozenset(("prefer", "prefer not", "like", "dislike", "hate", "love")),
     "preference"),
    (frozenset(("startup", "corporate", "government", "freelance", "employment")),
     "career_direction"),
    (frozenset(("simple", "minimal", "complex", "detailed", "thorough")),
     "style_preference"),
]


class ContradictionDetector:
    """Detects time-bound or simultaneous conflicting facts.

    Stores both facts as CONFLICTED without overwriting the older one.
    Time-bound contradictions (valid at different times) are stored as TIME_BOUND.
    """

    @classmethod
    def check(
        cls,
        user_message: str,
        entity_id: str,
        recent_preferences: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Returns a list of detected contradiction dicts (does NOT write to DB yet)."""
        lower = user_message.lower()
        detected: list[dict[str, Any]] = []

        for term_set, category in _CONTRADICTION_PAIRS:
            message_matches = [t for t in term_set if t in lower]
            if not message_matches:
                continue
            # Check if any stored preference in the same category contradicts
            for pref in recent_preferences:
                pref_val = pref.get("value", "").lower()
                pref_cat = pref.get("category", "").lower()
                if category not in pref_cat and category not in pref_val:
                    continue
                pref_matches = [t for t in term_set if t in pref_val]
                if pref_matches and not any(m in pref_val for m in message_matches):
                    detected.append({
                        "entity_id": entity_id,
                        "fact_a": pref.get("value", ""),
                        "fact_b": user_message.strip(),
                        "category": category,
                        "resolution": ContradictionResolution.TIME_BOUND.value,
                    })
        return detected


# ---------------------------------------------------------------------------
# Engine: PersonalityConsistencyEngine + IntellectualIntegrityMonitor
# ---------------------------------------------------------------------------

_STATE_TO_POSTURE: dict[RelationshipState, PersonalityPosture] = {
    RelationshipState.DEBUGGING_MODE:  PersonalityPosture.TECHNICAL_EXECUTOR,
    RelationshipState.BUILDING_MODE:   PersonalityPosture.TECHNICAL_EXECUTOR,
    RelationshipState.PLANNING_MODE:   PersonalityPosture.STRATEGIC_COLLABORATOR,
    RelationshipState.LEARNING_MODE:   PersonalityPosture.ACADEMIC_TEACHER,
    RelationshipState.EXPLORATION_MODE: PersonalityPosture.PLANNER,
}


class PersonalityConsistencyEngine:
    """Derives PersonalityPosture fresh per chapter from RelationshipState.

    Rule 4: Core personality constants are FROZEN (never modified at runtime).
    Adaptive posture is NEVER accumulated across chapters.
    """

    # Core layer: immutable constants
    CORE_TRAITS: dict[str, bool] = {
        "helpful": True,
        "truthful": True,
        "patient": True,
        "curious": True,
        "respectful": True,
    }

    @classmethod
    def derive_posture(cls, state: RelationshipState) -> PersonalityPosture:
        """Derive posture from state. No history. No accumulation."""
        return _STATE_TO_POSTURE.get(state, PersonalityPosture.TECHNICAL_EXECUTOR)


class IntellectualIntegrityMonitor:
    """Anti-sycophancy guard.

    Tracks correction_rate and disagreement_rate.
    Fires an integrity_flag if the system has agreed with the user
    without corrections for an extended period — because that is failure.
    """

    AGREEMENT_CONCERN_THRESHOLD_UTTERANCES: int = 20
    MIN_CORRECTION_RATE_THRESHOLD: float = 0.02  # expect ≥2% corrections

    @classmethod
    def check(cls, metrics: dict[str, Any]) -> bool:
        """Returns True (integrity_flag=True) if sycophancy risk is detected."""
        total = metrics.get("total_utterances", 0)
        correction_rate = metrics.get("correction_rate", 0.0)
        if total >= cls.AGREEMENT_CONCERN_THRESHOLD_UTTERANCES:
            if correction_rate < cls.MIN_CORRECTION_RATE_THRESHOLD:
                return True
        return False


# ---------------------------------------------------------------------------
# Engine: RelationshipContinuityEngine
# ---------------------------------------------------------------------------

class RelationshipContinuityEngine:
    """Manages the Relationship → Chapter lifecycle.

    Derives RelationshipState from active projects / goals context.
    """

    @classmethod
    def derive_state(
        cls,
        active_projects: list[dict[str, Any]],
        user_message: str,
    ) -> RelationshipState:
        """Derive RelationshipState from project health + message signals."""
        lower = user_message.lower()

        # Debug signals
        if any(t in lower for t in ("error", "bug", "crash", "exception",
                                     "fail", "debug", "trace", "stacktrace")):
            return RelationshipState.DEBUGGING_MODE

        # Planning signals
        if any(t in lower for t in ("plan", "architecture", "design", "roadmap",
                                     "milestone", "strategy", "approach")):
            return RelationshipState.PLANNING_MODE

        # Learning signals
        if any(t in lower for t in ("explain", "how does", "what is", "why does",
                                     "teach", "understand", "learn")):
            return RelationshipState.LEARNING_MODE

        # Exploration signals
        if any(t in lower for t in ("explore", "research", "consider", "what if",
                                     "options", "alternatives", "compare")):
            return RelationshipState.EXPLORATION_MODE

        # Default: building if active projects exist
        if active_projects:
            return RelationshipState.BUILDING_MODE

        return RelationshipState.EXPLORATION_MODE

    @classmethod
    def get_or_open_chapter(
        cls,
        relationship_id: str,
        relationship_state: RelationshipState,
    ) -> str:
        """Return active chapter_id, opening a new one if none exists."""
        existing = HCEStore.get_active_chapter(relationship_id)
        if existing:
            return existing["chapter_id"]
        chapter = HCEStore.open_chapter(relationship_id, relationship_state)
        return chapter["chapter_id"]


# ---------------------------------------------------------------------------
# Engine: ReflectionEngine
# ---------------------------------------------------------------------------

class ReflectionEngine:
    """Builds a ReflectionSummary before any response is composed.

    Answers internally:
    - What did the user ask?
    - What do I already know?
    - What changed?
    - What matters most right now?
    """

    @classmethod
    def reflect(
        cls,
        user_message: str,
        recalled_context: list[dict[str, Any]],
        relationship_state: RelationshipState,
        personality_posture: PersonalityPosture,
        friction_signal: float,
        ambiguity_score: float,
        blocker_density: float,
    ) -> ReflectionSummary:
        # Intent deduction: a concise internal description of what the user wants
        intent = cls._deduce_intent(user_message, recalled_context)
        return ReflectionSummary(
            intent_deduction=intent,
            recalled_context=recalled_context,
            personality_posture=personality_posture,
            relationship_state=relationship_state,
            friction_signal=friction_signal,
            ambiguity_score=ambiguity_score,
            blocker_density=blocker_density,
        )

    @classmethod
    def _deduce_intent(
        cls,
        user_message: str,
        recalled_context: list[dict[str, Any]],
    ) -> str:
        lower = user_message.lower()

        if any(t in lower for t in ("how do i", "how to", "how can i", "steps")):
            return "User is requesting procedural guidance."
        if any(t in lower for t in ("what is", "what are", "explain", "define")):
            return "User is requesting conceptual explanation."
        if any(t in lower for t in ("why", "why does", "why is", "reason")):
            return "User is seeking causal reasoning."
        if any(t in lower for t in ("status", "progress", "how is", "update")):
            return "User is requesting a status or progress update."
        if any(t in lower for t in ("fix", "solve", "help", "error", "issue")):
            return "User is requesting problem-solving assistance."
        if any(t in lower for t in _GOAL_INTENT_TERMS):
            return "User is expressing a goal or intent."
        if recalled_context:
            return f"User message relates to {len(recalled_context)} recalled context items."
        return "User intent requires further clarification."


# ---------------------------------------------------------------------------
# Engine: NarrativeEngine
# ---------------------------------------------------------------------------

class NarrativeEngine:
    """Converts raw data signals into narrative text fragments.

    Example:
      Input:  project_completion=0.74, blockers=0, milestones_remaining=2
      Output: "The project has cleared its steepest climb. Two milestones remain."
    """

    @classmethod
    def frame_project_progress(
        cls,
        project_name: str,
        completion: float,
        blockers: int,
        milestones_remaining: int,
    ) -> str:
        if completion >= 0.9:
            progress = "is in its final stretch"
        elif completion >= 0.7:
            progress = "has cleared its steepest climb"
        elif completion >= 0.5:
            progress = "has crossed the halfway point"
        elif completion >= 0.3:
            progress = "has laid its foundations"
        else:
            progress = "is in its early stages"

        blocker_clause = (
            f" {blockers} active blocker{'s' if blockers != 1 else ''} remain."
            if blockers > 0 else " No active blockers."
        )

        milestone_clause = (
            f" {milestones_remaining} milestone{'s' if milestones_remaining != 1 else ''} remain ahead."
            if milestones_remaining > 0 else " All milestones are complete."
        )

        return f"'{project_name}' {progress}.{blocker_clause}{milestone_clause}"

    @classmethod
    def frame_context_snapshot(
        cls,
        active_goals: int,
        active_projects: int,
        recalled_memories: int,
    ) -> str:
        parts = []
        if active_goals:
            parts.append(f"{active_goals} active goal{'s' if active_goals != 1 else ''}")
        if active_projects:
            parts.append(f"{active_projects} active project{'s' if active_projects != 1 else ''}")
        if recalled_memories:
            parts.append(f"{recalled_memories} recalled context item{'s' if recalled_memories != 1 else ''}")
        if not parts:
            return "No prior context retrieved."
        return "Context snapshot: " + ", ".join(parts) + "."


# ---------------------------------------------------------------------------
# Engine: NarrativeContinuityEngine
# ---------------------------------------------------------------------------

_ARC_KEYWORDS: dict[str, list[str]] = {
    "Career Arc": ["job", "career", "role", "hire", "promotion", "work", "company",
                   "employment", "resign", "quit", "joined", "interview"],
    "Kattappa Arc": ["kattappa", "ai system", "cognitive", "architecture", "hce",
                     "goal system", "ppm", "sandbox", "verification engine"],
    "Embedded Systems Arc": ["embedded", "firmware", "microcontroller", "stm32",
                              "uart", "spi", "i2c", "rtos", "pcb", "hardware",
                              "iot", "sensor", "sriot"],
    "Learning Arc": ["learning", "study", "course", "certification", "book",
                     "concept", "understand", "diploma", "college", "university"],
}


class NarrativeContinuityEngine:
    """Maintains long-term story arcs (auto-detected from chapter summaries).

    No manual seeding required — arcs are inferred from message content and
    updated when a chapter is closed with a summary narrative.
    """

    @classmethod
    def detect_arcs(cls, text: str) -> list[str]:
        """Returns arc names whose keywords appear in text."""
        lower = text.lower()
        return [
            arc_name for arc_name, keywords in _ARC_KEYWORDS.items()
            if any(k in lower for k in keywords)
        ]

    @classmethod
    def update_arcs_from_chapter(
        cls,
        relationship_id: str,
        chapter_id: str,
        chapter_summary: str,
    ) -> list[str]:
        """Detects and updates relevant arcs. Returns updated arc names."""
        arcs_detected = cls.detect_arcs(chapter_summary)
        updated = []
        for arc_name in arcs_detected:
            # Load existing arc to append chapter_id
            existing_arcs = HCEStore.get_narrative_arcs(relationship_id)
            arc_data = next(
                (a for a in existing_arcs if a["arc_name"] == arc_name), None
            )
            chapter_ids = arc_data["chapter_ids"] if arc_data else []
            if chapter_id not in chapter_ids:
                chapter_ids.append(chapter_id)
            HCEStore.upsert_narrative_arc(
                relationship_id=relationship_id,
                arc_name=arc_name,
                arc_summary=chapter_summary[:500],
                chapter_ids=chapter_ids,
            )
            updated.append(arc_name)
        return updated


# ---------------------------------------------------------------------------
# Engine: ConversationHealthMonitor
# ---------------------------------------------------------------------------

class ConversationHealthMonitor:
    """Tracks conversation quality signals.

    Monitors:
    - context_retention: how rarely the user re-explains things
    - correction_rate: how often the system is corrected
    - user_repetition_rate: how often the user repeats the same content

    These metrics feed retrieval priority only. Never behavioral signals.
    """

    @classmethod
    def detect_repetition(
        cls,
        user_message: str,
        recent_utterances: list[dict[str, Any]],
    ) -> float:
        """Returns [0,1] repetition score for this message vs recent history."""
        if not recent_utterances:
            return 0.0
        tokens = _tokens(user_message)
        if not tokens:
            return 0.0

        scores = []
        for utt in recent_utterances[-5:]:
            prev_tokens = _tokens(utt.get("user_message", ""))
            if prev_tokens:
                intersection = len(tokens & prev_tokens)
                union = len(tokens | prev_tokens)
                scores.append(intersection / union if union else 0.0)

        return max(scores) if scores else 0.0

    @classmethod
    def update(
        cls,
        relationship_id: str,
        user_message: str,
        recent_utterances: list[dict[str, Any]],
        *,
        system_was_corrected: bool = False,
        system_disagreed: bool = False,
    ) -> None:
        """Update health metrics. All values are exponentially smoothed."""
        metrics = HCEStore.get_metrics(relationship_id)
        if not metrics:
            return

        repetition = cls.detect_repetition(user_message, recent_utterances)
        total = max(1, metrics.get("total_utterances", 1))

        # Exponential moving average (α = 0.1 so history matters)
        alpha = 0.1
        new_rep = (1 - alpha) * metrics["user_repetition_rate"] + alpha * repetition
        new_corr = (1 - alpha) * metrics["correction_rate"] + alpha * (1.0 if system_was_corrected else 0.0)
        new_disag = (1 - alpha) * metrics["disagreement_rate"] + alpha * (1.0 if system_disagreed else 0.0)

        HCEStore.update_metrics(
            relationship_id,
            user_repetition_rate=new_rep,
            correction_rate=new_corr,
            disagreement_rate=new_disag,
            _increment_utterances=True,
        )


# ---------------------------------------------------------------------------
# Engine: TrustRecoveryEngine
# ---------------------------------------------------------------------------

class TrustRecoveryEngine:
    """Manages trust repair after errors.

    Error → Acknowledgement → Correction → Repair
    Trust score improves through verified accuracy, not conversation length.
    """

    TRUST_PENALTY_PER_ERROR: float = 2.0
    TRUST_RECOVERY_PER_CORRECTION: float = 1.5

    @classmethod
    def record_error(cls, relationship_id: str) -> None:
        metrics = HCEStore.get_metrics(relationship_id)
        if not metrics:
            return
        new_trust = max(0.0, metrics["trust_score"] - cls.TRUST_PENALTY_PER_ERROR)
        HCEStore.update_metrics(relationship_id, trust_score=new_trust)

    @classmethod
    def record_correction(cls, relationship_id: str) -> None:
        """Called when system acknowledges and corrects an error."""
        metrics = HCEStore.get_metrics(relationship_id)
        if not metrics:
            return
        new_trust = min(100.0, metrics["trust_score"] + cls.TRUST_RECOVERY_PER_CORRECTION)
        HCEStore.update_metrics(
            relationship_id,
            trust_score=new_trust,
            correction_rate=metrics["correction_rate"],  # preserve; updated by HealthMonitor
        )


# ---------------------------------------------------------------------------
# Context assembler
# ---------------------------------------------------------------------------

def _assemble_context(
    user_message: str,
    relationship_id: str,
    chapter_id: str,
    relationship_state: RelationshipState,
) -> ConversationContext:
    """Read-only context assembly. Never writes to any external store."""
    active_goals: list[dict[str, Any]] = []
    active_projects: list[dict[str, Any]] = []
    recalled_memories: list[dict[str, Any]] = []
    relationship_history: list[dict[str, Any]] = []
    preferences: list[dict[str, Any]] = []

    rel = HCEStore.get_relationship(relationship_id)
    user_entity_id = rel["user_entity_id"] if rel else ""

    # Goals (read-only)
    try:
        from backend.core.goal_memory import GoalMemory
        active_goals = GoalMemory.list_goals(status="ACTIVE")[:5]
    except Exception as e:
        log_event(f"hce: goal recall failed: {e}")

    # Projects (read-only)
    try:
        from backend.core.personal_project_manager import PersonalProjectManager
        active_projects = PersonalProjectManager.list_projects(status="ACTIVE")[:5]
    except Exception as e:
        log_event(f"hce: project recall failed: {e}")

    # Episodic memories (read-only)
    try:
        from backend.core.episodic_memory import EpisodicMemory
        recalled_memories = EpisodicMemory.recall(user_message, limit=4)
    except Exception as e:
        log_event(f"hce: episodic recall failed: {e}")

    # Relationship history + preferences (read-only)
    try:
        from backend.core.relationship_memory import RelationshipMemory
        if user_entity_id:
            relationship_history = RelationshipMemory.get_history(user_entity_id, limit=3)
            preferences = RelationshipMemory.get_preferences(user_entity_id)
    except Exception as e:
        log_event(f"hce: relationship recall failed: {e}")

    return ConversationContext(
        active_goals=active_goals,
        active_projects=active_projects,
        recalled_memories=recalled_memories,
        relationship_history=relationship_history,
        preferences=preferences,
        relationship_state=relationship_state,
        chapter_id=chapter_id,
    )


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

class HumanConversationEngine:
    """Social Cortex of Kattappa.

    Single entry point for all conversation processing.
    Pipeline: Context → Reflect → Acknowledge → Curiosity → Extract → Compose

    Constitutional guarantees are enforced by to_dict():
        authorized_to_create_goals: always False
        authorized_to_write_memory: always False
    """

    @classmethod
    def process(
        cls,
        user_message: str,
        *,
        relationship_id: str,
        chapter_id: str | None = None,
    ) -> HCEResponse:
        """Full conversation processing pipeline."""

        # 1. Ensure chapter exists
        rel = HCEStore.get_relationship(relationship_id)
        if not rel:
            raise ValueError(f"Relationship {relationship_id!r} not found. Create it first.")

        user_entity_id = rel["user_entity_id"]

        # 2. Assemble preliminary context to determine state
        #    (lightweight: just active projects for state derivation)
        active_projects_preview: list[dict[str, Any]] = []
        try:
            from backend.core.personal_project_manager import PersonalProjectManager
            active_projects_preview = PersonalProjectManager.list_projects(status="ACTIVE")[:3]
        except Exception:
            pass

        relationship_state = RelationshipContinuityEngine.derive_state(
            active_projects_preview, user_message
        )

        effective_chapter_id = chapter_id or RelationshipContinuityEngine.get_or_open_chapter(
            relationship_id, relationship_state
        )

        # 3. Create utterance record
        utterance_id = HCEStore.create_utterance(effective_chapter_id, user_message)

        # 4. Full context assembly
        ctx = _assemble_context(
            user_message, relationship_id, effective_chapter_id, relationship_state
        )

        # 5. Acknowledgement signals (ephemeral — never persisted beyond this turn)
        friction_signal, ambiguity_score, blocker_density = AcknowledgementEngine.compute(
            user_message, ctx.recalled_memories
        )

        # 6. Personality posture (derived fresh — never accumulated)
        posture = PersonalityConsistencyEngine.derive_posture(relationship_state)

        # 7. Reflection
        reflection = ReflectionEngine.reflect(
            user_message, ctx.recalled_memories, relationship_state,
            posture, friction_signal, ambiguity_score, blocker_density,
        )

        # 8. Curiosity + AttentionBudget
        budget = AttentionBudget()
        questions = CuriosityEngine.generate(
            user_message, ambiguity_score, budget,
            active_goals=ctx.active_goals,
            active_projects=ctx.active_projects,
        )

        # 9. Memory candidates (proposed only — Rule 2)
        memory_candidates = MemoryCandidateProducer.extract(user_message, utterance_id)
        for candidate in memory_candidates:
            HCEStore.store_memory_candidate(candidate)

        # 10. Intent candidates (proposed only — Rule 1)
        proposed_intents = IntentCandidateProducer.extract(user_message, utterance_id)
        for intent in proposed_intents:
            HCEStore.store_proposed_intent(intent)

        # 11. Contradiction detection
        contradictions_raw = ContradictionDetector.check(
            user_message, user_entity_id, ctx.preferences
        )
        persisted_contradictions: list[dict[str, Any]] = []
        for c in contradictions_raw:
            cid = HCEStore.store_contradiction(
                entity_id=c["entity_id"],
                fact_a=c["fact_a"],
                fact_b=c["fact_b"],
                resolution=ContradictionResolution(c["resolution"]),
            )
            c["contradiction_id"] = cid
            persisted_contradictions.append(c)

        # 12. Narrative framing
        narrative = NarrativeEngine.frame_context_snapshot(
            active_goals=len(ctx.active_goals),
            active_projects=len(ctx.active_projects),
            recalled_memories=len(ctx.recalled_memories),
        )

        # 13. Intellectual integrity check
        metrics = HCEStore.get_metrics(relationship_id) or {}
        integrity_flag = IntellectualIntegrityMonitor.check(metrics)

        # 14. Log reflection
        HCEStore.log_reflection(utterance_id, reflection, questions_asked=len(questions))

        # 15. Health monitor update
        recent_utterances = HCEStore.get_recent_utterances(effective_chapter_id, limit=5)
        ConversationHealthMonitor.update(
            relationship_id, user_message, recent_utterances
        )

        return HCEResponse(
            utterance_id=utterance_id,
            chapter_id=effective_chapter_id,
            relationship_id=relationship_id,
            reflection=reflection,
            conversation_context=ctx,
            memory_candidates=memory_candidates,
            proposed_intents=proposed_intents,
            contradictions_detected=persisted_contradictions,
            curiosity_questions=questions,
            narrative_framing=narrative,
            integrity_flag=integrity_flag,
        )

    @classmethod
    def commit_memory_candidate(cls, candidate_id: str) -> bool:
        """Move a PENDING memory candidate to COMMITTED status and write to Memory Fabric.

        This is the governance gate that converts a proposal into a real memory.
        """
        candidates = HCEStore.get_memory_candidates(governance_status="PENDING")
        cand = next((c for c in candidates if c["candidate_id"] == candidate_id), None)
        if not cand:
            return False

        # Attempt to write to the appropriate memory store
        committed = False
        try:
            if cand["memory_tier"] == MemoryTier.EPISODIC.value:
                from backend.core.episodic_memory import EpisodicMemory
                EpisodicMemory.create_episode(
                    content=cand["extracted_fact"],
                    importance=cand["confidence"],
                    category="hce_candidate",
                )
                committed = True
            elif cand["memory_tier"] in (MemoryTier.SEMANTIC.value, MemoryTier.RELATIONSHIP.value):
                from backend.core.human_memory import (
                    HumanMemoryStore, MemoryRecord, MemoryType, classify_memory_type
                )
                import uuid as _uuid
                mem_type = classify_memory_type(cand["extracted_fact"])
                record = MemoryRecord(
                    id=_uuid.uuid4().hex,
                    type=mem_type,
                    content=cand["extracted_fact"],
                    importance=cand["confidence"],
                    confidence=cand["confidence"],
                    decay_score=1.0,
                    recall_count=0,
                    created_at=time.time(),
                    last_recall_at=time.time(),
                    pinned=False,
                    trusted=True,
                    source="hce_candidate",
                    compression_level=0,
                )
                HumanMemoryStore.insert(record)
                committed = True
        except Exception as e:
            log_event(f"hce: memory commit failed for {candidate_id}: {e}")

        if committed:
            HCEStore.update_candidate_status(candidate_id, GovernanceStatus.COMMITTED)
        return committed

    @classmethod
    def reject_memory_candidate(cls, candidate_id: str) -> bool:
        return HCEStore.update_candidate_status(candidate_id, GovernanceStatus.REJECTED)

    @classmethod
    def commit_proposed_intent(cls, proposal_id: str) -> bool:
        """Submit a PENDING intent to the Goal System.

        Rule 1 compliance: this is the ONLY path through which conversation
        can create a goal, and it requires explicit user confirmation (API call).
        """
        intents = HCEStore.get_proposed_intents(status="PENDING_USER_CONFIRMATION")
        intent = next((i for i in intents if i["proposal_id"] == proposal_id), None)
        if not intent:
            return False

        try:
            from backend.core.goal_memory import GoalMemory
            goal_struct = intent["inferred_goal_structure"]
            GoalMemory.create_goal(
                title=goal_struct.get("title", "Untitled Goal"),
                description=goal_struct.get("description", ""),
                provenance="STATED",
            )
            HCEStore.update_intent_status(proposal_id, IntentStatus.COMMITTED_TO_GOAL_SYSTEM)
            return True
        except Exception as e:
            log_event(f"hce: intent commit failed for {proposal_id}: {e}")
            return False
