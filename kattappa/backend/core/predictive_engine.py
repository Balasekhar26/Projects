"""Predictive Cognition Layer — Phase K16.

Implements belief state tracking (UUIDs, sources, timestamps, and contradictions),
uncertainty-propagating forward simulations, counterfactual sandbox runs, and
prediction error loops to drive learning feedback.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.core.config import load_config
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass
class TransitionResult:
    """Carries simulated state transitions with propagated uncertainty."""
    predicted_state: Dict[str, Any]
    confidence: float
    uncertainty: float  # Entropy / disagreement metric (0.0 to 1.0)
    assumptions: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)


@dataclass
class Belief:
    """Evolving belief state item."""
    belief_id: str
    concept: str
    statement: str
    confidence: float
    source: str
    last_verified: float
    contradictions: List[str] = field(default_factory=list)


class PredictiveEngine:
    """Manages system-level predictive intelligence over belief states."""

    _lock = threading.Lock()

    @classmethod
    def _get_conn(cls, db_path: Optional[str] = None) -> sqlite3.Connection:
        if db_path is None:
            config = load_config()
            config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            db_path = str(config.sqlite_path.parent / "predictive_cognition.db")
        conn = sqlite3.connect(db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS hm_beliefs (
                id TEXT PRIMARY KEY,
                concept TEXT NOT NULL,
                statement TEXT NOT NULL,
                confidence REAL NOT NULL,
                source TEXT NOT NULL,
                last_verified REAL NOT NULL,
                contradictions TEXT DEFAULT '[]'
            );
            """
        )
        conn.commit()

    # ── Belief State Manager ────────────────────────────────────────────────
    @classmethod
    def add_belief(
        cls,
        concept: str,
        statement: str,
        confidence: float,
        source: str,
        db_path: Optional[str] = None
    ) -> str:
        """Add a new belief and auto-resolves contradictions."""
        bid = str(uuid.uuid4())
        now = time.time()
        
        # Check contradictions
        contradictions = cls.find_contradictions(statement, db_path=db_path)

        with cls._lock:
            conn = cls._get_conn(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO hm_beliefs (id, concept, statement, confidence, source, last_verified, contradictions)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (bid, concept, statement, confidence, source, now, json.dumps(contradictions))
                )
                
                # Update contradictory beliefs to link to this new one
                for contra_id in contradictions:
                    row = conn.execute("SELECT contradictions FROM hm_beliefs WHERE id = ?", (contra_id,)).fetchone()
                    if row:
                        lst = json.loads(row["contradictions"] or "[]")
                        if bid not in lst:
                            lst.append(bid)
                            conn.execute(
                                "UPDATE hm_beliefs SET contradictions = ? WHERE id = ?",
                                (json.dumps(lst), contra_id)
                            )

                conn.commit()
                log_event("predictive_belief_added", f"Belief added: {concept} (conf={confidence:.2f})")
            except Exception as e:
                conn.rollback()
                logger.error("PredictiveEngine: failed to add belief: %s", e)
                raise e
            finally:
                conn.close()
        return bid

    @classmethod
    def get_belief(cls, belief_id: str, db_path: Optional[str] = None) -> Optional[Belief]:
        with cls._lock:
            conn = cls._get_conn(db_path)
            try:
                row = conn.execute("SELECT * FROM hm_beliefs WHERE id = ?", (belief_id,)).fetchone()
                if row:
                    return Belief(
                        belief_id=row["id"],
                        concept=row["concept"],
                        statement=row["statement"],
                        confidence=row["confidence"],
                        source=row["source"],
                        last_verified=row["last_verified"],
                        contradictions=json.loads(row["contradictions"] or "[]")
                    )
            finally:
                conn.close()
        return None

    @classmethod
    def get_all_beliefs(cls, db_path: Optional[str] = None) -> List[Belief]:
        with cls._lock:
            conn = cls._get_conn(db_path)
            try:
                rows = conn.execute("SELECT * FROM hm_beliefs").fetchall()
                return [
                    Belief(
                        belief_id=row["id"],
                        concept=row["concept"],
                        statement=row["statement"],
                        confidence=row["confidence"],
                        source=row["source"],
                        last_verified=row["last_verified"],
                        contradictions=json.loads(row["contradictions"] or "[]")
                    ) for row in rows
                ]
            finally:
                conn.close()
        return []

    @classmethod
    def find_contradictions(cls, statement: str, db_path: Optional[str] = None) -> List[str]:
        """Search existing beliefs for logical contradictions."""
        stmt_lower = statement.lower()
        contradicting_ids = []

        # Simple semantic contradiction rules
        negations = ["not", "fails", "refutes", "never", "no longer"]
        has_negation = any(neg in stmt_lower for neg in negations)

        beliefs = cls.get_all_beliefs(db_path)
        for b in beliefs:
            b_stmt = b.statement.lower()
            # If one has negations and the other does not, but they share core concepts
            # (e.g. 'user prefers Windows' and 'user does not prefer Windows')
            core_words = [w for w in stmt_lower.split() if len(w) > 3 and w not in negations]
            matched = [w for w in core_words if w in b_stmt]
            if len(matched) >= 2:
                b_has_neg = any(neg in b_stmt for neg in negations)
                if has_negation != b_has_neg:
                    contradicting_ids.append(b.belief_id)

        return contradicting_ids

    # ── Forward Simulation & Uncertainty Propagation ────────────────────────
    @classmethod
    def simulate_action(
        cls,
        world_state: Dict[str, Any],
        action: Dict[str, Any],
        steps_count: int = 1
    ) -> TransitionResult:
        """Predicts transition outcome state given action and propagates uncertainty."""
        act_name = action.get("action", "").lower()
        
        # Uncertainty grows logarithmically with step execution depth (information entropy)
        import math
        uncertainty = min(1.0, math.log(steps_count + 1) * 0.3)
        confidence = max(0.0, 1.0 - uncertainty)

        predicted = dict(world_state)
        assumptions = []
        unknowns = []

        if "write" in act_name or "create" in act_name:
            predicted["file_state"] = "created"
            assumptions.append("Target directory exists and has write permissions")
        elif "delete" in act_name or "remove" in act_name:
            predicted["file_state"] = "deleted"
            uncertainty += 0.15  # delete actions introduce execution risks
            assumptions.append("Target file exists")
        else:
            predicted["state"] = "mutated"
            unknowns.append("Unhandled edge action side-effects")

        confidence = max(0.0, min(1.0, confidence - (uncertainty * 0.2)))
        return TransitionResult(
            predicted_state=predicted,
            confidence=round(confidence, 3),
            uncertainty=round(uncertainty, 3),
            assumptions=assumptions,
            unknowns=unknowns
        )

    # ── Counterfactual Engine ───────────────────────────────────────────────
    @classmethod
    def simulate_counterfactual(
        cls,
        hypothetical_modifications: Dict[str, Any],
        simulation_fn: Callable[[Dict[str, Any]], Any],
        db_path: Optional[str] = None
    ) -> Any:
        """Runs simulation over an isolated copy of current beliefs/states.

        This ensures imaginations do not mutate master databases.
        """
        log_event("counterfactual_start", f"Staging counterfactual modifications: {list(hypothetical_modifications.keys())}")
        
        # 1. Staging isolated SQLite DB path
        import tempfile
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        temp_db_path = temp_db.name
        temp_db.close()

        # 2. Copy current beliefs to isolated DB
        beliefs = cls.get_all_beliefs(db_path)
        with cls._lock:
            conn = cls._get_conn(temp_db_path)
            try:
                for b in beliefs:
                    conn.execute(
                        """
                        INSERT INTO hm_beliefs (id, concept, statement, confidence, source, last_verified, contradictions)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (b.belief_id, b.concept, b.statement, b.confidence, b.source, b.last_verified, json.dumps(b.contradictions))
                    )
                conn.commit()
            finally:
                conn.close()

        # 3. Apply hypothetical modifications to the isolated DB
        for key, val in hypothetical_modifications.items():
            cls.add_belief(
                concept=key,
                statement=val.get("statement", ""),
                confidence=val.get("confidence", 1.0),
                source="counterfactual_generator",
                db_path=temp_db_path
            )

        # 4. Execute the simulation on the temp DB
        try:
            result = simulation_fn({"db_path": temp_db_path})
            log_event("counterfactual_complete", "Counterfactual simulation run completed successfully")
            return result
        finally:
            # 5. Cleanup the isolated DB
            import os
            try:
                os.remove(temp_db_path)
            except Exception:
                pass

    # ── Prediction Error Loop ────────────────────────────────────────────────
    @classmethod
    def track_prediction_error(
        cls,
        belief_id: str,
        predicted_outcome: Dict[str, Any],
        actual_outcome: Dict[str, Any],
        db_path: Optional[str] = None
    ) -> float:
        """Calculates prediction deviation and decays belief confidence."""
        # Calculate error delta based on mismatched outcome keys or values
        mismatched_keys = 0
        all_keys = set(predicted_outcome.keys()).union(actual_outcome.keys())
        
        for k in all_keys:
            if predicted_outcome.get(k) != actual_outcome.get(k):
                mismatched_keys += 1

        error_delta = mismatched_keys / len(all_keys) if all_keys else 0.0
        log_event("prediction_error_calculated", f"Prediction Error Delta = {error_delta:.3f}")

        # If error exists, decay the confidence of the parent belief
        if error_delta > 0.0:
            b = cls.get_belief(belief_id, db_path)
            if b:
                new_conf = max(0.0, b.confidence - (error_delta * 0.3))
                with cls._lock:
                    conn = cls._get_conn(db_path)
                    try:
                        conn.execute(
                            "UPDATE hm_beliefs SET confidence = ? WHERE id = ?",
                            (new_conf, belief_id)
                        )
                        conn.commit()
                        log_event("prediction_belief_decayed", f"Decayed belief {belief_id} confidence to {new_conf:.3f}")
                    finally:
                        conn.close()
        
        return error_delta

    @classmethod
    def reset(cls, db_path: Optional[str] = None) -> None:
        with cls._lock:
            conn = cls._get_conn(db_path)
            try:
                conn.execute("DROP TABLE IF EXISTS hm_beliefs")
                conn.commit()
            finally:
                conn.close()
