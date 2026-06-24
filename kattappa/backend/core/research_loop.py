"""Research Loop & Claim Verification System (Step 16).

Establishes Kattappa's capability to search, verify, score, and test external
research hypotheses against Kattappa's own benchmark baselines.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from backend.core.config import load_config


class ResearchLoop:
    """Scientific Intelligence pipeline that verifies citations, scores ROI, and schedules experiments."""

    _lock = threading.RLock()
    _schema_ensured = False

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        config = load_config()
        db_path = config.sqlite_path.parent / "research_ledger.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        with cls._lock:
            # Check dynamically to support tests resetting or unlinking the DB
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='research_papers'")
            if not cursor.fetchone():
                cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_papers (
                    paper_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    authors TEXT NOT NULL,
                    arxiv_id TEXT,
                    doi TEXT,
                    published_date TEXT,
                    verification_status TEXT DEFAULT 'unverified',
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_claims (
                    claim_id TEXT PRIMARY KEY,
                    paper_id TEXT NOT NULL,
                    claim_text TEXT NOT NULL,
                    target_component TEXT NOT NULL,
                    expected_delta REAL NOT NULL,
                    FOREIGN KEY(paper_id) REFERENCES research_papers(paper_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS research_experiments (
                    experiment_id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    roi_score REAL NOT NULL,
                    arena_suite_id TEXT,
                    test_results TEXT,
                    FOREIGN KEY(claim_id) REFERENCES research_claims(claim_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS research_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    implementation_path TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY(experiment_id) REFERENCES research_experiments(experiment_id) ON DELETE CASCADE
                );
                """
            )
            conn.commit()

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute("DELETE FROM research_proposals")
                conn.execute("DELETE FROM research_experiments")
                conn.execute("DELETE FROM research_claims")
                conn.execute("DELETE FROM research_papers")
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def verify_citation(arxiv_id: Optional[str], doi: Optional[str]) -> bool:
        """Verifies if the citation matches valid regular expression patterns."""
        if not arxiv_id and not doi:
            return False

        if arxiv_id:
            # Matches standard arXiv id e.g. arXiv:1706.03762v1 or 1706.03762
            arxiv_clean = arxiv_id.strip()
            pattern = re.compile(r"^(arXiv:)?\d{4}\.\d{4,5}(v\d+)?$", re.IGNORECASE)
            if pattern.match(arxiv_clean):
                return True

        if doi:
            # Matches standard DOI structure e.g. 10.1000/xyz123
            doi_clean = doi.strip()
            pattern = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)
            if pattern.match(doi_clean):
                return True

        return False

    @staticmethod
    def calculate_priority(
        relevance: float,
        reproducibility: float,
        expected_gain: float,
        evidence_strength: float
    ) -> float:
        """Priority Score calculation: ROI model weighting.

        Formula: 0.3 * relevance + 0.25 * reproducibility + 0.25 * expected_gain + 0.2 * evidence_strength
        Values should be float in range [0.0 - 10.0].
        """
        relevance = max(0.0, min(10.0, relevance))
        reproducibility = max(0.0, min(10.0, reproducibility))
        expected_gain = max(0.0, min(10.0, expected_gain))
        evidence_strength = max(0.0, min(10.0, evidence_strength))

        score = (0.30 * relevance) + (0.25 * reproducibility) + (0.25 * expected_gain) + (0.20 * evidence_strength)
        return round(score, 2)

    @classmethod
    def ingest_paper(
        cls,
        title: str,
        authors: str,
        arxiv_id: Optional[str],
        doi: Optional[str],
        published_date: str,
        claims: List[Dict[str, Any]],
        metrics: Dict[str, float]
    ) -> Dict[str, Any]:
        """Ingests a research paper, validates citations, calculates ROI, and creates proposals."""
        import uuid
        paper_id = f"pap_{uuid.uuid4().hex[:12]}"
        now = time.time()

        # 1. Verify Citation
        verified = cls.verify_citation(arxiv_id, doi)
        verification_status = "verified" if verified else "rejected"

        # 2. Score ROI
        relevance = float(metrics.get("relevance", 5.0))
        reproducibility = float(metrics.get("reproducibility", 5.0))
        expected_gain = float(metrics.get("expected_gain", 5.0))
        evidence_strength = float(metrics.get("evidence_strength", 5.0))

        priority_score = cls.calculate_priority(relevance, reproducibility, expected_gain, evidence_strength)

        conn = cls._get_sqlite_conn()
        try:
            # 3. Save Paper
            conn.execute(
                """
                INSERT INTO research_papers (paper_id, title, authors, arxiv_id, doi, published_date, verification_status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (paper_id, title.strip(), authors.strip(), arxiv_id, doi, published_date, verification_status, now)
            )

            # 4. Save Claims & Experiments
            experiment_candidate = False
            experiment_ids = []
            proposal_ids = []

            for idx, claim in enumerate(claims):
                claim_id = f"clm_{uuid.uuid4().hex[:12]}_{idx}"
                conn.execute(
                    """
                    INSERT INTO research_claims (claim_id, paper_id, claim_text, target_component, expected_delta)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (claim_id, paper_id, claim.get("claim_text", ""), claim.get("target_component", "unknown"), float(claim.get("expected_delta", 0.0)))
                )

                # Initialize Experiment
                exp_id = f"exp_{uuid.uuid4().hex[:12]}_{idx}"
                status = "implementation_candidate" if priority_score > 9.0 else "pending"
                if priority_score > 9.0:
                    experiment_candidate = True

                conn.execute(
                    """
                    INSERT INTO research_experiments (experiment_id, claim_id, status, roi_score, arena_suite_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (exp_id, claim_id, status, priority_score, claim.get("arena_suite_id"))
                )
                experiment_ids.append(exp_id)

                # Generate Proposals if score > 8.5
                if priority_score > 8.5:
                    prop_id = f"prp_{uuid.uuid4().hex[:12]}_{idx}"
                    summary = f"Reproduction proposal for claim: {claim.get('claim_text')}"
                    impl_path = f"backend/core/{claim.get('target_component', 'unknown')}.py"
                    conn.execute(
                        """
                        INSERT INTO research_proposals (proposal_id, experiment_id, summary, implementation_path, status)
                        VALUES (?, ?, ?, ?, 'pending')
                        """,
                        (prop_id, exp_id, summary, impl_path)
                    )
                    proposal_ids.append(prop_id)

            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

        # Step 18: Auto-queue experiment templates for high-priority claims
        # (priority_score > 9.0 → implementation_candidate).
        # Templates are queued only; human triggers /research/reproduce/{claim_id}.
        reproduction_template_ids: list[str] = []
        if priority_score > 9.0 and verified:
            try:
                from backend.core.claim_reproduction_engine import ClaimReproductionEngine
                for idx, claim in enumerate(claims):
                    claim_id = f"clm_lookup_{idx}"   # resolve from experiment_ids
                    # Re-derive claim_id from stored experiment_ids
                    if idx < len(experiment_ids):
                        # Find the claim_id from the experiment record
                        try:
                            _conn = cls._get_sqlite_conn()
                            row = _conn.execute(
                                "SELECT claim_id FROM research_experiments WHERE experiment_id = ?",
                                (experiment_ids[idx],)
                            ).fetchone()
                            _conn.close()
                            if row:
                                claim_id = row["claim_id"]
                        except Exception:
                            pass

                    template = ClaimReproductionEngine.build_template(
                        claim_id=claim_id,
                        paper_id=paper_id,
                        paper_title=title,
                        component_target=claim.get("target_component", "agent"),
                        predicted_gain=float(claim.get("expected_delta", 0.0)),
                    )
                    reproduction_template_ids.append(template.experiment_id)
            except Exception:
                pass  # Never crash ingestion due to reproduction queue failure

        return {
            "paper_id": paper_id,
            "verification_status": verification_status,
            "priority_score": priority_score,
            "experiment_candidate": experiment_candidate,
            "experiment_ids": experiment_ids,
            "proposal_ids": proposal_ids,
            "reproduction_template_ids": reproduction_template_ids,
        }


    @classmethod
    def list_proposals(cls) -> List[Dict[str, Any]]:
        """Returns all research proposals with associated papers and claims details."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                """
                SELECT p.proposal_id, p.summary, p.implementation_path, p.status AS proposal_status,
                       e.experiment_id, e.roi_score, e.status AS experiment_status,
                       c.claim_text, c.target_component, c.expected_delta,
                       pa.title, pa.authors, pa.arxiv_id, pa.doi, pa.verification_status
                FROM research_proposals p
                JOIN research_experiments e ON p.experiment_id = e.experiment_id
                JOIN research_claims c ON e.claim_id = c.claim_id
                JOIN research_papers pa ON c.paper_id = pa.paper_id
                """
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def evaluate_experiment_candidate(cls, experiment_id: str, run_results: Dict[str, Any]) -> Dict[str, Any]:
        """Appends benchmark evaluation results and resolves the candidate experiment status."""
        success = bool(run_results.get("success", False))
        status = "verified" if success else "rejected"
        
        conn = cls._get_sqlite_conn()
        try:
            conn.execute(
                """
                UPDATE research_experiments
                SET status = ?, test_results = ?
                WHERE experiment_id = ?
                """,
                (status, json.dumps(run_results), experiment_id)
            )
            
            # Cascade status to associated proposal
            conn.execute(
                """
                UPDATE research_proposals
                SET status = ?
                WHERE experiment_id = ?
                """,
                (status, experiment_id)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

        return {"experiment_id": experiment_id, "status": status}
