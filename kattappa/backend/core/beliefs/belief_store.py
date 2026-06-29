"""Belief Management Component 2: Store.

Decoupled persistent SQLite store managing beliefs, version history, justifications, and dependency links.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.cos.state_representation import BeliefStatus
from backend.core.beliefs.belief import Belief, Justification, BeliefDependency

logger = logging.getLogger(__name__)


def _beliefs_db_path() -> Path:
    config = load_config()
    beliefs_dir = config.sqlite_path.parent / "beliefs"
    beliefs_dir.mkdir(parents=True, exist_ok=True)
    return beliefs_dir / "beliefs.db"


class BeliefStore:
    """Manages transactional access to the SQLite beliefs database."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self._db_path = str(db_path or _beliefs_db_path())
        self._lock = threading.RLock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                # Active/Current beliefs
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS beliefs (
                        belief_id TEXT PRIMARY KEY,
                        claim_subject TEXT NOT NULL,
                        claim_predicate TEXT NOT NULL,
                        claim_value TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        truth_status TEXT NOT NULL,
                        source_ids TEXT NOT NULL,
                        evidence_ids TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        valid_from REAL NOT NULL,
                        valid_until REAL,
                        version INTEGER NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}'
                    );
                """)
                # Index for quick lookup of current belief by subject+predicate
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_beliefs_claim ON beliefs(claim_subject, claim_predicate);"
                )

                # Belief Version History (to preserve retracted/refuted states)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS belief_history (
                        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        belief_id TEXT NOT NULL,
                        claim_subject TEXT NOT NULL,
                        claim_predicate TEXT NOT NULL,
                        claim_value TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        truth_status TEXT NOT NULL,
                        source_ids TEXT NOT NULL,
                        evidence_ids TEXT NOT NULL,
                        updated_at REAL NOT NULL,
                        valid_from REAL NOT NULL,
                        valid_until REAL,
                        version INTEGER NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}'
                    );
                """)

                # Justifications
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS justifications (
                        justification_id TEXT PRIMARY KEY,
                        belief_id TEXT NOT NULL,
                        rationale TEXT NOT NULL,
                        evidence_ids TEXT NOT NULL,
                        dependency_ids TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        FOREIGN KEY (belief_id) REFERENCES beliefs (belief_id)
                    );
                """)

                # Dependencies Table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS dependencies (
                        parent_belief_id TEXT NOT NULL,
                        child_belief_id TEXT NOT NULL,
                        dependency_type TEXT NOT NULL,
                        PRIMARY KEY (parent_belief_id, child_belief_id)
                    );
                """)
                conn.commit()
            except Exception as exc:
                logger.error("BeliefStore: schema initialization failed: %s", exc)
                conn.rollback()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Belief CRUD
    # ------------------------------------------------------------------

    def save_belief(self, belief: Belief) -> None:
        """Saves or updates a belief, writing the revision state to history."""
        with self._lock:
            conn = self._get_conn()
            try:
                # 1. Insert history log first
                conn.execute(
                    """
                    INSERT INTO belief_history (
                        belief_id, claim_subject, claim_predicate, claim_value,
                        confidence, truth_status, source_ids, evidence_ids,
                        updated_at, valid_from, valid_until, version, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        belief.belief_id,
                        belief.claim_subject,
                        belief.claim_predicate,
                        json.dumps(belief.claim_value),
                        belief.confidence,
                        belief.truth_status.value,
                        json.dumps(belief.source_ids),
                        json.dumps(belief.evidence_ids),
                        belief.updated_at,
                        belief.valid_from,
                        belief.valid_until,
                        belief.version,
                        json.dumps(belief.metadata),
                    ),
                )

                # 2. Upsert in active beliefs table
                conn.execute(
                    """
                    INSERT OR REPLACE INTO beliefs (
                        belief_id, claim_subject, claim_predicate, claim_value,
                        confidence, truth_status, source_ids, evidence_ids,
                        created_at, updated_at, valid_from, valid_until, version, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        belief.belief_id,
                        belief.claim_subject,
                        belief.claim_predicate,
                        json.dumps(belief.claim_value),
                        belief.confidence,
                        belief.truth_status.value,
                        json.dumps(belief.source_ids),
                        json.dumps(belief.evidence_ids),
                        belief.created_at,
                        belief.updated_at,
                        belief.valid_from,
                        belief.valid_until,
                        belief.version,
                        json.dumps(belief.metadata),
                    ),
                )
                conn.commit()
            except Exception as exc:
                logger.error("BeliefStore: save_belief failed: %s", exc)
                conn.rollback()
                raise exc
            finally:
                conn.close()

    def get_belief(self, belief_id: str) -> Optional[Belief]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT * FROM beliefs WHERE belief_id = ?", (belief_id,)).fetchone()
                if not row:
                    return None
                return Belief(
                    belief_id=row["belief_id"],
                    claim_subject=row["claim_subject"],
                    claim_predicate=row["claim_predicate"],
                    claim_value=json.loads(row["claim_value"]),
                    confidence=row["confidence"],
                    truth_status=BeliefStatus(row["truth_status"]),
                    source_ids=json.loads(row["source_ids"]),
                    evidence_ids=json.loads(row["evidence_ids"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    valid_from=row["valid_from"],
                    valid_until=row["valid_until"],
                    version=row["version"],
                    metadata=json.loads(row["metadata"]),
                )
            finally:
                conn.close()

    def get_belief_by_claim(self, subject: str, predicate: str) -> Optional[Belief]:
        """Finds active belief for a given subject & predicate."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    """
                    SELECT * FROM beliefs 
                    WHERE claim_subject = ? AND claim_predicate = ?
                    ORDER BY 
                      CASE truth_status 
                        WHEN 'BELIEVED' THEN 1 
                        WHEN 'HYPOTHESIS' THEN 2 
                        WHEN 'RETRACTED' THEN 3 
                        WHEN 'REFUTED' THEN 4 
                        ELSE 5 
                      END ASC, 
                      updated_at DESC 
                    LIMIT 1
                    """,
                    (subject, predicate),
                ).fetchone()
                if not row:
                    return None
                return Belief(
                    belief_id=row["belief_id"],
                    claim_subject=row["claim_subject"],
                    claim_predicate=row["claim_predicate"],
                    claim_value=json.loads(row["claim_value"]),
                    confidence=row["confidence"],
                    truth_status=BeliefStatus(row["truth_status"]),
                    source_ids=json.loads(row["source_ids"]),
                    evidence_ids=json.loads(row["evidence_ids"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    valid_from=row["valid_from"],
                    valid_until=row["valid_until"],
                    version=row["version"],
                    metadata=json.loads(row["metadata"]),
                )
            finally:
                conn.close()

    def list_beliefs(self) -> List[Belief]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute("SELECT * FROM beliefs").fetchall()
                return [
                    Belief(
                        belief_id=r["belief_id"],
                        claim_subject=r["claim_subject"],
                        claim_predicate=r["claim_predicate"],
                        claim_value=json.loads(r["claim_value"]),
                        confidence=r["confidence"],
                        truth_status=BeliefStatus(r["truth_status"]),
                        source_ids=json.loads(r["source_ids"]),
                        evidence_ids=json.loads(r["evidence_ids"]),
                        created_at=r["created_at"],
                        updated_at=r["updated_at"],
                        valid_from=r["valid_from"],
                        valid_until=r["valid_until"],
                        version=r["version"],
                        metadata=json.loads(r["metadata"]),
                    )
                    for r in rows
                ]
            finally:
                conn.close()

    def get_belief_history(self, belief_id: str) -> List[Dict[str, Any]]:
        """Returns all historic versions of a belief."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM belief_history WHERE belief_id = ? ORDER BY version ASC",
                    (belief_id,),
                ).fetchall()
                return [
                    {
                        "belief_id": r["belief_id"],
                        "claim_subject": r["claim_subject"],
                        "claim_predicate": r["claim_predicate"],
                        "claim_value": json.loads(r["claim_value"]),
                        "confidence": r["confidence"],
                        "truth_status": r["truth_status"],
                        "source_ids": json.loads(r["source_ids"]),
                        "evidence_ids": json.loads(r["evidence_ids"]),
                        "updated_at": r["updated_at"],
                        "valid_from": r["valid_from"],
                        "valid_until": r["valid_until"],
                        "version": r["version"],
                        "metadata": json.loads(r["metadata"]),
                    }
                    for r in rows
                ]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Justification CRUD
    # ------------------------------------------------------------------

    def save_justification(self, just: Justification) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO justifications (
                        justification_id, belief_id, rationale,
                        evidence_ids, dependency_ids, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        just.justification_id,
                        just.belief_id,
                        just.rationale,
                        json.dumps(just.evidence_ids),
                        json.dumps(just.dependency_ids),
                        just.created_at,
                    ),
                )
                conn.commit()
            except Exception as exc:
                logger.error("BeliefStore: save_justification failed: %s", exc)
                conn.rollback()
                raise exc
            finally:
                conn.close()

    def get_justifications_for_belief(self, belief_id: str) -> List[Justification]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM justifications WHERE belief_id = ? ORDER BY created_at DESC",
                    (belief_id,),
                ).fetchall()
                return [
                    Justification(
                        justification_id=r["justification_id"],
                        belief_id=r["belief_id"],
                        rationale=r["rationale"],
                        evidence_ids=json.loads(r["evidence_ids"]),
                        dependency_ids=json.loads(r["dependency_ids"]),
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Dependency CRUD
    # ------------------------------------------------------------------

    def add_dependency(self, dep: BeliefDependency) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO dependencies (parent_belief_id, child_belief_id, dependency_type) VALUES (?, ?, ?)",
                    (dep.parent_belief_id, dep.child_belief_id, dep.dependency_type),
                )
                conn.commit()
            except Exception as exc:
                logger.error("BeliefStore: add_dependency failed: %s", exc)
                conn.rollback()
                raise exc
            finally:
                conn.close()

    def remove_dependency(self, parent_id: str, child_id: str) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "DELETE FROM dependencies WHERE parent_belief_id = ? AND child_belief_id = ?",
                    (parent_id, child_id),
                )
                conn.commit()
            except Exception as exc:
                logger.error("BeliefStore: remove_dependency failed: %s", exc)
                conn.rollback()
                raise exc
            finally:
                conn.close()

    def get_child_dependencies(self, parent_belief_id: str) -> List[BeliefDependency]:
        """Returns dependencies where the given belief is the parent (i.e. child depends on parent)."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM dependencies WHERE parent_belief_id = ?",
                    (parent_belief_id,),
                ).fetchall()
                return [
                    BeliefDependency(
                        parent_belief_id=r["parent_belief_id"],
                        child_belief_id=r["child_belief_id"],
                        dependency_type=r["dependency_type"],
                    )
                    for r in rows
                ]
            finally:
                conn.close()

    def get_parent_dependencies(self, child_belief_id: str) -> List[BeliefDependency]:
        """Returns dependencies where the given belief is the child (i.e. depends on parent)."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM dependencies WHERE child_belief_id = ?",
                    (child_belief_id,),
                ).fetchall()
                return [
                    BeliefDependency(
                        parent_belief_id=r["parent_belief_id"],
                        child_belief_id=r["child_belief_id"],
                        dependency_type=r["dependency_type"],
                    )
                    for r in rows
                ]
            finally:
                conn.close()
