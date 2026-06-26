from __future__ import annotations

import hmac
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from backend.core.config import load_config
from backend.core.logger import log_event


class ProceduralMemory:
    """Procedural Memory Subsystem (Layer 5) for skills, procedures, and actions.
    
    Adheres to Memory System Layer 5 security specification:
    - Authoritative storage in SQLite (hm_procedures, hm_procedure_audit).
    - Cryptographic verification via HMAC-SHA256 signatures.
    - Security trust gates for execution (SYSTEM_TRUST, USER_APPROVED, DRAFT, UNTRUSTED).
    - Source isolation preventing OCR, Web, and untrusted memories from triggering procedures.
    - Monotonic version-check replay attack protection.
    - Audit log tracking execution history and security violations.
    """
    
    _lock = threading.RLock()
    _schema_ensured = False
    _default_key = b"kattappa_procedural_secret_default_key"

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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS hm_procedures (
                    id TEXT PRIMARY KEY,
                    skill_name TEXT NOT NULL,
                    trigger_phrase TEXT,
                    steps_json TEXT NOT NULL,
                    trust_level TEXT NOT NULL,
                    procedure_version INTEGER DEFAULT 1,
                    signature TEXT NOT NULL,
                    created_at REAL,
                    updated_at REAL,
                    last_used REAL,
                    revoked INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_hm_procedures_skill ON hm_procedures(skill_name);
                CREATE INDEX IF NOT EXISTS idx_hm_procedures_trigger ON hm_procedures(trigger_phrase);

                CREATE TABLE IF NOT EXISTS hm_procedure_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    procedure_id TEXT,
                    timestamp REAL,
                    action TEXT,
                    result TEXT,
                    source TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_hm_procedure_audit_proc ON hm_procedure_audit(procedure_id);
                """
            )
            conn.commit()

    @classmethod
    def _get_hmac_key(cls) -> bytes:
        key_str = os.getenv("KATTAPPA_PROCEDURAL_KEY")
        if key_str:
            return key_str.encode("utf-8")
        return cls._default_key

    @classmethod
    def calculate_signature(
        cls,
        skill_name: str,
        steps_json: str,
        trust_level: str,
        trigger_phrase: Optional[str],
        procedure_version: int
    ) -> str:
        """Calculates HMAC-SHA256 signature for procedure tamper and replay protection."""
        key = cls._get_hmac_key()
        phrase = trigger_phrase or ""
        # Deterministic serialization structure
        message = f"{skill_name}:{steps_json}:{trust_level}:{phrase}:{procedure_version}"
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()

    @classmethod
    def register_procedure(
        cls,
        skill_name: str,
        trigger_phrase: Optional[str],
        steps_json: str,
        trust_level: str,
        procedure_version: int = 1,
        procedure_id: Optional[str] = None,
        derived_from_nodes: Optional[list[str]] = None
    ) -> str:
        """Register or update a procedure in SQLite, signing the content."""
        clean_skill = skill_name.strip()
        clean_phrase = trigger_phrase.strip() if trigger_phrase else None
        clean_steps = steps_json.strip()
        clean_trust = trust_level.strip().upper()
        
        # Verify JSON syntax
        json.loads(clean_steps)
        
        # A-4: Source-Isolation Gate between Semantic -> Procedural
        if derived_from_nodes:
            from backend.core.semantic_memory import SemanticMemory
            all_episode_ids = []
            for node_id in derived_from_nodes:
                node = SemanticMemory.get_node(node_id)
                if node:
                    all_episode_ids.extend(node.get("source_episode_ids") or [])
            
            from backend.core.memory_governance import MemoryGovernance
            for eid in all_episode_ids:
                trust = MemoryGovernance.get_trust(eid)
                if trust == "TRUST_UNTRUSTED":
                    if clean_trust in {"SYSTEM_TRUST", "USER_APPROVED"}:
                        raise ValueError(f"Cannot register trusted procedure derived from untrusted episodes")
                prov = MemoryGovernance.get_provenance(eid)
                if prov and prov.get("source") in {"web", "ocr", "untrusted"}:
                    if clean_trust in {"SYSTEM_TRUST", "USER_APPROVED"}:
                        raise ValueError(f"Cannot register trusted procedure derived from untrusted episodes")

        signature = cls.calculate_signature(
            clean_skill, clean_steps, clean_trust, clean_phrase, procedure_version
        )
        
        pid = procedure_id or str(uuid.uuid4())
        now = time.time()

        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                # Check if it exists
                row = conn.execute("SELECT id FROM hm_procedures WHERE id = ?", (pid,)).fetchone()
                if row:
                    conn.execute(
                        """
                        UPDATE hm_procedures
                        SET skill_name = ?, trigger_phrase = ?, steps_json = ?,
                            trust_level = ?, procedure_version = ?, signature = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (clean_skill, clean_phrase, clean_steps, clean_trust, procedure_version, signature, now, pid)
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO hm_procedures (
                            id, skill_name, trigger_phrase, steps_json, trust_level,
                            procedure_version, signature, created_at, updated_at, revoked
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """,
                        (pid, clean_skill, clean_phrase, clean_steps, clean_trust, procedure_version, signature, now, now)
                    )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

        # Log provenance via MemoryGovernance
        try:
            from backend.core.memory_governance import MemoryGovernance
            MemoryGovernance.log_provenance(
                memory_id=pid,
                memory_type="procedural",
                source="system",
                created_by="procedural_layer",
                confidence=1.0,
                derived_from=derived_from_nodes
            )
        except Exception as e:
            log_event(f"procedural_memory: failed to log provenance for {pid}: {e}")
                
        return pid

    @classmethod
    def get_procedure(cls, procedure_id: str) -> dict[str, Any] | None:
        """Retrieves a procedure by ID from SQLite."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM hm_procedures WHERE id = ?", (procedure_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @classmethod
    def get_latest_version(cls, skill_name: str) -> int:
        """Get the highest registered version for a skill_name in SQLite."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT MAX(procedure_version) as max_v FROM hm_procedures WHERE skill_name = ?",
                (skill_name.strip(),)
            ).fetchone()
            return row["max_v"] if (row and row["max_v"] is not None) else 0
        finally:
            conn.close()

    @classmethod
    def revoke_procedure(cls, procedure_id: str) -> bool:
        """Revokes a procedure preventing any future executions."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cursor = conn.execute(
                    "UPDATE hm_procedures SET revoked = 1, updated_at = ? WHERE id = ?",
                    (now, procedure_id)
                )
                conn.commit()
                revoked = cursor.rowcount > 0
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        
        if revoked:
            cls._log_audit(procedure_id, "revoke", "SUCCESS", "system")
        return revoked

    @classmethod
    def delete_procedure(cls, procedure_id: str) -> bool:
        """Deletes a procedure from SQLite."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                cursor = conn.execute("DELETE FROM hm_procedures WHERE id = ?", (procedure_id,))
                conn.commit()
                deleted = cursor.rowcount > 0
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        return deleted

    @classmethod
    def validate_and_gate(cls, procedure_id: str, trigger_source: str) -> Tuple[bool, str]:
        """Validates procedure signature, trust levels, monotonic versioning, and trigger source.
        
        Returns:
            (is_allowed, block_reason)
        """
        source_clean = trigger_source.strip().lower()
        
        # 1. Fetch record from authoritative source of truth
        proc = cls.get_procedure(procedure_id)
        if not proc:
            cls._log_audit(procedure_id, "execute_attempt", "BLOCKED_PROCEDURE_NOT_FOUND", source_clean)
            return False, "procedure_not_found"

        # 2. Check if revoked
        if proc["revoked"] == 1:
            cls._log_audit(procedure_id, "execute_attempt", "BLOCKED_PROCEDURE_REVOKED", source_clean)
            return False, "procedure_revoked"

        # 3. Check trust level permissions
        allowed_trusts = {"SYSTEM_TRUST", "USER_APPROVED"}
        if proc["trust_level"] not in allowed_trusts:
            cls._log_audit(procedure_id, "execute_attempt", "BLOCKED_TRUST_LEVEL_NOT_ALLOWED", source_clean)
            return False, "trust_level_not_allowed"

        # 4. Check trigger source trust (web, ocr, untrusted inputs block execution)
        blocked_sources = {"web", "ocr", "untrusted", "untrusted_memory"}
        if source_clean in blocked_sources:
            cls._log_audit(procedure_id, "execute_attempt", "BLOCKED_UNTRUSTED_SOURCE", source_clean)
            return False, "untrusted_source"

        # 5. Monotonic version replay check
        latest_version = cls.get_latest_version(proc["skill_name"])
        if proc["procedure_version"] < latest_version:
            cls._log_audit(procedure_id, "execute_attempt", "BLOCKED_VERSION_REPLAY", source_clean)
            return False, "version_replay_blocked"

        # 6. Verify HMAC signature
        expected_signature = cls.calculate_signature(
            proc["skill_name"],
            proc["steps_json"],
            proc["trust_level"],
            proc["trigger_phrase"],
            proc["procedure_version"]
        )
        if not hmac.compare_digest(proc["signature"], expected_signature):
            cls._log_audit(procedure_id, "execute_attempt", "BLOCKED_SIGNATURE_INVALID", source_clean)
            return False, "signature_invalid"

        # Success - log audit and update last_used
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    "UPDATE hm_procedures SET last_used = ? WHERE id = ?",
                    (now, procedure_id)
                )
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

        cls._log_audit(procedure_id, "execute_attempt", "SUCCESS", source_clean)
        return True, "allowed"

    @classmethod
    def match_trigger(cls, context_text: str) -> list[dict[str, Any]]:
        """Matches a context string against regex or literal trigger phrases.
        
        Returns all matching procedures.
        """
        conn = cls._get_sqlite_conn()
        matched_procedures = []
        try:
            rows = conn.execute("SELECT * FROM hm_procedures WHERE trigger_phrase IS NOT NULL AND revoked = 0").fetchall()
            for row in rows:
                phrase = row["trigger_phrase"]
                matched = False
                
                # 1. Regex trigger matching
                try:
                    if re.search(phrase, context_text, re.IGNORECASE):
                        matched = True
                except re.error:
                    pass

                # 2. Literal substring fallback
                if not matched:
                    matched = phrase.lower() in context_text.lower()
                    
                if matched:
                    record = dict(row)
                    matched_procedures.append(record)
        finally:
            conn.close()
        return matched_procedures

    @classmethod
    def _log_audit(cls, procedure_id: str, action: str, result: str, source: str) -> None:
        """Inserts a record into the procedure execution audit trail."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_procedure_audit (procedure_id, timestamp, action, result, source)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (procedure_id, now, action, result, source)
                )
                conn.commit()
            except Exception as e:
                log_event(f"procedural_memory: audit logging failed: {e}")
            finally:
                conn.close()

    @classmethod
    def get_audit_trail(cls, procedure_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Retrieves audit trail entries, optionally filtered by procedure_id."""
        conn = cls._get_sqlite_conn()
        try:
            if procedure_id:
                rows = conn.execute(
                    "SELECT * FROM hm_procedure_audit WHERE procedure_id = ? ORDER BY timestamp DESC",
                    (procedure_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM hm_procedure_audit ORDER BY timestamp DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
