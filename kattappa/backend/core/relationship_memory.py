from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from backend.core.config import load_config
from backend.core.logger import log_event


# ---------------------------------------------------------------------------
# Sensitive Content Classifier
# ---------------------------------------------------------------------------

_SENSITIVE_CATEGORIES = {
    "religion": re.compile(
        r"(?i)\b(god|jesus|allah|bible|quran|church|mosque|temple|religious|priest|hindu|muslim|christian|buddhist|jewish|synagogue)\b"
    ),
    "politics": re.compile(
        r"(?i)\b(democrat|republican|election|vote|president|senator|congress|parliament|politics|political|government|lobbyist|mayor|governor)\b"
    ),
    "health": re.compile(
        r"(?i)\b(doctor|hospital|cancer|disease|illness|diagnosis|medicine|medication|patient|sick|symptoms|medical|therapy|clinic|cardio|oncology)\b"
    ),
    "sexual_information": re.compile(
        r"(?i)\b(sexual|sex|orientation|gay|lesbian|bisexual|transgender|pornography|erotic|gender identity|queer)\b"
    ),
    "financial_information": re.compile(
        r"(?i)\b(bank|credit card|debit card|routing number|checking account|savings account|visa|mastercard|amex|cvv|ssn|financial|salary|income|credit limit)\b"
    ),
    "credentials": re.compile(
        r"(?i)\b(password|passwd|auth|token|api[_\-]?key|private[_\-]?key|ssh[_\-]?key|credentials|secret|sk-[a-zA-Z0-9\-]{24,})\b"
    ),
    "government_ids": re.compile(
        r"(?i)\b(ssn|social security|passport|driver['\s]?s license|national id|state id|ein|tax id)\b"
    ),
    "contact_information": re.compile(
        r"(?i)\b(phone number|telephone|cellphone|home address|street address|zip code|postal code|email address)\b"
    ),
}

def classify_sensitive_content(text: str) -> Tuple[bool, str | None]:
    """Scans text to detect sensitive or prohibited data categories.
    
    Returns (is_sensitive, category_name).
    """
    if not text:
        return False, None
    for category, pattern in _SENSITIVE_CATEGORIES.items():
        if pattern.search(text):
            return True, category
    return False, None


# ---------------------------------------------------------------------------
# PII & Secret Redaction Helper
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9\-]{32,70}"), "[REDACTED_API_KEY]"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36,40}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(?i)(key|secret|token|password|passwd|auth)\s*[:=]\s*['\"]([a-zA-Z0-9_\-\.\~]{10,})['\"]"), lambda m: f"{m.group(1)}: '[REDACTED_SECRET]'"),
]

def redact_secrets(text: str) -> str:
    """Scans and sanitizes strings to prevent recording secrets."""
    if not text:
        return text
    current = text
    for pattern, replacement in _SECRET_PATTERNS:
        if callable(replacement):
            current = pattern.sub(replacement, current)
        else:
            current = pattern.sub(replacement, current)
    return current


# ---------------------------------------------------------------------------
# Relationship Memory (Layer 7)
# ---------------------------------------------------------------------------

