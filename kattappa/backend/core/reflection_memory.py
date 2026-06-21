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
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
