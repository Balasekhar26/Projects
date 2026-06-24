from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event


class ReflectionMemory:
    """Reflection Memory Subsystem (Layer 8).
    
    Acts as a closed-loop behavioral controller. Audits logs/traces, manages candidate reflections,
    A/B test interventions, and active guardrails under strict safety constraints.
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
                CREATE TABLE IF NOT EXISTS hm_reflections (
                    id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    category TEXT NOT NULL, -- 'RETRIEVAL', 'REASONING', 'TOOLING', 'ALIGNMENT', 'SAFETY', 'PERFORMANCE', 'SUCCESS'
                    problem TEXT NOT NULL,
                    cause TEXT NOT NULL,
                    improvement TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_count INTEGER DEFAULT 1,
                    source_count INTEGER DEFAULT 1,
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    active_guardrails TEXT NOT NULL DEFAULT '[]',
                    source_window_days INTEGER DEFAULT 7,
                    status TEXT NOT NULL DEFAULT 'pending' -- 'pending', 'testing', 'accepted', 'rejected', 'expired'
                );
                CREATE INDEX IF NOT EXISTS idx_hm_reflections_status ON hm_reflections(status);
                CREATE INDEX IF NOT EXISTS idx_hm_reflections_category ON hm_reflections(category);

                CREATE TABLE IF NOT EXISTS hm_interventions (
                    id TEXT PRIMARY KEY,
                    reflection_id TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    experiment_name TEXT NOT NULL,
                    change_applied TEXT NOT NULL,
                    metric_before REAL,
                    metric_after REAL,
                    result TEXT DEFAULT 'neutral', -- 'success', 'failure', 'neutral'
                    FOREIGN KEY (reflection_id) REFERENCES hm_reflections(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_hm_interventions_reflection ON hm_interventions(reflection_id);

                CREATE TABLE IF NOT EXISTS hm_guardrails (
                    id TEXT PRIMARY KEY,
                    source_reflection_id TEXT NOT NULL,
                    rule TEXT NOT NULL,
                    priority REAL NOT NULL DEFAULT 0.5,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    active INTEGER DEFAULT 1,
                    FOREIGN KEY (source_reflection_id) REFERENCES hm_reflections(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_hm_guardrails_active ON hm_guardrails(active);

                -- ============================================================
                -- STEP 12: SELF-REFLECTION TABLES
                -- ============================================================
                CREATE TABLE IF NOT EXISTS hm_reflection_observations (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    domain TEXT NOT NULL CHECK (domain IN ('memory', 'retrieval', 'communication', 'planning', 'security', 'authority', 'approval', 'permissions', 'capability_management', 'risk_management', 'identity_verification')),
                    action_type TEXT NOT NULL,
                    outcome TEXT NOT NULL CHECK (outcome IN ('SUCCESS', 'FAILURE', 'USER_CORRECTION', 'UNKNOWN')),
                    context_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_refl_obs_domain ON hm_reflection_observations(domain, outcome);

                CREATE TABLE IF NOT EXISTS hm_reflection_patterns (
                    id TEXT PRIMARY KEY,
                    pattern_signature TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    total_occurrences INTEGER DEFAULT 1 NOT NULL,
                    success_rate REAL NOT NULL CHECK (success_rate BETWEEN 0.0 AND 1.0),
                    independent_sessions_count INTEGER NOT NULL,
                    last_observed REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS hm_reflection_hypotheses (
                    id TEXT PRIMARY KEY,
                    pattern_id TEXT,
                    domain TEXT NOT NULL CHECK (domain IN ('memory', 'retrieval', 'communication', 'planning', 'security', 'authority', 'approval', 'permissions', 'capability_management', 'risk_management', 'identity_verification')),
                    statement TEXT NOT NULL,
                    predicted_metric_change TEXT NOT NULL,
                    confidence_lower_bound REAL NOT NULL CHECK (confidence_lower_bound BETWEEN 0.0 AND 1.0),
                    confidence_upper_bound REAL NOT NULL CHECK (confidence_upper_bound BETWEEN 0.0 AND 1.0),
                    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'promoted', 'rejected', 'expired')),
                    is_verified INTEGER DEFAULT 0 CHECK (is_verified IN (0, 1)),
                    is_approved INTEGER DEFAULT 0 CHECK (is_approved IN (0, 1)),
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    evidence_cutoff_timestamp REAL,
                    FOREIGN KEY (pattern_id) REFERENCES hm_reflection_patterns(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_refl_hyp_status ON hm_reflection_hypotheses(status);

                CREATE TABLE IF NOT EXISTS hm_reflection_reports (
                    id TEXT PRIMARY KEY,
                    execution_date TEXT NOT NULL UNIQUE,
                    interactions_count INTEGER NOT NULL,
                    serialized_report_json TEXT NOT NULL,
                    reviewer_id TEXT,
                    review_status TEXT DEFAULT 'pending' CHECK (review_status IN ('pending', 'approved', 'rejected')),
                    reviewed_at REAL
                );

                CREATE TABLE IF NOT EXISTS hm_reflection_drift_alerts (
                    id TEXT PRIMARY KEY,
                    detected_at REAL NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity REAL NOT NULL CHECK (severity BETWEEN 0.0 AND 1.0),
                    description TEXT NOT NULL,
                    resolved INTEGER DEFAULT 0 CHECK (resolved IN (0, 1))
                );

                -- ============================================================
                -- STEP 13: GOAL ADAPTATION PROPOSALS TABLE
                -- ============================================================
                CREATE TABLE IF NOT EXISTS hm_goal_adaptation_proposals (
                    id TEXT PRIMARY KEY,
                    hypothesis_id TEXT,
                    goal_id TEXT NOT NULL,
                    suggested_action TEXT NOT NULL CHECK (suggested_action IN ('PAUSE', 'ABANDON', 'DEPRIORITIZE', 'DELAY', 'RE-ROUTE')),
                    reason TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
                    FOREIGN KEY (hypothesis_id) REFERENCES hm_reflection_hypotheses(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_refl_goal_adap_status ON hm_goal_adaptation_proposals(status);
                """
            )
            
            # Ensure columns exist for schema updates
            columns_ref = {row[1] for row in conn.execute("PRAGMA table_info(hm_reflections)")}
            if "source_count" not in columns_ref:
                conn.execute("ALTER TABLE hm_reflections ADD COLUMN source_count INTEGER DEFAULT 1")
            if "sources_json" not in columns_ref:
                conn.execute("ALTER TABLE hm_reflections ADD COLUMN sources_json TEXT NOT NULL DEFAULT '[]'")
            if "active_guardrails" not in columns_ref:
                conn.execute("ALTER TABLE hm_reflections ADD COLUMN active_guardrails TEXT NOT NULL DEFAULT '[]'")
                
            columns_hyp = {row[1] for row in conn.execute("PRAGMA table_info(hm_reflection_hypotheses)")}
            if "evidence_cutoff_timestamp" not in columns_hyp:
                conn.execute("ALTER TABLE hm_reflection_hypotheses ADD COLUMN evidence_cutoff_timestamp REAL")

            conn.commit()

    @classmethod
    def propose_reflection(
        cls,
        category: str,
        problem: str,
        cause: str,
        improvement: str,
        confidence: float,
        source_window_days: int = 7,
        source_type: str = "conversation"
    ) -> str:
        """Adds a candidate reflection, or increments evidence_count if a duplicate pending/testing one exists."""
        category_upper = category.strip().upper()
        allowed_categories = {"RETRIEVAL", "REASONING", "TOOLING", "ALIGNMENT", "SAFETY", "PERFORMANCE", "SUCCESS"}
        if category_upper not in allowed_categories:
            raise ValueError(f"Invalid reflection category: {category}. Must be one of {allowed_categories}")

        norm_problem = " ".join(problem.strip().lower().split())
        now = time.time()
        
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Query active guardrails at proposal time
                active_g_rows = conn.execute(
                    "SELECT id FROM hm_guardrails WHERE active = 1 AND expires_at > ?",
                    (now,)
                ).fetchall()
                active_g_ids = [r["id"] for r in active_g_rows]

                # Scan existing pending/testing reflections for a normalized match
                rows = conn.execute(
                    "SELECT * FROM hm_reflections WHERE category = ? AND status IN ('pending', 'testing')",
                    (category_upper,)
                ).fetchall()
                
                match_id = None
                existing_count = 1
                existing_confidence = 0.0
                existing_sources = []
                existing_g_ids = []
                
                for r in rows:
                    existing_norm = " ".join(r["problem"].strip().lower().split())
                    if existing_norm == norm_problem:
                        match_id = r["id"]
                        existing_count = r["evidence_count"]
                        existing_confidence = r["confidence"]
                        try:
                            existing_sources = json.loads(r["sources_json"])
                        except Exception:
                            existing_sources = []
                        try:
                            existing_g_ids = json.loads(r["active_guardrails"])
                        except Exception:
                            existing_g_ids = []
                        break
                
                if match_id:
                    new_conf = max(existing_confidence, confidence)
                    if source_type not in existing_sources:
                        existing_sources.append(source_type)
                    # Merge active guardrails
                    for gid in active_g_ids:
                        if gid not in existing_g_ids:
                            existing_g_ids.append(gid)

                    conn.execute(
                        """
                        UPDATE hm_reflections
                        SET evidence_count = ?,
                            source_count = ?,
                            sources_json = ?,
                            active_guardrails = ?,
                            confidence = ?,
                            created_at = ?
                        WHERE id = ?
                        """,
                        (existing_count + 1, len(existing_sources), json.dumps(existing_sources),
                         json.dumps(existing_g_ids), new_conf, now, match_id)
                    )
                    conn.commit()
                    return match_id
                else:
                    ref_id = str(uuid.uuid4())
                    sources = [source_type]
                    conn.execute(
                        """
                        INSERT INTO hm_reflections (
                            id, created_at, category, problem, cause, improvement,
                            confidence, evidence_count, source_count, sources_json,
                            active_guardrails, source_window_days, status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?, 'pending')
                        """,
                        (ref_id, now, category_upper, problem.strip(), cause.strip(),
                         improvement.strip(), confidence, json.dumps(sources),
                         json.dumps(active_g_ids), source_window_days)
                    )
                    conn.commit()
                    return ref_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_reflection(cls, reflection_id: str) -> dict[str, Any] | None:
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM hm_reflections WHERE id = ?", (reflection_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @classmethod
    def list_reflections(cls, status: Optional[str] = None) -> list[dict[str, Any]]:
        conn = cls._get_sqlite_conn()
        try:
            if status:
                rows = conn.execute("SELECT * FROM hm_reflections WHERE status = ? ORDER BY created_at DESC", (status.strip().lower(),)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM hm_reflections ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def start_experiment(cls, reflection_id: str, experiment_name: str, change_applied: str, metric_before: float) -> str:
        """Transitions reflection to testing and records intervention, requiring source_count >= 2."""
        now = time.time()
        intervention_id = str(uuid.uuid4())
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT status, source_count FROM hm_reflections WHERE id = ?", (reflection_id,)).fetchone()
                if not row:
                    raise ValueError(f"Reflection {reflection_id} not found.")
                if row["status"] != "pending":
                    raise ValueError(f"Reflection {reflection_id} is not in pending state (currently: {row['status']}).")
                if row["source_count"] < 2:
                    raise ValueError(f"Reflection requires at least 2 independent source types to test (current: {row['source_count']}).")
                
                conn.execute(
                    "UPDATE hm_reflections SET status = 'testing' WHERE id = ?",
                    (reflection_id,)
                )
                
                conn.execute(
                    """
                    INSERT INTO hm_interventions (
                        id, reflection_id, started_at, ended_at, experiment_name,
                        change_applied, metric_before, metric_after, result
                    )
                    VALUES (?, ?, ?, NULL, ?, ?, ?, NULL, 'neutral')
                    """,
                    (intervention_id, reflection_id, now, experiment_name.strip(), change_applied.strip(), metric_before)
                )
                conn.commit()
                return intervention_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def conclude_experiment(cls, intervention_id: str, metric_after: float, result: str) -> bool:
        """Concludes the intervention experiment.
        
        If 'success', reflection is 'accepted'.
        If 'failure' or 'neutral', reflection is 'rejected' (reverting guardrails).
        """
        if result not in {"success", "failure", "neutral"}:
            raise ValueError(f"Invalid result: {result}")
            
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT * FROM hm_interventions WHERE id = ?", (intervention_id,)).fetchone()
                if not row:
                    return False
                reflection_id = row["reflection_id"]
                
                conn.execute(
                    """
                    UPDATE hm_interventions
                    SET ended_at = ?, metric_after = ?, result = ?
                    WHERE id = ?
                    """,
                    (now, metric_after, result, intervention_id)
                )
                
                new_status = "accepted" if result == "success" else "rejected"
                conn.execute(
                    "UPDATE hm_reflections SET status = ? WHERE id = ?",
                    (new_status, reflection_id)
                )
                
                # If rejected, disable any guardrails associated with this reflection
                if new_status == "rejected":
                    conn.execute(
                        "UPDATE hm_guardrails SET active = 0 WHERE source_reflection_id = ?",
                        (reflection_id,)
                    )
                    
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()

    @classmethod
    def create_guardrail(cls, reflection_id: str, rule: str, priority: float = 0.5, ttl_seconds: int = 604800) -> str:
        """Creates a prompt guardrail linked to an accepted reflection under safety checks."""
        now = time.time()
        expires_at = now + ttl_seconds
        gid = str(uuid.uuid4())
        
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT status FROM hm_reflections WHERE id = ?", (reflection_id,)).fetchone()
                if not row:
                    raise ValueError("Source reflection not found.")
                if row["status"] != "accepted":
                    raise ValueError(f"Guardrail can only be created from an accepted reflection (currently: {row['status']}).")
                
                # Contradiction Check
                active_rules = conn.execute("SELECT rule FROM hm_guardrails WHERE active = 1").fetchall()
                for ar in active_rules:
                    if cls._is_contradictory(ar["rule"], rule):
                        raise ValueError(f"Guardrail conflicts with existing active guardrail: {ar['rule']}")
                
                # Hard Cap of 5 active guardrails
                active_g = conn.execute(
                    "SELECT id FROM hm_guardrails WHERE active = 1 ORDER BY priority ASC, created_at ASC"
                ).fetchall()
                if len(active_g) >= 5:
                    retire_id = active_g[0]["id"]
                    conn.execute("UPDATE hm_guardrails SET active = 0 WHERE id = ?", (retire_id,))
                    log_event(f"reflection_memory: retired guardrail {retire_id} to enforce active cap of 5.")
                
                conn.execute(
                    """
                    INSERT INTO hm_guardrails (id, source_reflection_id, rule, priority, created_at, expires_at, active)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    """,
                    (gid, reflection_id, rule.strip(), priority, now, expires_at)
                )
                conn.commit()
                return gid
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @staticmethod
    def _is_contradictory(rule1: str, rule2: str) -> bool:
        r1 = rule1.lower()
        r2 = rule2.lower()
        contradictions = [
            ("concise", "detailed"),
            ("concise", "verbose"),
            ("brief", "explain deeply"),
            ("brief", "deep technical explanation"),
            ("fast", "slow"),
            ("strict", "relaxed"),
            ("free-only", "paid-only")
        ]
        for w1, w2 in contradictions:
            if (w1 in r1 and w2 in r2) or (w2 in r1 and w1 in r2):
                return True
        return False

    @classmethod
    def list_active_guardrails(cls) -> list[dict[str, Any]]:
        now = time.time()
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM hm_guardrails WHERE active = 1 AND expires_at > ? ORDER BY priority DESC, created_at DESC",
                (now,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def inject_guardrails(cls, prompt: str) -> str:
        """Appends active unexpired guardrails to the end of a prompt."""
        now = time.time()
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT rule FROM hm_guardrails WHERE active = 1 AND expires_at > ? ORDER BY priority DESC, created_at DESC",
                (now,)
            ).fetchall()
            if not rows:
                return prompt
            rules_block = "\n".join(f"- {r['rule']}" for r in rows)
            return f"{prompt}\n\n[Active Guardrails]:\n{rules_block}"
        finally:
            conn.close()

    @classmethod
    def run_cleanup_sweep(cls) -> dict[str, int]:
        """Transitions expired reflections and guardrails to deactivated states."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cur = conn.execute(
                    """
                    UPDATE hm_reflections
                    SET status = 'expired'
                    WHERE status IN ('pending', 'testing') AND (created_at + source_window_days * 86400) <= ?
                    """,
                    (now,)
                )
                reflections_expired = cur.rowcount
                
                cur_g = conn.execute(
                    "UPDATE hm_guardrails SET active = 0 WHERE active = 1 AND expires_at <= ?",
                    (now,)
                )
                guardrails_expired = cur_g.rowcount
                
                conn.commit()
                return {
                    "reflections_expired": reflections_expired,
                    "guardrails_expired": guardrails_expired
                }
            except Exception as e:
                conn.rollback()
                log_event(f"reflection_memory: cleanup sweep failed: {e}")
                return {"reflections_expired": 0, "guardrails_expired": 0}
            finally:
                conn.close()

    @classmethod
    def clear_all(cls) -> None:
        """Purges all records in Layer 8. Used primarily for resets and testing."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute("DELETE FROM hm_guardrails")
                conn.execute("DELETE FROM hm_interventions")
                conn.execute("DELETE FROM hm_reflections")
                conn.execute("DELETE FROM hm_reflection_observations")
                conn.execute("DELETE FROM hm_reflection_patterns")
                conn.execute("DELETE FROM hm_reflection_hypotheses")
                conn.execute("DELETE FROM hm_reflection_reports")
                conn.execute("DELETE FROM hm_reflection_drift_alerts")
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    # =========================================================================
    # STEP 12: SELF-REFLECTION PERSISTENCE APIs
    # =========================================================================

    @classmethod
    def add_reflection_observation(
        cls,
        session_id: str,
        domain: str,
        action_type: str,
        outcome: str,
        context_json: str,
    ) -> str:
        """Logs an un-deduplicated raw interaction metric to observations table."""
        _VALID_DOMAINS = {
            "memory", "retrieval", "communication", "planning", 
            "security", "authority", "approval", "permissions", 
            "capability_management", "risk_management", "identity_verification"
        }
        if domain not in _VALID_DOMAINS:
            raise ValueError(f"Protected-Core violation: Domain '{domain}' is invalid.")

        # RF5 Isolation: 'security' etc. domains generate a drift alarm and throw ValueError
        _PROTECTED_DOMAINS = {
            "security", "authority", "approval", "permissions", 
            "capability_management", "risk_management", "identity_verification"
        }
        if domain in _PROTECTED_DOMAINS:
            cls.raise_drift_alert(
                alert_type="SECURITY_POSTURE_INTERFERENCE",
                severity=1.0,
                description=f"Attempted observation write blocked on protected core domain '{domain}'."
            )
            raise ValueError(f"Protected-Core Isolation: Writing observations for domain '{domain}' is forbidden.")

        obs_id = str(uuid.uuid4())
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_reflection_observations
                        (id, session_id, timestamp, domain, action_type, outcome, context_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (obs_id, session_id, now, domain, action_type, outcome, context_json)
                )
                conn.commit()
                return obs_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def add_reflection_pattern(
        cls,
        signature: str,
        description: str,
        success_rate: float,
        independent_sessions: int,
        occurrences: int = 1,
    ) -> str:
        pat_id = str(uuid.uuid4())
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Upsert on signature uniqueness
                existing = conn.execute(
                    "SELECT id, total_occurrences FROM hm_reflection_patterns WHERE pattern_signature = ?",
                    (signature,)
                ).fetchone()

                if existing:
                    pat_id = existing["id"]
                    conn.execute(
                        """
                        UPDATE hm_reflection_patterns
                        SET total_occurrences = total_occurrences + ?,
                            success_rate = ?,
                            independent_sessions_count = ?,
                            last_observed = ?
                        WHERE id = ?
                        """,
                        (occurrences, success_rate, independent_sessions, now, pat_id)
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO hm_reflection_patterns
                            (id, pattern_signature, description, total_occurrences, success_rate, independent_sessions_count, last_observed)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (pat_id, signature, description, occurrences, success_rate, independent_sessions, now)
                    )
                conn.commit()
                return pat_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def add_reflection_hypothesis(
        cls,
        pattern_id: Optional[str],
        domain: str,
        statement: str,
        predicted_metric_change: str,
        lower_ci: float,
        upper_ci: float,
        ttl_seconds: int = 604800,
        evidence_cutoff_timestamp: Optional[float] = None,
    ) -> str:
        _VALID_DOMAINS = {
            "memory", "retrieval", "communication", "planning", 
            "security", "authority", "approval", "permissions", 
            "capability_management", "risk_management", "identity_verification"
        }
        if domain not in _VALID_DOMAINS:
            raise ValueError(f"Protected-Core violation: Domain '{domain}' is invalid.")

        # RF5 Isolation: Structural isolation checks on domain boundaries
        _PROTECTED_DOMAINS = {
            "security", "authority", "approval", "permissions", 
            "capability_management", "risk_management", "identity_verification"
        }
        if domain in _PROTECTED_DOMAINS:
            cls.raise_drift_alert(
                alert_type="SECURITY_POSTURE_INTERFERENCE",
                severity=1.0,
                description=f"Attempted hypothesis write blocked on protected core domain '{domain}'."
            )
            raise ValueError(f"Protected-Core Isolation: Refusing to store hypothesis targeting protected domain '{domain}'.")

        hyp_id = str(uuid.uuid4())
        now = time.time()
        cutoff = evidence_cutoff_timestamp if evidence_cutoff_timestamp is not None else now
        expires_at = now + ttl_seconds
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_reflection_hypotheses
                        (id, pattern_id, domain, statement, predicted_metric_change,
                         confidence_lower_bound, confidence_upper_bound, status,
                         is_verified, is_approved, created_at, expires_at, evidence_cutoff_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, 0, ?, ?, ?)
                    """,
                    (hyp_id, pattern_id, domain, statement, predicted_metric_change, lower_ci, upper_ci, now, expires_at, cutoff)
                )
                conn.commit()
                return hyp_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_hypothesis(cls, hyp_id: str) -> dict[str, Any] | None:
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM hm_reflection_hypotheses WHERE id = ?", (hyp_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @classmethod
    def raise_drift_alert(cls, alert_type: str, severity: float, description: str) -> str:
        alert_id = str(uuid.uuid4())
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_reflection_drift_alerts
                        (id, detected_at, alert_type, severity, description, resolved)
                    VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (alert_id, now, alert_type, severity, description)
                )
                conn.commit()
                return alert_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_drift_alerts(cls, include_resolved: bool = False) -> list[dict[str, Any]]:
        conn = cls._get_sqlite_conn()
        try:
            if include_resolved:
                rows = conn.execute("SELECT * FROM hm_reflection_drift_alerts ORDER BY detected_at DESC").fetchall()
            else:
                rows = conn.execute("SELECT * FROM hm_reflection_drift_alerts WHERE resolved = 0 ORDER BY detected_at DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def add_goal_adaptation_proposal(
        cls,
        hypothesis_id: Optional[str],
        goal_id: str,
        suggested_action: str,
        reason: str,
    ) -> str:
        """Step 13: Creates a read-only advisory proposal to adapt/pause a thrashed goal."""
        _VALID_ACTIONS = {"PAUSE", "ABANDON", "DEPRIORITIZE", "DELAY", "RE-ROUTE"}
        if suggested_action not in _VALID_ACTIONS:
            raise ValueError(f"Invalid suggested action: {suggested_action}")

        proposal_id = f"GAP-{uuid.uuid4().hex[:8].upper()}"
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_goal_adaptation_proposals
                        (id, hypothesis_id, goal_id, suggested_action, reason, created_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (proposal_id, hypothesis_id, goal_id, suggested_action, reason, now)
                )
                conn.commit()
                return proposal_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def list_goal_adaptation_proposals(cls, status: Optional[str] = None) -> list[dict[str, Any]]:
        """Lists goal adaptation proposals, optionally filtered by status."""
        conn = cls._get_sqlite_conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM hm_goal_adaptation_proposals WHERE status = ? ORDER BY created_at DESC",
                    (status.strip().lower(),)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM hm_goal_adaptation_proposals ORDER BY created_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def update_goal_adaptation_proposal_status(cls, proposal_id: str, status: str) -> bool:
        """Updates the status of a goal adaptation proposal ('approved' or 'rejected')."""
        status_clean = status.strip().lower()
        if status_clean not in {"approved", "rejected"}:
            raise ValueError(f"Invalid status transition: {status}")

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cursor = conn.execute(
                    "UPDATE hm_goal_adaptation_proposals SET status = ? WHERE id = ?",
                    (status_clean, proposal_id)
                )
                conn.commit()
                return cursor.rowcount > 0
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()