class RelationshipMemory:
    """Relationship Memory Subsystem (Layer 7).
    
    Provides personalization, user profile data, preference management, and interaction tracking
    integrated with Memory Governance. All columns store data in plaintext (no homemade crypto).
    """

    _lock = threading.RLock()
    _schema_ensured = False

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
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
        with cls._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS hm_entities (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL, -- 'user', 'project', 'organization', 'device', 'person'
                    name TEXT NOT NULL,
                    trust_level TEXT NOT NULL DEFAULT 'TRUST_UNVERIFIED',
                    pinned INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_hm_entities_type ON hm_entities(entity_type);

                CREATE TABLE IF NOT EXISTS hm_preferences (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    category TEXT NOT NULL, -- 'ui', 'tooling', 'coding', 'tone', 'privacy'
                    key TEXT NOT NULL,
                    value TEXT NOT NULL, -- Plaintext
                    confidence REAL NOT NULL DEFAULT 1.0,
                    evidence_count INTEGER DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'superseded', 'rejected', 'expired'
                    superseded_by TEXT, -- Chaining contradictory updates
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (entity_id) REFERENCES hm_entities(id) ON DELETE CASCADE,
                    FOREIGN KEY (superseded_by) REFERENCES hm_preferences(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_hm_pref_entity ON hm_preferences(entity_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_hm_pref_active ON hm_preferences(entity_id, category, key) WHERE status = 'active';

                CREATE TABLE IF NOT EXISTS hm_projects (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'backlog', 'completed'
                    priority REAL NOT NULL DEFAULT 0.5,
                    description TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (entity_id) REFERENCES hm_entities(id) ON DELETE CASCADE,
                    UNIQUE(entity_id, project_name)
                );
                CREATE INDEX IF NOT EXISTS idx_hm_proj_entity ON hm_projects(entity_id);

                CREATE TABLE IF NOT EXISTS hm_user_goals (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'completed', 'archived'
                    priority REAL NOT NULL DEFAULT 0.5,
                    approved INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (entity_id) REFERENCES hm_entities(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_hm_goals_entity ON hm_user_goals(entity_id);

                CREATE TABLE IF NOT EXISTS hm_relationship_history (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    summary TEXT NOT NULL, -- Plaintext
                    importance REAL NOT NULL DEFAULT 0.5,
                    created_at REAL NOT NULL,
                    is_compacted INTEGER DEFAULT 0,
                    FOREIGN KEY (entity_id) REFERENCES hm_entities(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_hm_hist_entity ON hm_relationship_history(entity_id);

                CREATE TABLE IF NOT EXISTS hm_relationship_candidates (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    candidate_type TEXT NOT NULL, -- 'preference', 'goal', 'project'
                    key TEXT NOT NULL DEFAULT '',
                    value TEXT NOT NULL, -- Plaintext
                    evidence_count INTEGER DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'pending_approval', 'promoted', 'rejected', 'expired'
                    expires_at REAL NOT NULL,
                    FOREIGN KEY (entity_id) REFERENCES hm_entities(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_hm_cand_entity ON hm_relationship_candidates(entity_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_hm_cand_unique ON hm_relationship_candidates(entity_id, candidate_type, key) WHERE status = 'pending' OR status = 'pending_approval';

                CREATE TABLE IF NOT EXISTS hm_emotional_state (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    emotion TEXT NOT NULL, -- Plaintext
                    confidence REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (entity_id) REFERENCES hm_entities(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_hm_emo_entity ON hm_emotional_state(entity_id);
                """
            )
            
            # Ensure columns exist for schema updates
            columns_pref = {row[1] for row in conn.execute("PRAGMA table_info(hm_preferences)")}
            if "superseded_by" not in columns_pref:
                conn.execute("ALTER TABLE hm_preferences ADD COLUMN superseded_by TEXT")
                
            columns_hist = {row[1] for row in conn.execute("PRAGMA table_info(hm_relationship_history)")}
            if "is_compacted" not in columns_hist:
                conn.execute("ALTER TABLE hm_relationship_history ADD COLUMN is_compacted INTEGER DEFAULT 0")
                
            conn.commit()

    # ---------------------------------------------------------------------------
    # Opt-in Privacy check
    # ---------------------------------------------------------------------------
    @classmethod
    def is_emotional_logging_enabled(cls, user_entity_id: str) -> bool:
        """Returns True if the user has opted-in to emotional state tracking."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT value FROM hm_preferences WHERE entity_id = ? AND category = 'privacy' AND key = 'emotional_logging_enabled' AND status = 'active'",
                (user_entity_id,)
            ).fetchone()
            if not row:
                return False
            return row["value"].lower() in {"1", "true", "yes"}
        except Exception:
            return False
        finally:
            conn.close()

    # ---------------------------------------------------------------------------
    # Entities CRUD
    # ---------------------------------------------------------------------------
    @classmethod
    def get_or_create_entity(cls, entity_id: str, name: str, entity_type: str = "user", trust_level: str = "TRUST_UNVERIFIED") -> dict[str, Any]:
        """Gets or creates an entity under hm_entities."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT * FROM hm_entities WHERE id = ?", (entity_id,)).fetchone()
                if row:
                    return dict(row)
                conn.execute(
                    """
                    INSERT INTO hm_entities (id, entity_type, name, trust_level, pinned, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 0, ?, ?)
                    """,
                    (entity_id, entity_type.strip().lower(), name.strip(), trust_level, now, now)
                )
                conn.commit()
                
                # Set in MemoryGovernance trust registry
                from backend.core.memory_governance import MemoryGovernance
                MemoryGovernance.set_trust(entity_id, entity_type, trust_level)
                
                return {
                    "id": entity_id,
                    "entity_type": entity_type.strip().lower(),
                    "name": name.strip(),
                    "trust_level": trust_level,
                    "pinned": 0,
                    "created_at": now,
                    "updated_at": now
                }
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_entity(cls, entity_id: str) -> dict[str, Any] | None:
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM hm_entities WHERE id = ?", (entity_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @classmethod
    def update_entity_trust(cls, entity_id: str, trust_level: str) -> bool:
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT entity_type FROM hm_entities WHERE id = ?", (entity_id,)).fetchone()
                if not row:
                    return False
                conn.execute(
                    "UPDATE hm_entities SET trust_level = ?, updated_at = ? WHERE id = ?",
                    (trust_level, now, entity_id)
                )
                conn.commit()
                from backend.core.memory_governance import MemoryGovernance
                MemoryGovernance.set_trust(entity_id, row["entity_type"], trust_level)
                return True
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()

    # ---------------------------------------------------------------------------
    # Preferences CRUD with Lifecycle, Contradiction Chaining & Provenance Logs
    # ---------------------------------------------------------------------------
    @classmethod
    def set_preference(cls, entity_id: str, category: str, key: str, value: str, confidence: float = 1.0, evidence_count: int = 1, status: str = "active") -> str:
        """Stores a preference directly, implementing lifecycle state check, contradiction chaining, and provenance log."""
        is_sensitive, matched_cat = classify_sensitive_content(value)
        if is_sensitive:
            raise ValueError(f"Content blocked due to sensitive category: {matched_cat}")

        now = time.time()
        pref_id = str(uuid.uuid4())
        redacted_value = redact_secrets(value)
        
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Preference Lifecycle check: if inserting active preference, supersede the previous active one & set superseded_by link
                if status == "active":
                    conn.execute(
                        "UPDATE hm_preferences SET status = 'superseded', superseded_by = ?, updated_at = ? WHERE entity_id = ? AND category = ? AND key = ? AND status = 'active'",
                        (pref_id, now, entity_id, category.strip().lower(), key.strip())
                    )
                
                conn.execute(
                    """
                    INSERT INTO hm_preferences (id, entity_id, category, key, value, confidence, evidence_count, status, superseded_by, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (pref_id, entity_id, category.strip().lower(), key.strip(), redacted_value, confidence, evidence_count, status, now, now)
                )
                conn.commit()

                # Mandated Provenance Log
                from backend.core.memory_governance import MemoryGovernance
                MemoryGovernance.log_provenance(
                    memory_id=pref_id,
                    memory_type="semantic",
                    source="user",
                    created_by="user",
                    confidence=confidence,
                    metadata={"preference_key": key.strip(), "preference_category": category.strip().lower()}
                )

                return pref_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_preferences(cls, entity_id: str, category: Optional[str] = None, min_confidence: float = 0.5) -> list[dict[str, Any]]:
        """Retrieves user-approved preferences (status = 'active') passing the relevance floor."""
        conn = cls._get_sqlite_conn()
        try:
            if category:
                rows = conn.execute(
                    "SELECT * FROM hm_preferences WHERE entity_id = ? AND category = ? AND status = 'active' AND confidence >= ?",
                    (entity_id, category.strip().lower(), min_confidence)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM hm_preferences WHERE entity_id = ? AND status = 'active' AND confidence >= ?",
                    (entity_id, min_confidence)
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def get_preference_history(cls, entity_id: str, category: str, key: str) -> list[dict[str, Any]]:
        """Retrieves the history (active + superseded/rejected) of a preference key."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hm_preferences WHERE entity_id = ? AND category = ? AND key = ? ORDER BY created_at DESC",
                (entity_id, category.strip().lower(), key.strip())
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---------------------------------------------------------------------------
    # Candidate Memory Queue & Promotion Gates
    # ---------------------------------------------------------------------------
    @classmethod
    def add_candidate(cls, entity_id: str, candidate_type: str, key: str, value: str, ttl_seconds: int = 2592000) -> str:
        """Adds candidate preference/goal/project, transitioning status to pending_approval if evidence threshold is met.
        
        Default candidate_ttl is 30 days (2592000s).
        """
        is_sensitive, matched_cat = classify_sensitive_content(value)
        if is_sensitive:
            raise ValueError(f"Content blocked due to sensitive category: {matched_cat}")

        now = time.time()
        cand_id = str(uuid.uuid4())
        expires_at = now + ttl_seconds
        redacted_value = redact_secrets(value)
        
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Check for existing pending candidate
                row = conn.execute(
                    """
                    SELECT id, evidence_count FROM hm_relationship_candidates 
                    WHERE entity_id = ? AND candidate_type = ? AND key = ? AND (status = 'pending' OR status = 'pending_approval')
                    """,
                    (entity_id, candidate_type.strip().lower(), key.strip())
                ).fetchone()
                
                if row:
                    cand_id = row["id"]
                    new_evidence = row["evidence_count"] + 1
                    # Evidence >= 2 transitions candidate to 'pending_approval' (waits for user confirmation, does NOT auto-promote)
                    new_status = "pending_approval" if new_evidence >= 2 else "pending"
                    conn.execute(
                        """
                        UPDATE hm_relationship_candidates 
                        SET evidence_count = ?, value = ?, status = ?, expires_at = ?
                        WHERE id = ?
                        """,
                        (new_evidence, redacted_value, new_status, expires_at, cand_id)
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO hm_relationship_candidates (id, entity_id, candidate_type, key, value, evidence_count, status, expires_at)
                        VALUES (?, ?, ?, ?, ?, 1, 'pending', ?)
                        """,
                        (cand_id, entity_id, candidate_type.strip().lower(), key.strip(), redacted_value, expires_at)
                    )
                
                conn.commit()
                return cand_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def _promote_candidate_direct(cls, conn: sqlite3.Connection, cand_data: dict[str, Any]) -> None:
        """Promotes candidate to active after user confirmation, logging provenance."""
        now = time.time()
        
        if cand_data["candidate_type"] == "preference":
            category = "general"
            key_name = cand_data["key"]
            if ":" in key_name:
                category, key_name = key_name.split(":", 1)
                
            pref_id = str(uuid.uuid4())
            # Set older preferences to superseded with contradiction link
            conn.execute(
                "UPDATE hm_preferences SET status = 'superseded', superseded_by = ?, updated_at = ? WHERE entity_id = ? AND category = ? AND key = ? AND status = 'active'",
                (pref_id, now, cand_data["entity_id"], category, key_name)
            )

            conn.execute(
                """
                INSERT INTO hm_preferences (id, entity_id, category, key, value, confidence, evidence_count, status, superseded_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 0.8, ?, 'active', NULL, ?, ?)
                """,
                (pref_id, cand_data["entity_id"], category, key_name, cand_data["value"], cand_data["evidence_count"], now, now)
            )
            
            # Record mandated provenance in memory governance
            from backend.core.memory_governance import MemoryGovernance
            MemoryGovernance.log_provenance(
                memory_id=pref_id,
                memory_type="semantic",
                source="user",
                created_by="broker",
                confidence=0.8,
                derived_from=[cand_data["id"]],
                metadata={"promoted_from_candidate": cand_data["id"], "preference_key": key_name}
            )
            
        elif cand_data["candidate_type"] == "goal":
            goal_id = str(uuid.uuid4())
            # Goals require explicit user statement or manual confirmation to approve.
            # Insert goal as active because it is user-confirmed here.
            conn.execute(
                """
                INSERT INTO hm_user_goals (id, entity_id, goal, status, priority, approved, created_at, updated_at)
                VALUES (?, ?, ?, 'active', 0.5, 1, ?, ?)
                """,
                (goal_id, cand_data["entity_id"], cand_data["value"], now, now)
            )

            # Record provenance
            from backend.core.memory_governance import MemoryGovernance
            MemoryGovernance.log_provenance(
                memory_id=goal_id,
                memory_type="strategic",
                source="user",
                created_by="broker",
                confidence=1.0,
                derived_from=[cand_data["id"]],
                metadata={"promoted_from_candidate": cand_data["id"]}
            )
            
        conn.execute(
            "UPDATE hm_relationship_candidates SET status = 'promoted' WHERE id = ?",
            (cand_data["id"],)
        )

    @classmethod
    def list_candidates(cls, entity_id: str, status: str = "pending") -> list[dict[str, Any]]:
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hm_relationship_candidates WHERE entity_id = ? AND status = ?",
                (entity_id, status.strip().lower())
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def promote_candidate_manually(cls, candidate_id: str) -> bool:
        """Promotes candidate memory with user confirmation, archiving active ones as superseded."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM hm_relationship_candidates WHERE id = ? AND (status = 'pending' OR status = 'pending_approval')", 
                    (candidate_id,)
                ).fetchone()
                if not row:
                    return False
                cls._promote_candidate_direct(conn, dict(row))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()

    @classmethod
    def reject_candidate(cls, candidate_id: str) -> bool:
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cur = conn.execute(
                    "UPDATE hm_relationship_candidates SET status = 'rejected' WHERE id = ? AND (status = 'pending' OR status = 'pending_approval')",
                    (candidate_id,)
                )
                conn.commit()
                return cur.rowcount > 0
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()

    # ---------------------------------------------------------------------------
    # Projects and Goals CRUD (with Relevance Floor & Provenance Logs)
    # ---------------------------------------------------------------------------
    @classmethod
    def add_project(cls, entity_id: str, project_name: str, description: str, status: str = "active", priority: float = 0.5) -> str:
        is_sensitive, matched_cat = classify_sensitive_content(description)
        if is_sensitive:
            raise ValueError(f"Content blocked due to sensitive category: {matched_cat}")

        now = time.time()
        proj_id = str(uuid.uuid4())
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_projects (id, entity_id, project_name, status, priority, description, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(entity_id, project_name) DO UPDATE SET
                        status = excluded.status,
                        priority = excluded.priority,
                        description = excluded.description,
                        updated_at = excluded.updated_at
                    """,
                    (proj_id, entity_id, project_name.strip(), status, priority, redact_secrets(description.strip()), now, now)
                )
                conn.commit()
                return proj_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_projects(cls, entity_id: str, min_priority: float = 0.3) -> list[dict[str, Any]]:
        """Retrieves projects matching the minimum priority relevance floor."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hm_projects WHERE entity_id = ? AND priority >= ? ORDER BY priority DESC", 
                (entity_id, min_priority)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def add_user_goal(cls, entity_id: str, goal: str, priority: float = 0.5, approved: bool = False) -> str:
        """Add user goal. Enforces that goals default to approved=False unless explicitly requested."""
        is_sensitive, matched_cat = classify_sensitive_content(goal)
        if is_sensitive:
            raise ValueError(f"Content blocked due to sensitive category: {matched_cat}")

        now = time.time()
        goal_id = str(uuid.uuid4())
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_user_goals (id, entity_id, goal, status, priority, approved, created_at, updated_at)
                    VALUES (?, ?, ?, 'active', ?, ?, ?, ?)
                    """,
                    (goal_id, entity_id, redact_secrets(goal.strip()), priority, int(approved), now, now)
                )
                conn.commit()

                # Record provenance
                from backend.core.memory_governance import MemoryGovernance
                MemoryGovernance.log_provenance(
                    memory_id=goal_id,
                    memory_type="strategic",
                    source="user",
                    created_by="user",
                    confidence=1.0 if approved else 0.5,
                    metadata={"goal_text": goal.strip()}
                )

                return goal_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_user_goals(cls, entity_id: str, include_unapproved: bool = False, min_priority: float = 0.3) -> list[dict[str, Any]]:
        """Retrieves goals matching the minimum priority relevance floor."""
        conn = cls._get_sqlite_conn()
        try:
            if include_unapproved:
                rows = conn.execute(
                    "SELECT * FROM hm_user_goals WHERE entity_id = ? AND priority >= ? ORDER BY priority DESC", 
                    (entity_id, min_priority)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM hm_user_goals WHERE entity_id = ? AND approved = 1 AND priority >= ? ORDER BY priority DESC", 
                    (entity_id, min_priority)
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def approve_goal(cls, goal_id: str) -> bool:
        """Explicitly approves a goal, setting approved = 1."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cur = conn.execute(
                    "UPDATE hm_user_goals SET approved = 1, updated_at = ? WHERE id = ?",
                    (now, goal_id)
                )
                conn.commit()
                return cur.rowcount > 0
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()

    # ---------------------------------------------------------------------------
    # Interaction History (Temporal Log & Compaction)
    # ---------------------------------------------------------------------------
    @classmethod
    def add_history(cls, entity_id: str, summary: str, importance: float = 0.5) -> str:
        """Stores a relationship summary note in plaintext."""
        is_sensitive, matched_cat = classify_sensitive_content(summary)
        if is_sensitive:
            raise ValueError(f"Content blocked due to sensitive category: {matched_cat}")

        now = time.time()
        hist_id = str(uuid.uuid4())
        redacted_summary = redact_secrets(summary)
        
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_relationship_history (id, entity_id, summary, importance, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (hist_id, entity_id, redacted_summary, importance, now)
                )
                conn.commit()
                return hist_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_history(cls, entity_id: str, limit: int = 10, min_importance: float = 0.3) -> list[dict[str, Any]]:
        """Retrieves history logs matching the minimum importance relevance floor."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hm_relationship_history WHERE entity_id = ? AND importance >= ? ORDER BY created_at DESC LIMIT ?",
                (entity_id, min_importance, limit)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def compact_history(cls, entity_id: str, age_days: int = 30) -> bool:
        """Consolidates history entries older than age_days into a single monthly summary note, deleting the source entries."""
        now = time.time()
        cutoff = now - (age_days * 86400)
        
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Query original entries older than cutoff (excluding already compacted ones)
                rows = conn.execute(
                    "SELECT * FROM hm_relationship_history WHERE entity_id = ? AND created_at <= ? AND is_compacted = 0 ORDER BY created_at ASC",
                    (entity_id, cutoff)
                ).fetchall()
                
                if len(rows) < 2:
                    return False
                
                # Consolidate summaries
                summaries = [r["summary"] for r in rows]
                merged_summary = f"Compacted monthly summary ({len(summaries)} entries):\n" + "\n".join(f"- {s}" for s in summaries)
                max_importance = max(r["importance"] for r in rows)
                new_importance = min(1.0, max_importance + 0.1)
                
                # Delete compacted entries
                ids_to_delete = [r["id"] for r in rows]
                placeholders = ", ".join("?" for _ in ids_to_delete)
                conn.execute(
                    f"DELETE FROM hm_relationship_history WHERE id IN ({placeholders})",
                    ids_to_delete
                )
                
                # Write consolidated entry
                new_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO hm_relationship_history (id, entity_id, summary, importance, created_at, is_compacted)
                    VALUES (?, ?, ?, ?, ?, 1)
                    """,
                    (new_id, entity_id, merged_summary, new_importance, cutoff)
                )
                conn.commit()
                
                # Log provenance for consolidation
                from backend.core.memory_governance import MemoryGovernance
                MemoryGovernance.log_provenance(
                    memory_id=new_id,
                    memory_type="semantic",
                    source="system",
                    created_by="broker",
                    confidence=1.0,
                    derived_from=ids_to_delete,
                    metadata={"compaction_event": "monthly", "entries_count": len(ids_to_delete)}
                )
                
                return True
            except Exception as e:
                conn.rollback()
                log_event(f"relationship_memory: history compaction failed: {e}")
                return False
            finally:
                conn.close()

    # ---------------------------------------------------------------------------
    # Ephemeral Emotional State (Decaying, Opt-In)
    # ---------------------------------------------------------------------------
    @classmethod
    def set_emotional_state(cls, entity_id: str, emotion: str, confidence: float, ttl_seconds: int = 259200) -> str | None:
        """Sets a temporary emotional state (expires in default 72h). Gated by opt-in preference."""
        if not cls.is_emotional_logging_enabled(entity_id):
            return None

        is_sensitive, matched_cat = classify_sensitive_content(emotion)
        if is_sensitive:
            raise ValueError(f"Content blocked due to sensitive category: {matched_cat}")
            
        now = time.time()
        state_id = str(uuid.uuid4())
        redacted_emotion = redact_secrets(emotion)
        expires_at = now + ttl_seconds
        
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute("DELETE FROM hm_emotional_state WHERE entity_id = ?", (entity_id,))
                conn.execute(
                    """
                    INSERT INTO hm_emotional_state (id, entity_id, emotion, confidence, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (state_id, entity_id, redacted_emotion, confidence, expires_at, now)
                )
                conn.commit()
                return state_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_emotional_state(cls, entity_id: str) -> dict[str, Any] | None:
        """Retrieves user's active emotional state if not expired."""
        now = time.time()
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT * FROM hm_emotional_state WHERE entity_id = ? AND expires_at > ?",
                (entity_id, now)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ---------------------------------------------------------------------------
    # Maintenance: GC, Right-To-Forget & Purging
    # ---------------------------------------------------------------------------
    @classmethod
    def run_cleanup_sweep(cls) -> dict[str, int]:
        """Prunes expired candidates and emotional states, returning count of deleted records.
        
        Expired candidates are transitioned to status='expired' to preserve history.
        """
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # 1. Prune expired candidates: update status to 'expired' instead of deleting
                cands_expired = conn.execute(
                    "UPDATE hm_relationship_candidates SET status = 'expired' WHERE expires_at <= ? AND (status = 'pending' OR status = 'pending_approval')",
                    (now,)
                ).rowcount
                
                # 2. Prune expired emotional states
                emotions_deleted = conn.execute(
                    "DELETE FROM hm_emotional_state WHERE expires_at <= ?",
                    (now,)
                ).rowcount
                
                conn.commit()
                return {
                    "expired_candidates_pruned": cands_expired,
                    "expired_emotions_pruned": emotions_deleted
                }
            except Exception as e:
                conn.rollback()
                log_event(f"relationship_memory: cleanup sweep failed: {e}")
                return {"expired_candidates_pruned": 0, "expired_emotions_pruned": 0}
            finally:
                conn.close()

    @classmethod
    def forget(cls, entity_id: str) -> bool:
        """Right-to-forget: Cascading delete of entity and all related tables."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Check existence
                row = conn.execute("SELECT id FROM hm_entities WHERE id = ?", (entity_id,)).fetchone()
                if not row:
                    return False
                # Explicit delete from all dependent tables for absolute robustness
                conn.execute("DELETE FROM hm_preferences WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM hm_projects WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM hm_user_goals WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM hm_relationship_history WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM hm_relationship_candidates WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM hm_emotional_state WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM hm_entities WHERE id = ?", (entity_id,))
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                log_event(f"relationship_memory: failed to forget entity {entity_id}: {e}")
                return False
            finally:
                conn.close()
