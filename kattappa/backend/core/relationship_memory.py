from __future__ import annotations

import json
import math
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
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False, timeout=30.0)
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
            # Check if legacy tables exist as actual tables
            row = conn.execute("SELECT type FROM sqlite_master WHERE name = 'hm_entities'").fetchone()
            is_legacy = row and row["type"] == "table"
            
            if is_legacy:
                legacy_tables = [
                    "hm_entities", "hm_preferences", "hm_projects", "hm_user_goals",
                    "hm_trust", "hm_communication", "hm_relationship_history",
                    "hm_relationship_candidates", "hm_emotional_state",
                    "hm_observed_behaviors", "hm_channel_bindings"
                ]
                for tbl in legacy_tables:
                    try:
                        conn.execute(f"ALTER TABLE {tbl} RENAME TO tmplegacy_{tbl}")
                    except Exception:
                        pass
                conn.commit()

            conn.executescript(
                """
                -- Upgraded Step 18 Relational Tables
                CREATE TABLE IF NOT EXISTS relationship_entities (
                    entity_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL CHECK (entity_type IN ('user', 'project', 'organization', 'device', 'person', 'colleague', 'friend', 'system')),
                    name TEXT NOT NULL,
                    trust_level TEXT NOT NULL DEFAULT 'TRUST_UNVERIFIED',
                    dunbar_layer INTEGER NOT NULL DEFAULT 1 CHECK (dunbar_layer IN (0, 1, 2, 3)),
                    pinned INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS relationship_preferences (
                    preference_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    preference_key TEXT NOT NULL,
                    preference_value TEXT NOT NULL,
                    confidence_score REAL NOT NULL CHECK (confidence_score BETWEEN 0.0 AND 1.0),
                    confidence_state TEXT NOT NULL DEFAULT 'INFERRED' CHECK (confidence_state IN ('STATED', 'OBSERVED', 'INFERRED', 'CONFIRMED')),
                    evidence_count INTEGER DEFAULT 1 NOT NULL,
                    privacy_tier INTEGER NOT NULL DEFAULT 1 CHECK (privacy_tier IN (1, 2)),
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    status TEXT DEFAULT 'ACTIVE',
                    superseded_by TEXT REFERENCES relationship_preferences(preference_id) ON DELETE SET NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_rel_pref_active ON relationship_preferences(entity_id, category, preference_key) WHERE status = 'ACTIVE' OR status = 'active';

                CREATE TABLE IF NOT EXISTS relationship_goals (
                    goal_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
                    goal_title TEXT NOT NULL,
                    goal_description TEXT NOT NULL,
                    status TEXT DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'PAUSED', 'COMPLETED', 'ABANDONED', 'active', 'archived', 'completed')),
                    priority_weight REAL NOT NULL CHECK (priority_weight BETWEEN 0.0 AND 1.0),
                    confidence_score REAL NOT NULL CHECK (confidence_score BETWEEN 0.0 AND 1.0),
                    confidence_state TEXT NOT NULL DEFAULT 'INFERRED' CHECK (confidence_state IN ('STATED', 'OBSERVED', 'INFERRED', 'CONFIRMED')),
                    approved INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_rel_goals_active ON relationship_goals(entity_id, goal_title) WHERE status = 'ACTIVE' OR status = 'active';

                CREATE TABLE IF NOT EXISTS relationship_projects (
                    project_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
                    project_name TEXT NOT NULL,
                    project_type TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('planning', 'active', 'delivered', 'archived', 'backlog', 'completed')),
                    importance_weight REAL NOT NULL CHECK (importance_weight BETWEEN 0.0 AND 1.0),
                    project_description TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    last_activity_at REAL NOT NULL,
                    UNIQUE(entity_id, project_name)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_rel_proj_active ON relationship_projects(entity_id, project_name) WHERE status = 'active' OR status = 'planning';

                CREATE TABLE IF NOT EXISTS relationship_style (
                    style_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
                    attribute_key TEXT NOT NULL CHECK (attribute_key IN ('response_length', 'technical_density', 'mixed_language_ratio', 'diagram_preference', 'language', 'format', 'technical_depth', 'example_density', 'tone')),
                    attribute_value TEXT NOT NULL,
                    confidence_score REAL NOT NULL CHECK (confidence_score BETWEEN 0.0 AND 1.0),
                    confidence_state TEXT NOT NULL DEFAULT 'INFERRED' CHECK (confidence_state IN ('STATED', 'OBSERVED', 'INFERRED', 'CONFIRMED')),
                    evidence_count INTEGER DEFAULT 1,
                    source TEXT NOT NULL DEFAULT 'observed',
                    last_confirmed REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(entity_id, attribute_key)
                );

                CREATE TABLE IF NOT EXISTS relationship_trust (
                    trust_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
                    domain_space TEXT NOT NULL CHECK (domain_space IN ('CODE_EXECUTION', 'ARCHITECTURE_DESIGN', 'PROJECT_MANAGEMENT', 'OPERATIONAL_PREDICTABILITY', 'GLOBAL')),
                    trust_score REAL NOT NULL CHECK (trust_score BETWEEN 0.0 AND 1.0),
                    confidence_score REAL NOT NULL CHECK (confidence_score BETWEEN 0.0 AND 1.0),
                    interaction_count INTEGER DEFAULT 0 NOT NULL,
                    last_updated_at REAL NOT NULL,
                    UNIQUE(entity_id, domain_space)
                );

                CREATE TABLE IF NOT EXISTS relationship_topics (
                    topic_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
                    topic_name TEXT NOT NULL,
                    frequency_count INTEGER DEFAULT 1 NOT NULL,
                    normalized_importance REAL NOT NULL CHECK (normalized_importance BETWEEN 0.0 AND 1.0),
                    last_seen_at REAL NOT NULL,
                    UNIQUE(entity_id, topic_name)
                );

                CREATE TABLE IF NOT EXISTS relationship_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
                    target_type TEXT NOT NULL CHECK (target_type IN ('PREFERENCE', 'GOAL', 'PROJECT', 'STYLE', 'TRUST', 'TOPIC', 'BEHAVIOR')),
                    target_id TEXT NOT NULL,
                    source_episode_id TEXT NOT NULL,
                    observation_text TEXT NOT NULL,
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS relationship_conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
                    target_type TEXT NOT NULL CHECK (target_type IN ('PREFERENCE', 'GOAL', 'PROJECT', 'STYLE')),
                    target_key TEXT NOT NULL,
                    old_value TEXT NOT NULL,
                    new_value TEXT NOT NULL,
                    evidence_source_id TEXT NOT NULL,
                    resolution_state TEXT DEFAULT 'PENDING' CHECK (resolution_state IN ('PENDING', 'RESOLVED_NEW', 'RESOLVED_OLD', 'DISCARDED')),
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS relationship_aliases (
                    alias TEXT PRIMARY KEY,
                    canonical_entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS relationship_history (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
                    summary TEXT NOT NULL,
                    importance REAL NOT NULL DEFAULT 0.5,
                    created_at REAL NOT NULL,
                    is_compacted INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS relationship_candidates (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
                    candidate_type TEXT NOT NULL,
                    key TEXT NOT NULL DEFAULT '',
                    value TEXT NOT NULL,
                    evidence_count INTEGER DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending',
                    expires_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS relationship_emotional_state (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
                    emotion TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS relationship_observed_behaviors (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
                    observation TEXT NOT NULL,
                    evidence_ids TEXT NOT NULL DEFAULT '[]',
                    evidence_count INTEGER DEFAULT 1,
                    confidence REAL NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    source TEXT NOT NULL DEFAULT 'observed',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS relationship_channel_bindings (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
                    channel_type TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    verification_state TEXT NOT NULL DEFAULT 'unverified',
                    created_at REAL NOT NULL,
                    verified_at REAL,
                    UNIQUE(channel_type, channel_id)
                );

                CREATE INDEX IF NOT EXISTS idx_rel_pref_lookup ON relationship_preferences(status, confidence_score DESC);
                CREATE INDEX IF NOT EXISTS idx_rel_proj_activity ON relationship_projects(status, last_activity_at DESC);
                CREATE INDEX IF NOT EXISTS idx_rel_topics_freq ON relationship_topics(frequency_count DESC, last_seen_at DESC);
                CREATE INDEX IF NOT EXISTS idx_rel_pref_entity ON relationship_preferences(entity_id);
                CREATE INDEX IF NOT EXISTS idx_rel_goals_entity ON relationship_goals(entity_id);
                CREATE INDEX IF NOT EXISTS idx_rel_proj_entity ON relationship_projects(entity_id);
                CREATE INDEX IF NOT EXISTS idx_rel_comm_entity ON relationship_style(entity_id);
                CREATE INDEX IF NOT EXISTS idx_rel_trust_entity ON relationship_trust(entity_id);

                -- Backward compatibility Views
                DROP VIEW IF EXISTS hm_entities;
                CREATE VIEW hm_entities AS
                SELECT entity_id AS id, entity_type, name, trust_level, pinned, created_at, updated_at
                FROM relationship_entities;

                DROP VIEW IF EXISTS hm_preferences;
                CREATE VIEW hm_preferences AS
                SELECT preference_id AS id, entity_id, category, preference_key AS key, preference_value AS value, confidence_score AS confidence, evidence_count, status, superseded_by, first_seen AS created_at, last_seen AS updated_at
                FROM relationship_preferences;

                DROP VIEW IF EXISTS hm_projects;
                CREATE VIEW hm_projects AS
                SELECT project_id AS id, entity_id, project_name, status, importance_weight AS priority, project_description AS description, created_at, last_activity_at AS updated_at
                FROM relationship_projects;

                DROP VIEW IF EXISTS hm_user_goals;
                CREATE VIEW hm_user_goals AS
                SELECT goal_id AS id, entity_id, goal_description AS goal, status, priority_weight AS priority, approved, created_at, updated_at
                FROM relationship_goals;

                DROP VIEW IF EXISTS hm_trust;
                CREATE VIEW hm_trust AS
                SELECT trust_id AS id, entity_id, trust_score, confidence_score AS confidence, interaction_count AS evidence_count, last_updated_at AS last_updated
                FROM relationship_trust
                WHERE domain_space = 'GLOBAL';

                DROP VIEW IF EXISTS hm_communication;
                CREATE VIEW hm_communication AS
                SELECT style_id AS id, entity_id, attribute_key AS style_key, attribute_value AS style_value, confidence_score AS confidence, evidence_count, source, last_confirmed, created_at, updated_at
                FROM relationship_style;

                DROP VIEW IF EXISTS hm_relationship_history;
                CREATE VIEW hm_relationship_history AS
                SELECT id, entity_id, summary, importance, created_at, is_compacted
                FROM relationship_history;

                DROP VIEW IF EXISTS hm_relationship_candidates;
                CREATE VIEW hm_relationship_candidates AS
                SELECT id, entity_id, candidate_type, key, value, evidence_count, status, expires_at
                FROM relationship_candidates;

                DROP VIEW IF EXISTS hm_emotional_state;
                CREATE VIEW hm_emotional_state AS
                SELECT id, entity_id, emotion, confidence, expires_at, created_at
                FROM relationship_emotional_state;

                DROP VIEW IF EXISTS hm_observed_behaviors;
                CREATE VIEW hm_observed_behaviors AS
                SELECT id, entity_id, observation, evidence_ids, evidence_count, confidence, is_active, source, created_at, updated_at
                FROM relationship_observed_behaviors;

                DROP VIEW IF EXISTS hm_channel_bindings;
                CREATE VIEW hm_channel_bindings AS
                SELECT id, entity_id, channel_type, channel_id, verification_state, created_at, verified_at
                FROM relationship_channel_bindings;

                -- View triggers for backward compatibility with COALESCE to protect partial updates
                DROP TRIGGER IF EXISTS trg_hm_entities_insert;
                CREATE TRIGGER trg_hm_entities_insert INSTEAD OF INSERT ON hm_entities BEGIN
                    INSERT INTO relationship_entities (entity_id, entity_type, name, trust_level, pinned, created_at, updated_at)
                    VALUES (new.id, new.entity_type, new.name, new.trust_level, COALESCE(new.pinned, 0), new.created_at, new.updated_at);
                END;
                DROP TRIGGER IF EXISTS trg_hm_entities_update;
                CREATE TRIGGER trg_hm_entities_update INSTEAD OF UPDATE ON hm_entities BEGIN
                    UPDATE relationship_entities
                    SET entity_type = new.entity_type, name = new.name, trust_level = new.trust_level, pinned = COALESCE(new.pinned, pinned), updated_at = new.updated_at
                    WHERE entity_id = old.id;
                END;
                DROP TRIGGER IF EXISTS trg_hm_entities_delete;
                CREATE TRIGGER trg_hm_entities_delete INSTEAD OF DELETE ON hm_entities BEGIN
                    DELETE FROM relationship_entities WHERE entity_id = old.id;
                END;

                DROP TRIGGER IF EXISTS trg_hm_preferences_insert;
                CREATE TRIGGER trg_hm_preferences_insert INSTEAD OF INSERT ON hm_preferences BEGIN
                    INSERT INTO relationship_preferences (preference_id, entity_id, category, preference_key, preference_value, confidence_score, confidence_state, evidence_count, privacy_tier, first_seen, last_seen, status, superseded_by)
                    VALUES (new.id, new.entity_id, new.category, new.key, new.value, new.confidence, 'INFERRED', COALESCE(new.evidence_count, 1), 1, new.created_at, new.updated_at, COALESCE(new.status, 'active'), new.superseded_by);
                END;
                DROP TRIGGER IF EXISTS trg_hm_preferences_update;
                CREATE TRIGGER trg_hm_preferences_update INSTEAD OF UPDATE ON hm_preferences BEGIN
                    UPDATE relationship_preferences
                    SET category = new.category, preference_key = new.key, preference_value = new.value, confidence_score = new.confidence, evidence_count = COALESCE(new.evidence_count, evidence_count), status = COALESCE(new.status, status), superseded_by = new.superseded_by, first_seen = COALESCE(new.created_at, first_seen), last_seen = new.updated_at
                    WHERE preference_id = old.id;
                END;
                DROP TRIGGER IF EXISTS trg_hm_preferences_delete;
                CREATE TRIGGER trg_hm_preferences_delete INSTEAD OF DELETE ON hm_preferences BEGIN
                    DELETE FROM relationship_preferences WHERE preference_id = old.id;
                END;

                DROP TRIGGER IF EXISTS trg_hm_projects_insert;
                CREATE TRIGGER trg_hm_projects_insert INSTEAD OF INSERT ON hm_projects BEGIN
                    INSERT INTO relationship_projects (project_id, entity_id, project_name, project_type, status, importance_weight, project_description, created_at, last_activity_at)
                    VALUES (new.id, new.entity_id, new.project_name, 'general', new.status, new.priority, new.description, new.created_at, new.updated_at);
                END;
                DROP TRIGGER IF EXISTS trg_hm_projects_update;
                CREATE TRIGGER trg_hm_projects_update INSTEAD OF UPDATE ON hm_projects BEGIN
                    UPDATE relationship_projects
                    SET project_name = new.project_name, status = new.status, importance_weight = new.priority, project_description = new.description, created_at = COALESCE(new.created_at, created_at), last_activity_at = new.updated_at
                    WHERE project_id = old.id;
                END;
                DROP TRIGGER IF EXISTS trg_hm_projects_delete;
                CREATE TRIGGER trg_hm_projects_delete INSTEAD OF DELETE ON hm_projects BEGIN
                    DELETE FROM relationship_projects WHERE project_id = old.id;
                END;

                DROP TRIGGER IF EXISTS trg_hm_user_goals_insert;
                CREATE TRIGGER trg_hm_user_goals_insert INSTEAD OF INSERT ON hm_user_goals BEGIN
                    INSERT INTO relationship_goals (goal_id, entity_id, goal_title, goal_description, status, priority_weight, confidence_score, confidence_state, approved, created_at, updated_at)
                    VALUES (new.id, new.entity_id, SUBSTR(new.goal, 1, 60), new.goal, new.status, new.priority, 1.0, 'CONFIRMED', COALESCE(new.approved, 0), new.created_at, new.updated_at);
                END;
                DROP TRIGGER IF EXISTS trg_hm_user_goals_update;
                CREATE TRIGGER trg_hm_user_goals_update INSTEAD OF UPDATE ON hm_user_goals BEGIN
                    UPDATE relationship_goals
                    SET goal_description = new.goal, goal_title = SUBSTR(new.goal, 1, 60), status = new.status, priority_weight = new.priority, approved = COALESCE(new.approved, approved), created_at = COALESCE(new.created_at, created_at), updated_at = new.updated_at
                    WHERE goal_id = old.id;
                END;
                DROP TRIGGER IF EXISTS trg_hm_user_goals_delete;
                CREATE TRIGGER trg_hm_user_goals_delete INSTEAD OF DELETE ON hm_user_goals BEGIN
                    DELETE FROM relationship_goals WHERE goal_id = old.id;
                END;

                DROP TRIGGER IF EXISTS trg_hm_trust_insert;
                CREATE TRIGGER trg_hm_trust_insert INSTEAD OF INSERT ON hm_trust BEGIN
                    INSERT INTO relationship_trust (trust_id, entity_id, domain_space, trust_score, confidence_score, interaction_count, last_updated_at)
                    VALUES (new.id, new.entity_id, 'GLOBAL', new.trust_score, new.confidence, new.evidence_count, new.last_updated);
                END;
                DROP TRIGGER IF EXISTS trg_hm_trust_update;
                CREATE TRIGGER trg_hm_trust_update INSTEAD OF UPDATE ON hm_trust BEGIN
                    UPDATE relationship_trust
                    SET trust_score = new.trust_score, confidence_score = new.confidence, interaction_count = COALESCE(new.evidence_count, interaction_count), last_updated_at = new.last_updated
                    WHERE trust_id = old.id;
                END;
                DROP TRIGGER IF EXISTS trg_hm_trust_delete;
                CREATE TRIGGER trg_hm_trust_delete INSTEAD OF DELETE ON hm_trust BEGIN
                    DELETE FROM relationship_trust WHERE trust_id = old.id;
                END;

                DROP TRIGGER IF EXISTS trg_hm_communication_insert;
                CREATE TRIGGER trg_hm_communication_insert INSTEAD OF INSERT ON hm_communication BEGIN
                    INSERT INTO relationship_style (style_id, entity_id, attribute_key, attribute_value, confidence_score, confidence_state, evidence_count, source, last_confirmed, created_at, updated_at)
                    VALUES (new.id, new.entity_id, new.style_key, new.style_value, new.confidence, 'INFERRED', new.evidence_count, new.source, new.last_confirmed, new.created_at, new.updated_at);
                END;
                DROP TRIGGER IF EXISTS trg_hm_communication_update;
                CREATE TRIGGER trg_hm_communication_update INSTEAD OF UPDATE ON hm_communication BEGIN
                    UPDATE relationship_style
                    SET attribute_key = new.style_key, attribute_value = new.style_value, confidence_score = new.confidence, evidence_count = COALESCE(new.evidence_count, evidence_count), source = new.source, last_confirmed = new.last_confirmed, updated_at = new.updated_at
                    WHERE style_id = old.id;
                END;
                DROP TRIGGER IF EXISTS trg_hm_communication_delete;
                CREATE TRIGGER trg_hm_communication_delete INSTEAD OF DELETE ON hm_communication BEGIN
                    DELETE FROM relationship_style WHERE style_id = old.id;
                END;

                DROP TRIGGER IF EXISTS trg_hm_relationship_history_insert;
                CREATE TRIGGER trg_hm_relationship_history_insert INSTEAD OF INSERT ON hm_relationship_history BEGIN
                    INSERT INTO relationship_history (id, entity_id, summary, importance, created_at, is_compacted)
                    VALUES (new.id, new.entity_id, new.summary, new.importance, new.created_at, COALESCE(new.is_compacted, 0));
                END;
                DROP TRIGGER IF EXISTS trg_hm_relationship_history_update;
                CREATE TRIGGER trg_hm_relationship_history_update INSTEAD OF UPDATE ON hm_relationship_history BEGIN
                    UPDATE relationship_history
                    SET summary = new.summary, importance = new.importance, created_at = COALESCE(new.created_at, created_at), is_compacted = COALESCE(new.is_compacted, is_compacted)
                    WHERE id = old.id;
                END;
                DROP TRIGGER IF EXISTS trg_hm_relationship_history_delete;
                CREATE TRIGGER trg_hm_relationship_history_delete INSTEAD OF DELETE ON hm_relationship_history BEGIN
                    DELETE FROM relationship_history WHERE id = old.id;
                END;

                DROP TRIGGER IF EXISTS trg_hm_relationship_candidates_insert;
                CREATE TRIGGER trg_hm_relationship_candidates_insert INSTEAD OF INSERT ON hm_relationship_candidates BEGIN
                    INSERT INTO relationship_candidates (id, entity_id, candidate_type, key, value, evidence_count, status, expires_at)
                    VALUES (new.id, new.entity_id, new.candidate_type, new.key, new.value, COALESCE(new.evidence_count, 1), COALESCE(new.status, 'pending'), new.expires_at);
                END;
                DROP TRIGGER IF EXISTS trg_hm_relationship_candidates_update;
                CREATE TRIGGER trg_hm_relationship_candidates_update INSTEAD OF UPDATE ON hm_relationship_candidates BEGIN
                    UPDATE relationship_candidates
                    SET candidate_type = new.candidate_type, key = new.key, value = new.value, evidence_count = COALESCE(new.evidence_count, evidence_count), status = COALESCE(new.status, status), expires_at = new.expires_at
                    WHERE id = old.id;
                END;
                DROP TRIGGER IF EXISTS trg_hm_relationship_candidates_delete;
                CREATE TRIGGER trg_hm_relationship_candidates_delete INSTEAD OF DELETE ON hm_relationship_candidates BEGIN
                    DELETE FROM relationship_candidates WHERE id = old.id;
                END;

                DROP TRIGGER IF EXISTS trg_hm_emotional_state_insert;
                CREATE TRIGGER trg_hm_emotional_state_insert INSTEAD OF INSERT ON hm_emotional_state BEGIN
                    INSERT INTO relationship_emotional_state (id, entity_id, emotion, confidence, expires_at, created_at)
                    VALUES (new.id, new.entity_id, new.emotion, new.confidence, new.expires_at, new.created_at);
                END;
                DROP TRIGGER IF EXISTS trg_hm_emotional_state_update;
                CREATE TRIGGER trg_hm_emotional_state_update INSTEAD OF UPDATE ON hm_emotional_state BEGIN
                    UPDATE relationship_emotional_state
                    SET emotion = new.emotion, confidence = new.confidence, expires_at = new.expires_at
                    WHERE id = old.id;
                END;
                DROP TRIGGER IF EXISTS trg_hm_emotional_state_delete;
                CREATE TRIGGER trg_hm_emotional_state_delete INSTEAD OF DELETE ON hm_emotional_state BEGIN
                    DELETE FROM relationship_emotional_state WHERE id = old.id;
                END;

                DROP TRIGGER IF EXISTS trg_hm_observed_behaviors_insert;
                CREATE TRIGGER trg_hm_observed_behaviors_insert INSTEAD OF INSERT ON hm_observed_behaviors BEGIN
                    INSERT INTO relationship_observed_behaviors (id, entity_id, observation, evidence_ids, evidence_count, confidence, is_active, source, created_at, updated_at)
                    VALUES (new.id, new.entity_id, new.observation, COALESCE(new.evidence_ids, '[]'), COALESCE(new.evidence_count, 1), new.confidence, COALESCE(new.is_active, 1), COALESCE(new.source, 'observed'), new.created_at, new.updated_at);
                END;
                DROP TRIGGER IF EXISTS trg_hm_observed_behaviors_update;
                CREATE TRIGGER trg_hm_observed_behaviors_update INSTEAD OF UPDATE ON hm_observed_behaviors BEGIN
                    UPDATE relationship_observed_behaviors
                    SET observation = new.observation, evidence_ids = COALESCE(new.evidence_ids, evidence_ids), evidence_count = COALESCE(new.evidence_count, evidence_count), confidence = new.confidence, is_active = COALESCE(new.is_active, is_active), source = COALESCE(new.source, source), updated_at = new.updated_at
                    WHERE id = old.id;
                END;
                DROP TRIGGER IF EXISTS trg_hm_observed_behaviors_delete;
                CREATE TRIGGER trg_hm_observed_behaviors_delete INSTEAD OF DELETE ON hm_observed_behaviors BEGIN
                    DELETE FROM relationship_observed_behaviors WHERE id = old.id;
                END;

                DROP TRIGGER IF EXISTS trg_hm_channel_bindings_insert;
                CREATE TRIGGER trg_hm_channel_bindings_insert INSTEAD OF INSERT ON hm_channel_bindings BEGIN
                    INSERT INTO relationship_channel_bindings (id, entity_id, channel_type, channel_id, verification_state, created_at, verified_at)
                    VALUES (new.id, new.entity_id, new.channel_type, new.channel_id, COALESCE(new.verification_state, 'unverified'), new.created_at, new.verified_at);
                END;
                DROP TRIGGER IF EXISTS trg_hm_channel_bindings_update;
                CREATE TRIGGER trg_hm_channel_bindings_update INSTEAD OF UPDATE ON hm_channel_bindings BEGIN
                    UPDATE relationship_channel_bindings
                    SET entity_id = new.entity_id, verification_state = COALESCE(new.verification_state, verification_state), verified_at = new.verified_at
                    WHERE id = old.id;
                END;
                DROP TRIGGER IF EXISTS trg_hm_channel_bindings_delete;
                CREATE TRIGGER trg_hm_channel_bindings_delete INSTEAD OF DELETE ON hm_channel_bindings BEGIN
                    DELETE FROM relationship_channel_bindings WHERE id = old.id;
                END;
                """
            )

            # Copy data if migrating
            if is_legacy:
                try:
                    conn.execute("INSERT INTO relationship_entities (entity_id, entity_type, name, trust_level, pinned, created_at, updated_at) SELECT id, entity_type, name, trust_level, pinned, created_at, updated_at FROM tmplegacy_hm_entities")
                    conn.execute("INSERT INTO relationship_preferences (preference_id, entity_id, category, preference_key, preference_value, confidence_score, evidence_count, status, superseded_by, first_seen, last_seen) SELECT id, entity_id, category, key, value, confidence, evidence_count, status, superseded_by, created_at, updated_at FROM tmplegacy_hm_preferences")
                    conn.execute("INSERT INTO relationship_projects (project_id, entity_id, project_name, project_type, status, importance_weight, project_description, created_at, last_activity_at) SELECT id, entity_id, project_name, 'general', status, priority, description, created_at, updated_at FROM tmplegacy_hm_projects")
                    conn.execute("INSERT INTO relationship_goals (goal_id, entity_id, goal_title, goal_description, status, priority_weight, confidence_score, confidence_state, approved, created_at, updated_at) SELECT id, entity_id, SUBSTR(goal, 1, 60), goal, status, priority, 1.0, 'CONFIRMED', approved, created_at, updated_at FROM tmplegacy_hm_user_goals")
                    conn.execute("INSERT INTO relationship_trust (trust_id, entity_id, domain_space, trust_score, confidence_score, interaction_count, last_updated_at) SELECT id, entity_id, 'GLOBAL', trust_score, confidence, evidence_count, last_updated FROM tmplegacy_hm_trust")
                    conn.execute("INSERT INTO relationship_style (style_id, entity_id, attribute_key, attribute_value, confidence_score, confidence_state, evidence_count, source, last_confirmed, created_at, updated_at) SELECT id, entity_id, style_key, style_value, confidence, 'INFERRED', evidence_count, source, last_confirmed, created_at, updated_at FROM tmplegacy_hm_communication")
                    conn.execute("INSERT INTO relationship_history (id, entity_id, summary, importance, created_at, is_compacted) SELECT id, entity_id, summary, importance, created_at, is_compacted FROM tmplegacy_hm_relationship_history")
                    conn.execute("INSERT INTO relationship_candidates (id, entity_id, candidate_type, key, value, evidence_count, status, expires_at) SELECT id, entity_id, candidate_type, key, value, evidence_count, status, expires_at FROM tmplegacy_hm_relationship_candidates")
                    conn.execute("INSERT INTO relationship_emotional_state (id, entity_id, emotion, confidence, expires_at, created_at) SELECT id, entity_id, emotion, confidence, expires_at, created_at FROM tmplegacy_hm_emotional_state")
                    conn.execute("INSERT INTO relationship_observed_behaviors (id, entity_id, observation, evidence_ids, evidence_count, confidence, is_active, source, created_at, updated_at) SELECT id, entity_id, observation, evidence_ids, evidence_count, confidence, is_active, source, created_at, updated_at FROM tmplegacy_hm_observed_behaviors")
                    conn.execute("INSERT INTO relationship_channel_bindings (id, entity_id, channel_type, channel_id, verification_state, created_at, verified_at) SELECT id, entity_id, channel_type, channel_id, verification_state, created_at, verified_at FROM tmplegacy_hm_channel_bindings")
                    
                    legacy_tables = [
                        "hm_entities", "hm_preferences", "hm_projects", "hm_user_goals",
                        "hm_trust", "hm_communication", "hm_relationship_history",
                        "hm_relationship_candidates", "hm_emotional_state",
                        "hm_observed_behaviors", "hm_channel_bindings"
                    ]
                    for tbl in legacy_tables:
                        conn.execute(f"DROP TABLE tmplegacy_{tbl}")
                except Exception as e:
                    log_event(f"relationship_memory: schema migration error: {e}")
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
                "SELECT preference_value FROM relationship_preferences WHERE entity_id = ? AND category = 'privacy' AND preference_key = 'emotional_logging_enabled' AND (status = 'active' OR status = 'ACTIVE')",
                (user_entity_id,)
            ).fetchone()
            if not row:
                return False
            return row["preference_value"].lower() in {"1", "true", "yes"}
        except Exception:
            return False
        finally:
            conn.close()

    # ---------------------------------------------------------------------------
    # Entities CRUD
    # ---------------------------------------------------------------------------
    @classmethod
    def get_or_create_entity(cls, entity_id: str, name: str, entity_type: str = "user", trust_level: str = "TRUST_UNVERIFIED") -> dict[str, Any]:
        """Gets or creates an entity under relationship_entities."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT entity_id AS id, entity_type, name, trust_level, dunbar_layer, pinned, created_at, updated_at FROM relationship_entities WHERE entity_id = ?", (entity_id,)).fetchone()
                if row:
                    return dict(row)
                conn.execute(
                    """
                    INSERT INTO relationship_entities (entity_id, entity_type, name, trust_level, pinned, created_at, updated_at)
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
            row = conn.execute("SELECT entity_id AS id, entity_type, name, trust_level, dunbar_layer, pinned, created_at, updated_at FROM relationship_entities WHERE entity_id = ?", (entity_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @classmethod
    def update_entity_trust(cls, entity_id: str, trust_level: str) -> bool:
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT entity_type FROM relationship_entities WHERE entity_id = ?", (entity_id,)).fetchone()
                if not row:
                    return False
                conn.execute(
                    "UPDATE relationship_entities SET trust_level = ?, updated_at = ? WHERE entity_id = ?",
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

    @classmethod
    def update_entity_dunbar_layer(cls, entity_id: str, layer: int) -> bool:
        """Update the Dunbar layer of an entity (0 to 3)."""
        if layer not in (0, 1, 2, 3):
            raise ValueError("Dunbar layer must be 0, 1, 2, or 3")
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cur = conn.execute(
                    "UPDATE relationship_entities SET dunbar_layer = ?, updated_at = ? WHERE entity_id = ?",
                    (layer, time.time(), entity_id)
                )
                conn.commit()
                return cur.rowcount > 0
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()

    # ---------------------------------------------------------------------------
    # Preferences CRUD with Lifecycle, Contradiction Chaining & Provenance Logs
    # ---------------------------------------------------------------------------
    @classmethod
    def _enforce_dunbar_limit(cls, conn: sqlite3.Connection, entity_id: str) -> None:
        # Get entity's dunbar_layer (default to 1)
        row_ent = conn.execute("SELECT dunbar_layer FROM relationship_entities WHERE entity_id = ?", (entity_id,)).fetchone()
        layer = row_ent["dunbar_layer"] if row_ent else 1
        
        limit = {3: 100, 2: 50, 1: 15, 0: 5}.get(layer, 15)
        
        # Select active preferences, sorted by confidence_score (lowest first) and then oldest last_seen
        active_rows = conn.execute(
            "SELECT preference_id FROM relationship_preferences WHERE entity_id = ? AND (status = 'active' OR status = 'ACTIVE') ORDER BY confidence_score ASC, last_seen ASC",
            (entity_id,)
        ).fetchall()
        
        if len(active_rows) > limit:
            excess = len(active_rows) - limit
            for r in active_rows[:excess]:
                conn.execute(
                    "UPDATE relationship_preferences SET status = 'ARCHIVED', last_seen = ? WHERE preference_id = ?",
                    (time.time(), r["preference_id"])
                )

    @classmethod
    def _add_evidence(
        cls,
        conn: sqlite3.Connection,
        entity_id: str,
        target_type: str,
        target_id: str,
        episode_id: Optional[str],
        observation_text: Optional[str],
    ) -> None:
        if not episode_id:
            return
        now = time.time()
        evidence_id = str(uuid.uuid4())
        obs = observation_text if observation_text else f"Observed update for {target_type.lower()} {target_id}"
        conn.execute(
            """
            INSERT INTO relationship_evidence (evidence_id, entity_id, target_type, target_id, source_episode_id, observation_text, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (evidence_id, entity_id, target_type.upper(), target_id, episode_id, obs, now)
        )

    @classmethod
    def set_preference(
        cls,
        entity_id: str,
        category: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        evidence_count: int = 1,
        status: str = "active",
        confidence_state: Optional[str] = None,
        privacy_tier: int = 1,
        episode_id: Optional[str] = None,
        observation_text: Optional[str] = None,
    ) -> str:
        """Stores a preference directly, implementing lifecycle state check, contradiction chaining, and provenance log."""
        is_sensitive, matched_cat = classify_sensitive_content(value)
        if is_sensitive:
            raise ValueError(f"Content blocked due to sensitive category: {matched_cat}")

        now = time.time()
        pref_id = str(uuid.uuid4())
        redacted_value = redact_secrets(value)
        
        if not confidence_state:
            confidence_state = "CONFIRMED" if confidence == 1.0 else "INFERRED"

        # Calculate consistency-frequency confidence if OBSERVED or INFERRED, and confidence is default (1.0)
        if confidence_state in ("OBSERVED", "INFERRED") and confidence == 1.0:
            with cls._lock:
                conn = cls._get_sqlite_conn()
                try:
                    aligned_rows = conn.execute(
                        "SELECT COUNT(*) FROM relationship_preferences WHERE entity_id = ? AND category = ? AND preference_key = ? AND preference_value = ?",
                        (entity_id, category.strip().lower(), key.strip(), redacted_value)
                    ).fetchone()[0]
                    total_rows = conn.execute(
                        "SELECT COUNT(*) FROM relationship_preferences WHERE entity_id = ? AND category = ? AND preference_key = ?",
                        (entity_id, category.strip().lower(), key.strip())
                    ).fetchone()[0]
                    
                    aligned = aligned_rows + evidence_count
                    contradictory = max(0, total_rows - aligned_rows)
                    
                    consistency = aligned / (aligned + contradictory) if (aligned + contradictory) > 0 else 1.0
                    frequency = aligned
                    confidence = consistency * (1.0 - math.exp(-0.08 * frequency))
                    confidence = max(0.0, min(1.0, confidence))
                except Exception:
                    pass
                finally:
                    conn.close()
            
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Find previously active row
                prev_row = conn.execute(
                    "SELECT preference_id, preference_value, evidence_count FROM relationship_preferences WHERE entity_id = ? AND category = ? AND preference_key = ? AND (status = 'active' OR status = 'ACTIVE')",
                    (entity_id, category.strip().lower(), key.strip())
                ).fetchone()
                
                old_pref_id = None
                # Check for contradiction (conflict)
                if prev_row and prev_row["preference_value"] != redacted_value:
                    if confidence < 1.0 and confidence_state not in ("CONFIRMED", "STATED"):
                        conflict_id = str(uuid.uuid4())
                        conn.execute(
                            """
                            INSERT INTO relationship_conflicts (conflict_id, entity_id, target_type, target_key, old_value, new_value, evidence_source_id, resolution_state, created_at)
                            VALUES (?, ?, 'PREFERENCE', ?, ?, ?, ?, 'PENDING', ?)
                            """,
                            (conflict_id, entity_id, f"{category}:{key}", prev_row["preference_value"], redacted_value, episode_id or f"SRC_CONF_{pref_id}", now)
                        )
                        conn.commit()
                        return conflict_id
                    else:
                        old_pref_id = prev_row["preference_id"]
                        # Pre-supersede old preference status to avoid UNIQUE index violation on insert
                        conn.execute(
                            "UPDATE relationship_preferences SET status = 'superseded', last_seen = ? WHERE preference_id = ?",
                            (now, old_pref_id)
                        )
                        # Log conflict as resolved
                        conflict_id = str(uuid.uuid4())
                        conn.execute(
                            """
                            INSERT INTO relationship_conflicts (conflict_id, entity_id, target_type, target_key, old_value, new_value, evidence_source_id, resolution_state, created_at)
                            VALUES (?, ?, 'PREFERENCE', ?, ?, ?, ?, 'RESOLVED_NEW', ?)
                            """,
                            (conflict_id, entity_id, f"{category}:{key}", prev_row["preference_value"], redacted_value, episode_id or f"SRC_CONF_{pref_id}", now)
                        )
                elif prev_row and prev_row["preference_value"] == redacted_value:
                    # Same value, update last_seen, confidence, evidence_count
                    new_evidence = prev_row["evidence_count"] + evidence_count
                    conn.execute(
                        "UPDATE relationship_preferences SET confidence_score = ?, evidence_count = ?, last_seen = ? WHERE preference_id = ?",
                        (confidence, new_evidence, now, prev_row["preference_id"])
                    )
                    cls._add_evidence(conn, entity_id, 'PREFERENCE', prev_row["preference_id"], episode_id, observation_text)
                    conn.commit()
                    return prev_row["preference_id"]

                # Insert the new preference
                conn.execute(
                    """
                    INSERT INTO relationship_preferences (preference_id, entity_id, category, preference_key, preference_value, confidence_score, confidence_state, evidence_count, privacy_tier, first_seen, last_seen, status, superseded_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (pref_id, entity_id, category.strip().lower(), key.strip(), redacted_value, confidence, confidence_state, evidence_count, privacy_tier, now, now, status)
                )

                # Link previous active row if present
                if old_pref_id:
                    conn.execute(
                        "UPDATE relationship_preferences SET superseded_by = ? WHERE preference_id = ?",
                        (pref_id, old_pref_id)
                    )

                # Add evidence log
                cls._add_evidence(conn, entity_id, 'PREFERENCE', pref_id, episode_id, observation_text)

                # Enforce Dunbar limit
                cls._enforce_dunbar_limit(conn, entity_id)

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
    def get_evidence(cls, entity_id: str, target_type: str, target_id: str) -> list[dict[str, Any]]:
        """Retrieves all evidence associated with a specific relationship item."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                """
                SELECT evidence_id AS id, entity_id, target_type, target_id, source_episode_id AS episode_id, observation_text, timestamp
                FROM relationship_evidence
                WHERE entity_id = ? AND target_type = ? AND target_id = ?
                ORDER BY timestamp DESC
                """,
                (entity_id, target_type.upper(), target_id)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def get_preferences(cls, entity_id: str, category: Optional[str] = None, min_confidence: float = 0.5) -> list[dict[str, Any]]:
        """Retrieves user-approved preferences (status = 'active') passing the relevance floor."""
        conn = cls._get_sqlite_conn()
        try:
            if category:
                rows = conn.execute(
                    """
                    SELECT preference_id AS id, entity_id, category, preference_key AS key, preference_value AS value, 
                           confidence_score AS confidence, confidence_state, evidence_count, privacy_tier, 
                           first_seen AS created_at, last_seen AS updated_at, status, superseded_by
                    FROM relationship_preferences 
                    WHERE entity_id = ? AND category = ? AND (status = 'active' OR status = 'ACTIVE') AND confidence_score >= ?
                    """,
                    (entity_id, category.strip().lower(), min_confidence)
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT preference_id AS id, entity_id, category, preference_key AS key, preference_value AS value, 
                           confidence_score AS confidence, confidence_state, evidence_count, privacy_tier, 
                           first_seen AS created_at, last_seen AS updated_at, status, superseded_by
                    FROM relationship_preferences 
                    WHERE entity_id = ? AND (status = 'active' OR status = 'ACTIVE') AND confidence_score >= ?
                    """,
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
                """
                SELECT preference_id AS id, entity_id, category, preference_key AS key, preference_value AS value, 
                       confidence_score AS confidence, confidence_state, evidence_count, privacy_tier, 
                       first_seen AS created_at, last_seen AS updated_at, status, superseded_by
                FROM relationship_preferences 
                WHERE entity_id = ? AND category = ? AND preference_key = ? 
                ORDER BY first_seen DESC
                """,
                (entity_id, category.strip().lower(), key.strip())
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def get_conflicts(cls, entity_id: str) -> list[dict[str, Any]]:
        """Retrieve all queued conflicts for an entity."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT conflict_id AS id, entity_id, target_type, target_key, old_value, new_value, evidence_source_id, resolution_state, created_at FROM relationship_conflicts WHERE entity_id = ? ORDER BY created_at DESC",
                (entity_id,)
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
                    SELECT id, evidence_count FROM relationship_candidates 
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
                        UPDATE relationship_candidates 
                        SET evidence_count = ?, value = ?, status = ?, expires_at = ?
                        WHERE id = ?
                        """,
                        (new_evidence, redacted_value, new_status, expires_at, cand_id)
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO relationship_candidates (id, entity_id, candidate_type, key, value, evidence_count, status, expires_at)
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
            
            # For manual user confirmation/promotion, the confidence score should be 1.0 (CONFIRMED state)
            confidence = 1.0

            # Set older preferences to superseded with contradiction link
            conn.execute(
                "UPDATE relationship_preferences SET status = 'superseded', superseded_by = ?, last_seen = ? WHERE entity_id = ? AND category = ? AND preference_key = ? AND (status = 'active' OR status = 'ACTIVE')",
                (pref_id, now, cand_data["entity_id"], category, key_name)
            )

            conn.execute(
                """
                INSERT INTO relationship_preferences (preference_id, entity_id, category, preference_key, preference_value, confidence_score, confidence_state, evidence_count, privacy_tier, first_seen, last_seen, status, superseded_by)
                VALUES (?, ?, ?, ?, ?, ?, 'CONFIRMED', ?, 1, ?, ?, 'active', NULL)
                """,
                (pref_id, cand_data["entity_id"], category, key_name, cand_data["value"], confidence, cand_data["evidence_count"], now, now)
            )
            
            # Record mandated provenance in memory governance
            from backend.core.memory_governance import MemoryGovernance
            MemoryGovernance.log_provenance(
                memory_id=pref_id,
                memory_type="semantic",
                source="user",
                created_by="broker",
                confidence=confidence,
                derived_from=[cand_data["id"]],
                metadata={"promoted_from_candidate": cand_data["id"], "preference_key": key_name}
            )
            
        elif cand_data["candidate_type"] == "goal":
            goal_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO relationship_goals (goal_id, entity_id, goal_title, goal_description, status, priority_weight, confidence_score, confidence_state, approved, created_at, updated_at)
                VALUES (?, ?, SUBSTR(?, 1, 60), ?, 'active', 0.5, 1.0, 'CONFIRMED', 1, ?, ?)
                """,
                (goal_id, cand_data["entity_id"], cand_data["value"], cand_data["value"], now, now)
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
            "UPDATE relationship_candidates SET status = 'promoted' WHERE id = ?",
            (cand_data["id"],)
        )

    @classmethod
    def list_candidates(cls, entity_id: str, status: str = "pending") -> list[dict[str, Any]]:
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT id, entity_id, candidate_type, key, value, evidence_count, status, expires_at FROM relationship_candidates WHERE entity_id = ? AND status = ?",
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
                    "SELECT * FROM relationship_candidates WHERE id = ? AND (status = 'pending' OR status = 'pending_approval')", 
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
                    "UPDATE relationship_candidates SET status = 'rejected' WHERE id = ? AND (status = 'pending' OR status = 'pending_approval')",
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
    def add_project(
        cls,
        entity_id: str,
        project_name: str,
        description: str,
        status: str = "active",
        priority: float = 0.5,
        episode_id: Optional[str] = None,
        observation_text: Optional[str] = None,
    ) -> str:
        is_sensitive, matched_cat = classify_sensitive_content(description)
        if is_sensitive:
            raise ValueError(f"Content blocked due to sensitive category: {matched_cat}")

        now = time.time()
        proj_id = str(uuid.uuid4())
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Retrieve existing project_id if it exists to preserve evidence link integrity
                row = conn.execute(
                    "SELECT project_id FROM relationship_projects WHERE entity_id = ? AND project_name = ?",
                    (entity_id, project_name.strip())
                ).fetchone()
                if row:
                    proj_id = row["project_id"]

                conn.execute(
                    """
                    INSERT INTO relationship_projects (project_id, entity_id, project_name, project_type, status, importance_weight, project_description, created_at, last_activity_at)
                    VALUES (?, ?, ?, 'general', ?, ?, ?, ?, ?)
                    ON CONFLICT(entity_id, project_name) DO UPDATE SET
                        status = excluded.status,
                        importance_weight = excluded.importance_weight,
                        project_description = excluded.project_description,
                        last_activity_at = excluded.last_activity_at
                    """,
                    (proj_id, entity_id, project_name.strip(), status, priority, redact_secrets(description.strip()), now, now)
                )
                cls._add_evidence(conn, entity_id, 'PROJECT', proj_id, episode_id, observation_text)
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
                """
                SELECT project_id AS id, entity_id, project_name, status, importance_weight AS priority, project_description AS description, created_at, last_activity_at AS updated_at
                FROM relationship_projects 
                WHERE entity_id = ? AND importance_weight >= ? 
                ORDER BY importance_weight DESC
                """, 
                (entity_id, min_priority)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def add_user_goal(
        cls,
        entity_id: str,
        goal: str,
        priority: float = 0.5,
        approved: bool = False,
        episode_id: Optional[str] = None,
        observation_text: Optional[str] = None,
    ) -> str:
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
                    INSERT INTO relationship_goals (goal_id, entity_id, goal_title, goal_description, status, priority_weight, confidence_score, confidence_state, approved, created_at, updated_at)
                    VALUES (?, ?, SUBSTR(?, 1, 60), ?, 'active', ?, 1.0, 'CONFIRMED', ?, ?, ?)
                    """,
                    (goal_id, entity_id, goal.strip(), redact_secrets(goal.strip()), priority, int(approved), now, now)
                )
                cls._add_evidence(conn, entity_id, 'GOAL', goal_id, episode_id, observation_text)
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
                    """
                    SELECT goal_id AS id, entity_id, goal_description AS goal, status, priority_weight AS priority, approved, created_at, updated_at 
                    FROM relationship_goals 
                    WHERE entity_id = ? AND priority_weight >= ? 
                    ORDER BY priority_weight DESC
                    """, 
                    (entity_id, min_priority)
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT goal_id AS id, entity_id, goal_description AS goal, status, priority_weight AS priority, approved, created_at, updated_at 
                    FROM relationship_goals 
                    WHERE entity_id = ? AND approved = 1 AND priority_weight >= ? 
                    ORDER BY priority_weight DESC
                    """, 
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
                    "UPDATE relationship_goals SET approved = 1, updated_at = ? WHERE goal_id = ?",
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
                    INSERT INTO relationship_history (id, entity_id, summary, importance, created_at, is_compacted)
                    VALUES (?, ?, ?, ?, ?, 0)
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
                """
                SELECT id, entity_id, summary, importance, created_at, is_compacted 
                FROM relationship_history 
                WHERE entity_id = ? AND importance >= ? 
                ORDER BY created_at DESC LIMIT ?
                """,
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
                    "SELECT id, summary, importance, created_at FROM relationship_history WHERE entity_id = ? AND created_at <= ? AND is_compacted = 0 ORDER BY created_at ASC",
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
                    f"DELETE FROM relationship_history WHERE id IN ({placeholders})",
                    ids_to_delete
                )
                
                # Write consolidated entry
                new_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO relationship_history (id, entity_id, summary, importance, created_at, is_compacted)
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
                conn.execute("DELETE FROM relationship_emotional_state WHERE entity_id = ?", (entity_id,))
                conn.execute(
                    """
                    INSERT INTO relationship_emotional_state (id, entity_id, emotion, confidence, expires_at, created_at)
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
                "SELECT id, entity_id, emotion, confidence, expires_at, created_at FROM relationship_emotional_state WHERE entity_id = ? AND expires_at > ?",
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
        """Prunes expired candidates and emotional states, and decays preference/topic confidence.
        
        Expired candidates are transitioned to status='expired' to preserve history.
        """
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # 1. Prune expired candidates: update status to 'expired' instead of deleting
                cands_expired = conn.execute(
                    "UPDATE relationship_candidates SET status = 'expired' WHERE expires_at <= ? AND (status = 'pending' OR status = 'pending_approval')",
                    (now,)
                ).rowcount
                
                # 2. Prune expired emotional states
                emotions_deleted = conn.execute(
                    "DELETE FROM relationship_emotional_state WHERE expires_at <= ?",
                    (now,)
                ).rowcount
                
                # 3. Dynamic linear time-based decay of baseline confidence scores
                # Decays active preferences by 0.001 per day
                pref_rows = conn.execute(
                    "SELECT preference_id, confidence_score, last_seen, status FROM relationship_preferences WHERE status = 'active' OR status = 'ACTIVE'"
                ).fetchall()
                for r in pref_rows:
                    delta_t = (now - r["last_seen"]) / 86400.0
                    new_conf = max(0.0, r["confidence_score"] - 0.001 * delta_t)
                    new_status = 'DECAYED' if new_conf <= 0.0 else r["status"]
                    conn.execute(
                        "UPDATE relationship_preferences SET confidence_score = ?, status = ? WHERE preference_id = ?",
                        (new_conf, new_status, r["preference_id"])
                    )

                # Decays topic interests by 0.025 per day
                topic_rows = conn.execute("SELECT topic_id, normalized_importance, last_seen_at FROM relationship_topics").fetchall()
                for r in topic_rows:
                    delta_t = (now - r["last_seen_at"]) / 86400.0
                    new_importance = max(0.0, r["normalized_importance"] - 0.025 * delta_t)
                    conn.execute(
                        "UPDATE relationship_topics SET normalized_importance = ? WHERE topic_id = ?",
                        (new_importance, r["topic_id"])
                    )
                
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
                row = conn.execute("SELECT entity_id FROM relationship_entities WHERE entity_id = ?", (entity_id,)).fetchone()
                if not row:
                    return False
                # Explicit delete from all dependent tables for absolute robustness
                conn.execute("DELETE FROM relationship_preferences WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM relationship_projects WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM relationship_goals WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM relationship_history WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM relationship_candidates WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM relationship_emotional_state WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM relationship_style WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM relationship_trust WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM relationship_observed_behaviors WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM relationship_channel_bindings WHERE entity_id = ?", (entity_id,))
                conn.execute("DELETE FROM relationship_entities WHERE entity_id = ?", (entity_id,))
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                log_event(f"relationship_memory: failed to forget entity {entity_id}: {e}")
                return False
            finally:
                conn.close()

    # =========================================================================
    # LAYER 3: Communication Style
    # =========================================================================

    @classmethod
    def set_communication_style(
        cls,
        entity_id: str,
        style_key: str,
        style_value: str,
        confidence: float = 0.8,
        source: str = "observed",
        episode_id: Optional[str] = None,
        observation_text: Optional[str] = None,
    ) -> str:
        """Set or update a communication style preference for an entity.

        Valid keys: language, format, technical_depth, example_density, tone.
        Upserts on (entity_id, style_key) — latest value wins, evidence accumulates.

        Security: Communication style data never reaches authority modules.
        It only influences presentation (formatting, language, depth).
        """
        _VALID_STYLE_KEYS = {"language", "format", "technical_depth", "example_density", "tone"}
        if style_key not in _VALID_STYLE_KEYS:
            raise ValueError(f"Invalid style_key '{style_key}'. Must be one of {_VALID_STYLE_KEYS}")

        is_sensitive, cat = classify_sensitive_content(style_value)
        if is_sensitive:
            raise ValueError(f"Communication style value blocked — sensitive category: {cat}")

        now = time.time()
        comm_id = str(uuid.uuid4())
        redacted_value = redact_secrets(style_value)

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Upsert: update evidence_count and confidence if key already exists
                existing = conn.execute(
                    "SELECT style_id, evidence_count FROM relationship_style WHERE entity_id = ? AND attribute_key = ?",
                    (entity_id, style_key)
                ).fetchone()

                if existing:
                    new_evidence = existing["evidence_count"] + 1
                    # Confidence rises with corroboration but is bounded at 0.99
                    new_conf = min(0.99, confidence + 0.02 * (1.0 - confidence))
                    conn.execute(
                        """
                        UPDATE relationship_style
                        SET attribute_value = ?, confidence_score = ?, evidence_count = ?,
                            source = ?, last_confirmed = ?, updated_at = ?
                        WHERE entity_id = ? AND attribute_key = ?
                        """,
                        (redacted_value, new_conf, new_evidence, source, now, now, entity_id, style_key)
                    )
                    comm_id = existing["style_id"]
                else:
                    conn.execute(
                        """
                        INSERT INTO relationship_style
                            (style_id, entity_id, attribute_key, attribute_value, confidence_score, confidence_state, evidence_count,
                             source, last_confirmed, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, 'INFERRED', 1, ?, ?, ?, ?)
                        """,
                        (comm_id, entity_id, style_key, redacted_value, confidence, source, now, now, now)
                    )

                cls._add_evidence(conn, entity_id, 'STYLE', comm_id, episode_id, observation_text)
                conn.commit()

                from backend.core.memory_governance import MemoryGovernance
                MemoryGovernance.log_provenance(
                    memory_id=comm_id,
                    memory_type="semantic",
                    source=source,
                    created_by="relationship_engine",
                    confidence=confidence,
                    metadata={"style_key": style_key}
                )
                return comm_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_communication_style(cls, entity_id: str) -> dict[str, str]:
        """Get communication style preferences as key-value pairs (only active ones)."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT attribute_key, attribute_value FROM relationship_style WHERE entity_id = ?",
                (entity_id,)
            ).fetchall()
            return {r["attribute_key"]: r["attribute_value"] for r in rows}
        finally:
            conn.close()

    @classmethod
    def get_communication_style_full(cls, entity_id: str) -> list[dict[str, Any]]:
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                """
                SELECT style_id AS id, entity_id, attribute_key AS style_key, attribute_value AS style_value,
                       confidence_score AS confidence, evidence_count, source, last_confirmed, created_at, updated_at
                FROM relationship_style
                WHERE entity_id = ?
                """,
                (entity_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # =========================================================================
    # LAYER 4: Trust & Reliability Metrics
    # =========================================================================

    @classmethod
    def get_trust_history(cls, entity_id: str, domain: str = "GLOBAL") -> list[dict[str, Any]]:
        """History of trust evaluations for auditing."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                """
                SELECT trust_id AS id, entity_id, domain_space, trust_score, confidence_score AS confidence, interaction_count AS evidence_count, last_updated_at AS last_updated
                FROM relationship_trust
                WHERE entity_id = ? AND domain_space = ?
                ORDER BY last_updated_at DESC
                """,
                (entity_id, domain)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def get_or_create_trust(cls, entity_id: str, domain: str = "GLOBAL") -> dict[str, Any]:
        """Get or create the trust record for this entity and domain.

        Trust score measures our *model reliability*, not the person's power.
        Range: 0.0 (no data) → 1.0 (strongly corroborated model).
        """
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute(
                    "SELECT trust_id AS id, entity_id, trust_score, confidence_score AS confidence, interaction_count AS evidence_count, last_updated_at AS last_updated FROM relationship_trust WHERE entity_id = ? AND domain_space = ?",
                    (entity_id, domain)
                ).fetchone()
                if row:
                    return dict(row)

                trust_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO relationship_trust (trust_id, entity_id, domain_space, trust_score, confidence_score, interaction_count, last_updated_at)
                    VALUES (?, ?, ?, 0.0, 0.0, 0, ?)
                    """,
                    (trust_id, entity_id, domain, now)
                )
                conn.commit()
                return {
                    "id": trust_id, "entity_id": entity_id,
                    "trust_score": 0.0, "confidence": 0.0,
                    "evidence_count": 0, "last_updated": now
                }
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def update_trust(
        cls,
        entity_id: str,
        evidence_strength: float,
        is_contradiction: bool = False,
        domain: str = "GLOBAL",
        episode_id: Optional[str] = None,
        observation_text: Optional[str] = None,
    ) -> dict[str, Any]:
        """Update the model-reliability trust score using an evidence-driven EMA."""
        _DECAY = 0.95
        _LEARNING = 0.05
        _CONF_GAIN = 0.02
        _CONF_PENALTY = 0.08  # Contradiction penalises confidence harder

        evidence_strength = max(0.0, min(1.0, evidence_strength))
        now = time.time()

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                rec = cls.get_or_create_trust(entity_id, domain)
                old_trust = rec["trust_score"]
                old_conf = rec["confidence"]
                old_count = rec["evidence_count"]

                new_trust = old_trust * _DECAY + evidence_strength * _LEARNING
                new_trust = max(0.0, min(1.0, new_trust))

                if is_contradiction:
                    new_conf = max(0.0, old_conf - _CONF_PENALTY)
                else:
                    new_conf = min(0.99, old_conf + _CONF_GAIN * (1.0 - old_conf))

                conn.execute(
                    """
                    UPDATE relationship_trust
                    SET trust_score = ?, confidence_score = ?, interaction_count = ?, last_updated_at = ?
                    WHERE entity_id = ? AND domain_space = ?
                    """,
                    (new_trust, new_conf, old_count + 1, now, entity_id, domain)
                )
                cls._add_evidence(conn, entity_id, 'TRUST', rec["id"], episode_id, observation_text)
                conn.commit()
                return {
                    "entity_id": entity_id,
                    "trust_score": round(new_trust, 4),
                    "confidence": round(new_conf, 4),
                    "evidence_count": old_count + 1,
                }
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_trust(cls, entity_id: str, domain: str = "GLOBAL") -> dict[str, Any] | None:
        """Return the current trust record for an entity (internal only — never render to users)."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT trust_id AS id, entity_id, trust_score, confidence_score AS confidence, interaction_count AS evidence_count, last_updated_at AS last_updated FROM relationship_trust WHERE entity_id = ? AND domain_space = ?",
                (entity_id, domain)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # =========================================================================
    # LAYER 8: Observed Behaviors
    # =========================================================================

    @classmethod
    def add_observed_behavior(
        cls,
        entity_id: str,
        observation: str,
        evidence_ids: list[str] | None = None,
        confidence: float = 0.5,
        source: str = "observed",
    ) -> str:
        """Record an evidence-linked behavioral observation."""
        _FORBIDDEN_LABELS = {
            "introvert", "extrovert", "analytical", "creative", "systematic",
            "impulsive", "anxious", "confident", "aggressive", "passive",
            "narcissist", "manipulative", "empathetic", "cold",
        }
        obs_lower = observation.lower()
        for label in _FORBIDDEN_LABELS:
            if label in obs_lower:
                raise ValueError(
                    f"Psychological label '{label}' detected in observation. "
                    "Store specific, evidence-linked observations only, not personality labels."
                )

        is_sensitive, cat = classify_sensitive_content(observation)
        if is_sensitive:
            raise ValueError(f"Observation blocked — sensitive category: {cat}")

        now = time.time()
        obs_id = str(uuid.uuid4())
        evidence_json = json.dumps(evidence_ids or [])
        redacted_obs = redact_secrets(observation)

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO relationship_observed_behaviors
                        (id, entity_id, observation, evidence_ids, evidence_count,
                         confidence, is_active, source, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (obs_id, entity_id, redacted_obs, evidence_json,
                     len(evidence_ids or []) or 1, confidence, source, now, now)
                )
                conn.commit()

                from backend.core.memory_governance import MemoryGovernance
                MemoryGovernance.log_provenance(
                    memory_id=obs_id,
                    memory_type="semantic",
                    source=source,
                    created_by="relationship_engine",
                    confidence=confidence,
                    derived_from=evidence_ids or [],
                    metadata={"observation": redacted_obs[:100]}
                )
                return obs_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_observed_behaviors(
        cls,
        entity_id: str,
        min_confidence: float = 0.4,
    ) -> list[dict[str, Any]]:
        """Return active observed behaviors, ordered by confidence descending."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                """
                SELECT id, entity_id, observation, evidence_ids, evidence_count, confidence, is_active, source, created_at, updated_at
                FROM relationship_observed_behaviors
                WHERE entity_id = ? AND is_active = 1 AND confidence >= ?
                ORDER BY confidence DESC, updated_at DESC
                """,
                (entity_id, min_confidence)
            ).fetchall()
            results = []
            for r in rows:
                rec = dict(r)
                rec["evidence_ids"] = json.loads(rec["evidence_ids"])
                results.append(rec)
            return results
        finally:
            conn.close()

    @classmethod
    def retract_observed_behavior(cls, obs_id: str) -> bool:
        """User-initiated retraction — deactivates an observation (right to correct)."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cur = conn.execute(
                    "UPDATE relationship_observed_behaviors SET is_active = 0, updated_at = ? WHERE id = ?",
                    (time.time(), obs_id)
                )
                conn.commit()
                return cur.rowcount > 0
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()

    # =========================================================================
    # CHANNEL BINDING (Identity Provenance)
    # =========================================================================

    @classmethod
    def bind_channel(
        cls,
        entity_id: str,
        channel_type: str,
        channel_id: str,
        verified: bool = False,
    ) -> str:
        """Bind an entity to an authenticated channel."""
        _VALID_CHANNEL_TYPES = {"system", "user_session", "email", "github", "api"}
        if channel_type not in _VALID_CHANNEL_TYPES:
            raise ValueError(f"Invalid channel_type '{channel_type}'")

        now = time.time()
        binding_id = str(uuid.uuid4())
        verification_state = "verified" if verified else "unverified"
        verified_at = now if verified else None

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO relationship_channel_bindings
                        (id, entity_id, channel_type, channel_id, verification_state, created_at, verified_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(channel_type, channel_id) DO UPDATE SET
                        entity_id = excluded.entity_id,
                        verification_state = excluded.verification_state,
                        verified_at = excluded.verified_at
                    """,
                    (binding_id, entity_id, channel_type, channel_id, verification_state, now, verified_at)
                )
                conn.commit()
                return binding_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def verify_channel(cls, channel_type: str, channel_id: str) -> bool:
        """Mark a channel binding as verified."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cur = conn.execute(
                    """
                    UPDATE relationship_channel_bindings
                    SET verification_state = 'verified', verified_at = ?
                    WHERE channel_type = ? AND channel_id = ?
                    """,
                    (now, channel_type, channel_id)
                )
                conn.commit()
                return cur.rowcount > 0
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()

    @classmethod
    def get_channel_bindings(cls, entity_id: str) -> list[dict[str, Any]]:
        """Return all channel bindings for an entity."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT id, entity_id, channel_type, channel_id, verification_state, created_at, verified_at FROM relationship_channel_bindings WHERE entity_id = ? ORDER BY created_at DESC",
                (entity_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def is_identity_verified(cls, entity_id: str) -> bool:
        """Returns True if at least one verified channel binding exists for this entity."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT id FROM relationship_channel_bindings WHERE entity_id = ? AND verification_state = 'verified' LIMIT 1",
                (entity_id,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()


# =============================================================================
# Relationship Assembler
# =============================================================================

class RelationshipAssembler:
    """Assembles a complete relationship context profile for an entity.

    Equivalent to MemoryAssembler but for the relationship engine.
    Pure read-only: gathers identity, trust metrics, communication style,
    preferences, goals, projects, history, and observed behaviors into a
    single structured payload for the planner.

    Invariant: Relationship ≠ Permission.
    This assembler's output is NEVER read by approval_engine, risk_classifier,
    capability_broker, or execution_policy. Structural isolation (no imports)
    enforces this.
    """

    @classmethod
    def assemble(
        cls,
        entity_id: str,
        history_limit: int = 5,
        min_pref_confidence: float = 0.5,
        query_text: Optional[str] = None,
    ) -> dict[str, Any] | None:
        """Build the relationship context profile.

        Returns None if the entity doesn't exist.
        """
        entity = RelationshipMemory.get_entity(entity_id)
        if not entity:
            return None

        # Identity layer
        is_verified = RelationshipMemory.is_identity_verified(entity_id)
        identity = {
            "id": entity_id,
            "name": entity["name"],
            "entity_type": entity["entity_type"],
            "is_verified": is_verified,
        }

        # Trust metrics
        trust_rec = RelationshipMemory.get_trust(entity_id)
        trust_evidence = RelationshipMemory.get_evidence(entity_id, "TRUST", trust_rec["id"]) if trust_rec else []
        trust_metrics = {
            "trust_score": round(trust_rec["trust_score"], 4) if trust_rec else 0.0,
            "confidence": round(trust_rec["confidence"], 4) if trust_rec else 0.0,
            "evidence_count": trust_rec["evidence_count"] if trust_rec else 0,
            "evidence": trust_evidence,
        }

        # History and Observed Behaviors (uncapped logs)
        history_raw = RelationshipMemory.get_history(entity_id, limit=history_limit, min_importance=0.0)
        history = [
            {"summary": h["summary"], "importance": h["importance"], "created_at": h["created_at"]}
            for h in history_raw
        ]

        behaviors_raw = RelationshipMemory.get_observed_behaviors(entity_id, min_confidence=min_pref_confidence)
        observed_behaviors = [
            {"observation": b["observation"], "evidence_ids": b["evidence_ids"], "confidence": b["confidence"]}
            for b in behaviors_raw
        ]

        # Gather Lobe Items for Prioritized Sorting & Hot/Cold Partitioning
        # Active Projects (40%)
        projects_raw = RelationshipMemory.get_projects(entity_id, min_priority=0.0)
        
        # Goals (25%)
        goals_raw = RelationshipMemory.get_user_goals(entity_id, include_unapproved=True, min_priority=0.0)
        
        # Preferences (20%)
        prefs_raw = RelationshipMemory.get_preferences(entity_id, min_confidence=0.0)
        
        # Style (10%)
        style_raw = RelationshipMemory.get_communication_style_full(entity_id)
        
        # Topics (5%)
        conn = RelationshipMemory._get_sqlite_conn()
        try:
            topics_raw = conn.execute(
                "SELECT topic_id, topic_name, frequency_count, normalized_importance, last_seen_at FROM relationship_topics WHERE entity_id = ?",
                (entity_id,)
            ).fetchall()
            topics_raw = [dict(t) for t in topics_raw]
        except Exception:
            topics_raw = []
        finally:
            conn.close()

        # Helper to check Tier 2 Privacy filter matching keywords
        def matches_query(query: str, category: str, key: str, value: str) -> bool:
            q = query.lower()
            return (category.lower() in q or 
                    key.lower() in q or 
                    any(len(w) > 3 and w in q for w in value.lower().split()))

        # Assemble and score items
        all_items = []

        # Score Projects (40%)
        for p in projects_raw:
            evidence = RelationshipMemory.get_evidence(entity_id, "PROJECT", p["id"])
            p_dict = {
                "project_name": p["project_name"],
                "status": p["status"],
                "priority": p["priority"],
                "description": p["description"],
                "evidence": evidence
            }
            score = 0.40 * p["priority"]
            all_items.append({
                "type": "project",
                "score": score,
                "data": p_dict,
                "raw": {
                    "project_name": p["project_name"],
                    "priority": p["priority"],
                    "evidence_count": len(evidence) if evidence else 1,
                    "last_seen": p["updated_at"],
                    "evidence": evidence
                }
            })

        # Score Goals (25%)
        for g in goals_raw:
            if g["status"] == "active":
                evidence = RelationshipMemory.get_evidence(entity_id, "GOAL", g["id"])
                g_dict = {
                    "goal": g["goal"],
                    "priority": g["priority"],
                    "status": g["status"],
                    "evidence": evidence
                }
                score = 0.25 * g["priority"]
                all_items.append({
                    "type": "goal",
                    "score": score,
                    "data": g_dict,
                    "raw": {
                        "goal_title": g["goal"],
                        "priority": g["priority"],
                        "evidence_count": len(evidence) if evidence else 1,
                        "last_seen": g["updated_at"],
                        "evidence": evidence
                    }
                })

        # Score Preferences (20%) - Filtering Tier 2 if not matched
        for p in prefs_raw:
            if p["privacy_tier"] == 2:
                # If Tier 2, check keyword relevance
                if not query_text or not matches_query(query_text, p["category"], p["key"], p["value"]):
                    continue
            evidence = RelationshipMemory.get_evidence(entity_id, "PREFERENCE", p["id"])
            p_dict = {
                "category": p["category"],
                "key": p["key"],
                "value": p["value"],
                "confidence": p["confidence"],
                "evidence": evidence
            }
            score = 0.20 * p["confidence"]
            all_items.append({
                "type": "preference",
                "score": score,
                "data": p_dict,
                "raw": {
                    "category": p["category"],
                    "key": p["key"],
                    "confidence": p["confidence"],
                    "evidence_count": p["evidence_count"],
                    "last_seen": p["updated_at"],
                    "evidence": evidence
                }
            })

        # Score Communication Style (10%)
        for s in style_raw:
            evidence = RelationshipMemory.get_evidence(entity_id, "STYLE", s["id"])
            s_dict = {
                "key": s["style_key"],
                "value": s["style_value"],
                "confidence": s["confidence"],
                "evidence": evidence
            }
            score = 0.10 * s["confidence"]
            all_items.append({
                "type": "style",
                "score": score,
                "data": s_dict,
                "raw": {
                    "style_key": s["style_key"],
                    "confidence": s["confidence"],
                    "evidence_count": s["evidence_count"],
                    "last_seen": s["updated_at"],
                    "evidence": evidence
                }
            })

        # Score Topics (5%)
        for t in topics_raw:
            t_dict = {"topic_name": t["topic_name"], "normalized_importance": t["normalized_importance"], "frequency_count": t["frequency_count"]}
            score = 0.05 * t["normalized_importance"]
            all_items.append({
                "type": "topic",
                "score": score,
                "data": t_dict,
                "raw": {
                    "topic_name": t["topic_name"],
                    "normalized_importance": t["normalized_importance"],
                    "evidence_count": t["frequency_count"],
                    "last_seen": t["last_seen_at"]
                }
            })

        # Sort all items by score descending
        all_items.sort(key=lambda x: x["score"], reverse=True)

        # Hot partition = top 100 items; Cold partition = anything else
        hot_items = all_items[:100]
        cold_items = all_items[100:]

        # Filter back into categorized fields
        preferences_res = []
        goals_res = []
        projects_res = []
        comm_style_res = {}
        topics_res = []

        for item in hot_items:
            itype = item["type"]
            idata = item["data"]
            if itype == "preference":
                preferences_res.append(idata)
            elif itype == "goal":
                goals_res.append(idata)
            elif itype == "project":
                projects_res.append(idata)
            elif itype == "style":
                comm_style_res[idata["key"]] = idata["value"]
            elif itype == "topic":
                topics_res.append(idata)

        # Retrieval Explainability Payload
        explainability = {
            "hot_items_count": len(hot_items),
            "cold_items_count": len(cold_items),
            "ranking": [
                {
                    "type": it["type"],
                    "score": round(it["score"], 4),
                    "evidence_count": it["raw"]["evidence_count"],
                    "last_seen": it["raw"]["last_seen"],
                    "identifier": it["raw"].get("project_name") or it["raw"].get("goal_title") or it["raw"].get("topic_name") or it["raw"].get("style_key") or f"{it['raw'].get('category')}:{it['raw'].get('key')}",
                    "evidence": it["raw"].get("evidence", [])
                }
                for it in hot_items
            ]
        }

        return {
            "identity": identity,
            "trust_metrics": trust_metrics,
            "communication_style": comm_style_res,
            "preferences": preferences_res,
            "goals": goals_res,
            "projects": projects_res,
            "history": history,
            "observed_behaviors": observed_behaviors,
            "topics": topics_res,
            "retrieval_explainability": explainability
        }

    @classmethod
    def assemble_for_session(
        cls,
        entity_id: str,
        session_summary: str | None = None,
    ) -> dict[str, Any] | None:
        """Assemble profile and optionally log a session history entry."""
        if session_summary:
            # Only log if content is non-sensitive
            try:
                RelationshipMemory.add_history(
                    entity_id=entity_id,
                    summary=session_summary,
                    importance=0.5,
                )
            except ValueError:
                pass  # Sensitive content blocked — skip silently

        return cls.assemble(entity_id)
