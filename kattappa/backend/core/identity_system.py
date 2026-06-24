# identity_system.py
# ==================
# Long-Term Identity System (LIS) Core Module for Kattappa.
# Enforces safety boundaries, stateless roleweight arbitration, truth gates,
# retractable evidence ledger, and covariance drift tracking.

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event


class IdentitySystem:
    """Long-Term Identity System (LIS) Core behavioral steering layer."""

    _lock = threading.RLock()
    _schema_ensured = False

    # Immutable value weights
    TRUTH_WEIGHT = 0.30
    ALIGNMENT_WEIGHT = 0.25
    RELIABILITY_WEIGHT = 0.20
    LEARNING_WEIGHT = 0.15
    CREATIVITY_WEIGHT = 0.10

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = config.sqlite_path.parent / "goal_memory.db"
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        with cls._lock:
            if not cls._schema_ensured:
                cls._ensure_schema(conn)
                cls._schema_ensured = True
            else:
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lis_identity_profile'")
                if not cursor.fetchone():
                    cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS lis_identity_profile (
                    profile_id TEXT PRIMARY KEY,
                    current_health_state TEXT NOT NULL DEFAULT 'EXEMPLARY',
                    composite_health_score REAL NOT NULL DEFAULT 100.0,
                    last_verification_timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lis_role_logs (
                    log_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    action_context_id TEXT NOT NULL,
                    teacher_weight_applied REAL NOT NULL,
                    engineer_weight_applied REAL NOT NULL,
                    scientist_weight_applied REAL NOT NULL,
                    builder_weight_applied REAL NOT NULL,
                    assistant_weight_applied REAL NOT NULL,
                    recorded_at REAL NOT NULL,
                    FOREIGN KEY (profile_id) REFERENCES lis_identity_profile(profile_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS lis_identity_ledger (
                    entry_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    verification_report_id TEXT NOT NULL,
                    evidence_hash TEXT NOT NULL,
                    behavioral_evidence_summary TEXT NOT NULL,
                    impacted_value TEXT NOT NULL,
                    delta_applied REAL NOT NULL,
                    recorded_at REAL NOT NULL,
                    is_retracted INTEGER NOT NULL DEFAULT 0,
                    retraction_entry_id TEXT,
                    FOREIGN KEY (profile_id) REFERENCES lis_identity_profile(profile_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS lis_drift_tracker (
                    drift_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    metric_monitored TEXT NOT NULL,
                    current_divergence_value REAL NOT NULL,
                    is_alarm_tripped INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (profile_id) REFERENCES lis_identity_profile(profile_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS lis_value_checks (
                    check_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    associated_action_id TEXT NOT NULL,
                    truthfulness_rating INTEGER NOT NULL DEFAULT 50,
                    user_alignment_rating INTEGER NOT NULL DEFAULT 50,
                    reliability_rating INTEGER NOT NULL DEFAULT 50,
                    learning_rating INTEGER NOT NULL DEFAULT 50,
                    creativity_rating INTEGER NOT NULL DEFAULT 50,
                    recorded_at REAL NOT NULL,
                    FOREIGN KEY (profile_id) REFERENCES lis_identity_profile(profile_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS lis_identity_metrics (
                    profile_id TEXT PRIMARY KEY,
                    rolling_truth_index REAL NOT NULL DEFAULT 50.0,
                    rolling_alignment_index REAL NOT NULL DEFAULT 50.0,
                    rolling_reliability_index REAL NOT NULL DEFAULT 50.0,
                    rolling_learning_index REAL NOT NULL DEFAULT 50.0,
                    rolling_creativity_index REAL NOT NULL DEFAULT 50.0,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (profile_id) REFERENCES lis_identity_profile(profile_id) ON DELETE CASCADE
                );
                """
            )
            # Seed default profile
            now = time.time()
            conn.execute(
                "INSERT OR IGNORE INTO lis_identity_profile (profile_id, current_health_state, composite_health_score, last_verification_timestamp) VALUES (?, ?, ?, ?)",
                ("default_profile", "EXEMPLARY", 100.0, now)
            )
            conn.execute(
                "INSERT OR IGNORE INTO lis_identity_metrics (profile_id, rolling_truth_index, rolling_alignment_index, rolling_reliability_index, rolling_learning_index, rolling_creativity_index, updated_at) VALUES (?, 100.0, 100.0, 100.0, 100.0, 100.0, ?)",
                ("default_profile", now)
            )
            conn.commit()

    @classmethod
    def get_or_create_profile(cls, profile_id: str = "default_profile") -> Dict[str, Any]:
        """Idempotently loads or creates the LIS profile."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM lis_identity_profile WHERE profile_id = ?", (profile_id,)).fetchone()
            if row:
                return dict(row)
            
            now = time.time()
            with cls._lock:
                conn.execute(
                    "INSERT INTO lis_identity_profile (profile_id, current_health_state, composite_health_score, last_verification_timestamp) VALUES (?, ?, ?, ?)",
                    (profile_id, "EXEMPLARY", 100.0, now)
                )
                conn.execute(
                    "INSERT INTO lis_identity_metrics (profile_id, rolling_truth_index, rolling_alignment_index, rolling_reliability_index, rolling_learning_index, rolling_creativity_index, updated_at) VALUES (?, 100.0, 100.0, 100.0, 100.0, 100.0, ?)",
                    (profile_id, now)
                )
                conn.commit()
            
            row = conn.execute("SELECT * FROM lis_identity_profile WHERE profile_id = ?", (profile_id,)).fetchone()
            return dict(row)
        finally:
            conn.close()

    # ----- Core Steering logic -----

    @classmethod
    def project_weights(cls, w: Dict[str, float], floors: Dict[str, float], ceilings: Dict[str, float]) -> Dict[str, float]:
        """Project weight dict onto floor/ceiling bounds and normalize to sum up to exactly 1.0."""
        res = {}
        for k in w:
            res[k] = max(floors.get(k, 0.0), min(ceilings.get(k, 1.0), w[k]))
        
        # Iterative adjustments
        for _ in range(10):
            s = sum(res.values())
            diff = 1.0 - s
            if abs(diff) < 1e-6:
                break
            
            adjustable = []
            for k in res:
                if diff > 0 and res[k] < ceilings.get(k, 1.0):
                    adjustable.append(k)
                elif diff < 0 and res[k] > floors.get(k, 0.0):
                    adjustable.append(k)
            if not adjustable:
                break
            
            delta = diff / len(adjustable)
            for k in adjustable:
                new_val = res[k] + delta
                res[k] = max(floors.get(k, 0.0), min(ceilings.get(k, 1.0), new_val))
        return res

    @classmethod
    def derive_role_weights(cls, context: Dict[str, Any]) -> Dict[str, float]:
        """Rule 5 & Score Blindness: Stateless weights derivation from task context.
        
        This method reads ONLY context and immutable priorities, never identity scores/health metrics.
        """
        w = {"Teacher": 0.25, "Engineer": 0.25, "Scientist": 0.25, "Builder": 0.25}
        floors = {"Teacher": 0.15, "Engineer": 0.15, "Scientist": 0.15, "Builder": 0.15}
        ceilings = {"Teacher": 0.70, "Engineer": 0.70, "Scientist": 0.70, "Builder": 0.70}

        # Context-based matching
        task = str(context.get("task_type", "")).lower()
        domain = str(context.get("domain", "")).lower()

        matched_role = None
        if any(k in task or k in domain for k in ("teach", "explain", "edu", "tutor", "instruct", "concept")):
            matched_role = "Teacher"
        elif any(k in task or k in domain for k in ("engine", "code", "coding", "debug", "architect", "database", "infra", "opt", "struct")):
            matched_role = "Engineer"
        elif any(k in task or k in domain for k in ("scien", "resear", "verif", "test", "falsif", "measur", "empir")):
            matched_role = "Scientist"
        elif any(k in task or k in domain for k in ("build", "execut", "ship", "iterat", "deploy", "packag", "releas")):
            matched_role = "Builder"

        if matched_role:
            w[matched_role] += 0.20
            floors[matched_role] = 0.35  # Domain-specific floor limit

        return cls.project_weights(w, floors, ceilings)

    @classmethod
    def evaluate_truth_gate(cls, recommendation: Dict[str, Any]) -> bool:
        """Truth Gate (Constraint check): Structurally filters unverified inputs."""
        verification = recommendation.get("verification")
        if isinstance(verification, dict):
            status = verification.get("status") or verification.get("outcome")
            if status in ("FAILED", "CONTRADICTED", "failure", "failure_rollback"):
                return False
            score = verification.get("confidence_score") or verification.get("score")
            if score is not None and float(score) < 0.50:
                return False
        
        if recommendation.get("truthfulness_rating") is not None:
            if int(recommendation["truthfulness_rating"]) < 50:
                return False
                
        return True

    # ----- Ledger & Metrics management -----

    @classmethod
    def record_behavior(
        cls,
        profile_id: str,
        action_id: str,
        verification_report_id: str,
        evidence_hash: str,
        summary: str,
        value: str,
        delta: float
    ) -> str:
        """Appends a behavior evidence log to the LIS ledger (Rule 4: score updates)."""
        entry_id = f"lis_entry_{uuid.uuid4().hex[:8]}"
        now = time.time()
        conn = cls._get_sqlite_conn()
        try:
            with cls._lock:
                conn.execute(
                    """
                    INSERT INTO lis_identity_ledger 
                    (entry_id, profile_id, action_id, verification_report_id, evidence_hash, behavioral_evidence_summary, impacted_value, delta_applied, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (entry_id, profile_id, action_id, verification_report_id, evidence_hash, summary, value.upper().strip(), delta, now)
                )
                conn.commit()
            
            cls._recalculate_rolling_metrics(profile_id)
            return entry_id
        finally:
            conn.close()

    @classmethod
    def retract_behavior(cls, profile_id: str, target_report_id: str, retraction_reason: str = "Verification overturned") -> Optional[str]:
        """Retractable Ledger: Marks original entry retracted and appends negating entry."""
        conn = cls._get_sqlite_conn()
        try:
            with cls._lock:
                row = conn.execute(
                    "SELECT * FROM lis_identity_ledger WHERE profile_id = ? AND verification_report_id = ? AND is_retracted = 0",
                    (profile_id, target_report_id)
                ).fetchone()
                if not row:
                    return None
                
                orig = dict(row)
                retraction_entry_id = f"lis_retract_{uuid.uuid4().hex[:8]}"
                now = time.time()
                
                # Mark original entry as retracted
                conn.execute(
                    "UPDATE lis_identity_ledger SET is_retracted = 1, retraction_entry_id = ? WHERE entry_id = ?",
                    (retraction_entry_id, orig["entry_id"])
                )
                
                # Append retraction negated delta entry
                negated_delta = -orig["delta_applied"]
                summary = f"RETRACTION: {retraction_reason}. Negated original entry: {orig['entry_id']}"
                conn.execute(
                    """
                    INSERT INTO lis_identity_ledger 
                    (entry_id, profile_id, action_id, verification_report_id, evidence_hash, behavioral_evidence_summary, impacted_value, delta_applied, recorded_at, is_retracted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (retraction_entry_id, profile_id, orig["action_id"], target_report_id, orig["evidence_hash"], summary, orig["impacted_value"], negated_delta, now)
                )
                conn.commit()
                
            cls._recalculate_rolling_metrics(profile_id)
            return retraction_entry_id
        finally:
            conn.close()

    @classmethod
    def _recalculate_rolling_metrics(cls, profile_id: str) -> None:
        """Recomputes scores from non-retracted ledger entries and resolves health state."""
        conn = cls._get_sqlite_conn()
        try:
            with cls._lock:
                rows = conn.execute(
                    "SELECT impacted_value, SUM(delta_applied) as total_delta FROM lis_identity_ledger WHERE profile_id = ? GROUP BY impacted_value",
                    (profile_id,)
                ).fetchall()
                
                # Baseline defaults to 100.0
                deltas = {"TRUTH": 0.0, "ALIGNMENT": 0.0, "RELIABILITY": 0.0, "LEARNING": 0.0, "CREATIVITY": 0.0}
                for r in rows:
                    val = r["impacted_value"]
                    if val in deltas:
                        deltas[val] = r["total_delta"]
                
                rolling_truth = max(0.0, min(100.0, 100.0 + deltas["TRUTH"]))
                rolling_alignment = max(0.0, min(100.0, 100.0 + deltas["ALIGNMENT"]))
                rolling_reliability = max(0.0, min(100.0, 100.0 + deltas["RELIABILITY"]))
                rolling_learning = max(0.0, min(100.0, 100.0 + deltas["LEARNING"]))
                rolling_creativity = max(0.0, min(100.0, 100.0 + deltas["CREATIVITY"]))
                
                now = time.time()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO lis_identity_metrics
                    (profile_id, rolling_truth_index, rolling_alignment_index, rolling_reliability_index, rolling_learning_index, rolling_creativity_index, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (profile_id, rolling_truth, rolling_alignment, rolling_reliability, rolling_learning, rolling_creativity, now)
                )
                
                # Formula: 0.30T + 0.25A + 0.20R + 0.15L + 0.10C
                health_score = (
                    0.30 * rolling_truth +
                    0.25 * rolling_alignment +
                    0.20 * rolling_reliability +
                    0.15 * rolling_learning +
                    0.10 * rolling_creativity
                )
                
                if health_score >= 90.0:
                    state = "EXEMPLARY"
                elif health_score >= 75.0:
                    state = "STRONG"
                elif health_score >= 60.0:
                    state = "STABLE"
                elif health_score >= 40.0:
                    state = "DEGRADED"
                else:
                    state = "CRITICAL"
                
                conn.execute(
                    """
                    UPDATE lis_identity_profile
                    SET current_health_state = ?, composite_health_score = ?, last_verification_timestamp = ?
                    WHERE profile_id = ?
                    """,
                    (state, health_score, now, profile_id)
                )
                conn.commit()
                
            cls._check_identity_drift(profile_id, rolling_truth, rolling_alignment, rolling_reliability, rolling_learning, rolling_creativity)
        finally:
            conn.close()

    @classmethod
    def _check_identity_drift(
        cls,
        profile_id: str,
        truth: float,
        alignment: float,
        reliability: float,
        learning: float,
        creativity: float
    ) -> None:
        """Drift Detection: monitors index covariances to raise alerts on sycophancy or creativity decay."""
        conn = cls._get_sqlite_conn()
        try:
            with cls._lock:
                recent = conn.execute(
                    "SELECT * FROM lis_identity_ledger WHERE profile_id = ? ORDER BY recorded_at DESC LIMIT 10",
                    (profile_id,)
                ).fetchall()
                
                truth_trend = sum(r["delta_applied"] for r in recent if r["impacted_value"] == "TRUTH")
                align_trend = sum(r["delta_applied"] for r in recent if r["impacted_value"] == "ALIGNMENT")
                rel_trend = sum(r["delta_applied"] for r in recent if r["impacted_value"] == "RELIABILITY")
                creat_trend = sum(r["delta_applied"] for r in recent if r["impacted_value"] == "CREATIVITY")
                
                sycophancy_triggered = (truth_trend < 0 and align_trend > 0) or (truth < 45.0 and alignment > 70.0)
                reliability_triggered = (rel_trend < 0) or (reliability < 40.0)
                alignment_triggered = (align_trend < -5.0) or (alignment < 40.0)
                creativity_triggered = (creat_trend > 5.0 and truth_trend < 0) or (creativity > 70.0 and truth < 50.0)
                
                alarms = {
                    "SYCOPHANCY_INDEX": (sycophancy_triggered, truth - alignment),
                    "RELIABILITY_GAP": (reliability_triggered, 50.0 - reliability),
                    "CHATTER_DECAY": (alignment_triggered, 50.0 - alignment),
                    "CREATIVITY_ERRORS": (creativity_triggered, creativity - truth)
                }
                
                now = time.time()
                for metric, (triggered, div) in alarms.items():
                    conn.execute(
                        """
                        INSERT INTO lis_drift_tracker
                        (drift_id, profile_id, metric_monitored, current_divergence_value, is_alarm_tripped, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (f"drift_{uuid.uuid4().hex[:8]}", profile_id, metric, div, 1 if triggered else 0, now)
                    )
                conn.commit()
        finally:
            conn.close()

    @classmethod
    def get_autonomy_level(cls, profile_id: str = "default_profile") -> str:
        """Autonomy constraints mapping health score to restrictive zones."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT current_health_state, composite_health_score FROM lis_identity_profile WHERE profile_id = ?",
                (profile_id,)
            ).fetchone()
            if not row:
                return "FULL_AUTONOMY"
            
            score = row["composite_health_score"]
            if score < 40.0:
                return "RESTRICTED_MODE"
            elif score < 60.0:
                return "REDUCED_AUTONOMY"
            return "FULL_AUTONOMY"
        finally:
            conn.close()

    @classmethod
    def log_role_log(cls, profile_id: str, action_context_id: str, weights: Dict[str, float]) -> None:
        """Persists derived role weight trace logs (building tracing metadata for Meta-Cognition)."""
        conn = cls._get_sqlite_conn()
        log_id = f"lis_log_{uuid.uuid4().hex[:8]}"
        now = time.time()
        try:
            with cls._lock:
                conn.execute(
                    """
                    INSERT INTO lis_role_logs
                    (log_id, profile_id, action_context_id, teacher_weight_applied, engineer_weight_applied, scientist_weight_applied, builder_weight_applied, assistant_weight_applied, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        log_id, profile_id, action_context_id,
                        weights.get("Teacher", 0.20), weights.get("Engineer", 0.20),
                        weights.get("Scientist", 0.20), weights.get("Builder", 0.20),
                        weights.get("Assistant", 0.20), now
                    )
                )
                conn.commit()
        finally:
            conn.close()
