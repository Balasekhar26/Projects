"""Provenance Engine Component 2: Store.

Decoupled persistent SQLite store managing sources, evidence, and target links.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.provenance.models import ProvenanceEvidenceItem, ProvenanceRecord, Source

logger = logging.getLogger(__name__)


def _provenance_db_path() -> Path:
    config = load_config()
    provenance_dir = config.sqlite_path.parent / "provenance"
    provenance_dir.mkdir(parents=True, exist_ok=True)
    return provenance_dir / "provenance.db"


class ProvenanceStore:
    """Manages transactional access to the SQLite provenance database."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self._db_path = str(db_path or _provenance_db_path())
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
                # Sources Table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sources (
                        source_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        base_reputation REAL NOT NULL,
                        current_reputation REAL NOT NULL,
                        trust_level TEXT NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}'
                    );
                """)
                # Evidence Table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS evidence (
                        evidence_id TEXT PRIMARY KEY,
                        source_id TEXT NOT NULL,
                        evidence_level TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        verification_state TEXT NOT NULL,
                        observed_at REAL NOT NULL,
                        context_citation TEXT,
                        supports INTEGER NOT NULL DEFAULT 1,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        FOREIGN KEY (source_id) REFERENCES sources (source_id)
                    );
                """)
                # Provenance Links (Many-to-Many or Many-to-One association)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS provenance_links (
                        target_id TEXT NOT NULL,
                        evidence_id TEXT NOT NULL,
                        PRIMARY KEY (target_id, evidence_id),
                        FOREIGN KEY (evidence_id) REFERENCES evidence (evidence_id)
                    );
                """)
                conn.commit()
            except Exception as exc:
                logger.error("ProvenanceStore: schema initialization failed: %s", exc)
                conn.rollback()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Source Registry CRUD
    # ------------------------------------------------------------------

    def save_source(self, src: Source) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO sources (
                        source_id, name, source_type, base_reputation,
                        current_reputation, trust_level, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        src.source_id,
                        src.name,
                        src.source_type,
                        src.base_reputation,
                        src.current_reputation,
                        src.trust_level,
                        json.dumps(src.metadata),
                    ),
                )
                conn.commit()
            except Exception as exc:
                logger.error("ProvenanceStore: save_source failed (%s): %s", src.source_id, exc)
                conn.rollback()
                raise exc
            finally:
                conn.close()

    def get_source(self, source_id: str) -> Optional[Source]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT * FROM sources WHERE source_id = ?", (source_id,)).fetchone()
                if not row:
                    return None
                return Source(
                    source_id=row["source_id"],
                    name=row["name"],
                    source_type=row["source_type"],
                    base_reputation=row["base_reputation"],
                    current_reputation=row["current_reputation"],
                    trust_level=row["trust_level"],
                    metadata=json.loads(row["metadata"]),
                )
            finally:
                conn.close()

    def list_sources(self) -> List[Source]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute("SELECT * FROM sources").fetchall()
                return [
                    Source(
                        source_id=r["source_id"],
                        name=r["name"],
                        source_type=r["source_type"],
                        base_reputation=r["base_reputation"],
                        current_reputation=r["current_reputation"],
                        trust_level=r["trust_level"],
                        metadata=json.loads(r["metadata"]),
                    )
                    for r in rows
                ]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Evidence Operations
    # ------------------------------------------------------------------

    def save_evidence(self, ev: ProvenanceEvidenceItem) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                # Ensure the source exists in the DB first
                source_row = conn.execute("SELECT 1 FROM sources WHERE source_id = ?", (ev.source_id,)).fetchone()
                if not source_row:
                    # Register an autodetected placeholder source
                    placeholder = Source(
                        source_id=ev.source_id,
                        name=ev.source_id,
                        source_type="autodetected",
                    )
                    self.save_source(placeholder)

                conn.execute(
                    """
                    INSERT OR REPLACE INTO evidence (
                        evidence_id, source_id, evidence_level, confidence,
                        verification_state, observed_at, context_citation, supports, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ev.evidence_id,
                        ev.source_id,
                        ev.evidence_level.name,
                        ev.confidence,
                        ev.verification_state.value,
                        ev.observed_at,
                        ev.context_citation,
                        1 if ev.supports else 0,
                        json.dumps(ev.metadata),
                    ),
                )
                conn.commit()
            except Exception as exc:
                logger.error("ProvenanceStore: save_evidence failed (%s): %s", ev.evidence_id, exc)
                conn.rollback()
                raise exc
            finally:
                conn.close()

    def get_evidence(self, evidence_id: str) -> Optional[ProvenanceEvidenceItem]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
                if not row:
                    return None
                return ProvenanceEvidenceItem.from_dict({
                    "evidence_id": row["evidence_id"],
                    "source_id": row["source_id"],
                    "evidence_level": row["evidence_level"],
                    "confidence": row["confidence"],
                    "verification_state": row["verification_state"],
                    "observed_at": row["observed_at"],
                    "context_citation": row["context_citation"],
                    "supports": bool(row["supports"]),
                    "metadata": json.loads(row["metadata"]),
                })
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Link Operations (Provenance Links)
    # ------------------------------------------------------------------

    def link_target_to_evidence(self, target_id: str, evidence_id: str) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO provenance_links (target_id, evidence_id) VALUES (?, ?)",
                    (target_id, evidence_id),
                )
                conn.commit()
            except Exception as exc:
                logger.error("ProvenanceStore: link failed (target=%s, ev=%s): %s", target_id, evidence_id, exc)
                conn.rollback()
                raise exc
            finally:
                conn.close()

    def get_provenance_record(self, target_id: str) -> ProvenanceRecord:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT evidence_id FROM provenance_links WHERE target_id = ?",
                    (target_id,),
                ).fetchall()
                evidence_ids = [r["evidence_id"] for r in rows]
                return ProvenanceRecord(target_id=target_id, evidence_ids=evidence_ids)
            finally:
                conn.close()

    def get_evidence_for_target(self, target_id: str) -> List[ProvenanceEvidenceItem]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """
                    SELECT e.* FROM evidence e
                    JOIN provenance_links l ON e.evidence_id = l.evidence_id
                    WHERE l.target_id = ?
                    ORDER BY e.observed_at ASC
                    """,
                    (target_id,),
                ).fetchall()
                return [
                    ProvenanceEvidenceItem.from_dict({
                        "evidence_id": r["evidence_id"],
                        "source_id": r["source_id"],
                        "evidence_level": r["evidence_level"],
                        "confidence": r["confidence"],
                        "verification_state": r["verification_state"],
                        "observed_at": r["observed_at"],
                        "context_citation": r["context_citation"],
                        "supports": bool(r["supports"]),
                        "metadata": json.loads(r["metadata"]),
                    })
                    for r in rows
                ]
            finally:
                conn.close()
