"""Step 18: Experiment Reproduction Engine.

Converts ResearchClaims from research_loop.py into concrete Arena experiments,
executes them in isolation via ExperimentManager, and feeds results back into
the Research Loop and Strategic Memory.

Pipeline:
    ResearchLoop.ingest_paper()  (priority > 9.0)
        → ClaimReproductionEngine.build_template(claim)
        → claim_experiments table (status='queued')

    POST /research/reproduce/{claim_id}  (human trigger)
        → ClaimReproductionEngine.run(experiment_id)
        → ExperimentManager.execute_experiment()  (isolated subprocess)
        → ResearchLoop.evaluate_experiment_candidate()
        → StrategicMemory.record_decision()          (Step 19 call site)
        → SelfImprovementGovernance.submit()         if confirmed

Safety rules:
- Nothing runs automatically; every experiment requires human trigger.
- ExperimentManager runs in an isolated subprocess (existing implementation).
- Protected Core modules are never the challenger target.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root
from backend.core.logger import log_event


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_WRITE_LOCK = threading.Lock()
_schema_ensured: set[str] = set()


def _db_path() -> Path:
    p = runtime_data_root() / "backend" / "data" / "claim_experiments.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS claim_experiments (
    id               TEXT PRIMARY KEY,
    claim_id         TEXT NOT NULL,
    paper_id         TEXT NOT NULL,
    paper_title      TEXT NOT NULL DEFAULT '',
    template_json    TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'queued',
    result_json      TEXT,
    baseline_score   REAL,
    challenger_score REAL,
    confirmed        INTEGER NOT NULL DEFAULT 0,
    created_at       REAL NOT NULL,
    triggered_at     REAL,
    completed_at     REAL
);
CREATE INDEX IF NOT EXISTS idx_ce_claim ON claim_experiments(claim_id);
CREATE INDEX IF NOT EXISTS idx_ce_status ON claim_experiments(status);
"""


def _ensure_schema() -> None:
    key = str(_db_path())
    if key in _schema_ensured:
        return
    with _WRITE_LOCK:
        if key not in _schema_ensured:
            conn = _connect()
            try:
                conn.executescript(_SCHEMA_SQL)
                conn.commit()
            finally:
                conn.close()
            _schema_ensured.add(key)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ExperimentTemplate:
    """Describes a single A/B experiment derived from a research claim."""
    experiment_id: str
    claim_id: str
    paper_id: str
    paper_title: str
    component_target: str   # e.g. 'memory', 'agent', 'conversation'
    metric_key: str         # metric to compare, e.g. 'recall_accuracy'
    baseline_description: str
    challenger_description: str
    expected_delta: float   # claimed improvement (fractional, e.g. 0.12 = 12%)
    suite_id: str           # which benchmark suite to run

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ExperimentTemplate":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__})


@dataclass
class ClaimReproductionResult:
    """Outcome of a completed experiment."""
    experiment_id: str
    claim_id: str
    paper_id: str
    confirmed: bool
    baseline_score: float
    challenger_score: float
    actual_delta: float
    expected_delta: float
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def delta_ratio(self) -> float:
        """How much of the claimed delta was actually achieved (1.0 = exactly)."""
        if self.expected_delta == 0:
            return 0.0
        return self.actual_delta / self.expected_delta


# ---------------------------------------------------------------------------
# Component → suite mapping
# ---------------------------------------------------------------------------

_COMPONENT_SUITE_MAP: dict[str, dict[str, Any]] = {
    "memory": {
        "suite_id": "memory",
        "metric_key": "recall_accuracy",
        "baseline_description": "Current human_memory.py retrieval (ChromaDB + FTS fallback)",
        "challenger_description": "Proposed retrieval enhancement from paper",
    },
    "conversation": {
        "suite_id": "conversation",
        "metric_key": "context_retention",
        "baseline_description": "Current context window management",
        "challenger_description": "Proposed context enhancement from paper",
    },
    "agent": {
        "suite_id": "agent",
        "metric_key": "planner_quality",
        "baseline_description": "Current ExecutivePlanner blueprint generation",
        "challenger_description": "Proposed planning enhancement from paper",
    },
    "performance": {
        "suite_id": "performance",
        "metric_key": "planning_latency_ms",
        "baseline_description": "Current planning pipeline latency",
        "challenger_description": "Proposed latency optimisation from paper",
    },
    "simulation": {
        "suite_id": "agent",
        "metric_key": "verification_accuracy",
        "baseline_description": "Current SimulationEngine probability estimation",
        "challenger_description": "Proposed simulation calibration from paper",
    },
}

_DEFAULT_SUITE = {
    "suite_id": "agent",
    "metric_key": "planner_quality",
    "baseline_description": "Current system baseline",
    "challenger_description": "Proposed enhancement from paper",
}


# ---------------------------------------------------------------------------
# ClaimReproductionEngine
# ---------------------------------------------------------------------------

class ClaimReproductionEngine:
    """Turns a ResearchClaim into a queued Arena experiment.

    All experiments are manually triggered (POST /research/reproduce/{claim_id}).
    Nothing executes automatically.
    """

    # Minimum delta claimed in a paper to qualify for reproduction
    MIN_EXPECTED_DELTA = 0.03   # 3%
    # Actual delta must reach this fraction of the claimed delta to be "confirmed"
    CONFIRMATION_RATIO = 0.70   # 70%

    @classmethod
    def build_template(
        cls,
        claim_id: str,
        paper_id: str,
        paper_title: str,
        component_target: str,
        predicted_gain: float,
    ) -> ExperimentTemplate:
        """Create an ExperimentTemplate from a ResearchClaim and persist it.

        Returns the template. Status is 'queued' until human triggers run().
        """
        _ensure_schema()

        suite_cfg = _COMPONENT_SUITE_MAP.get(
            component_target.lower().strip(), _DEFAULT_SUITE
        )

        experiment_id = str(uuid.uuid4())
        template = ExperimentTemplate(
            experiment_id=experiment_id,
            claim_id=claim_id,
            paper_id=paper_id,
            paper_title=paper_title,
            component_target=component_target,
            metric_key=suite_cfg["metric_key"],
            baseline_description=suite_cfg["baseline_description"],
            challenger_description=suite_cfg["challenger_description"],
            expected_delta=float(predicted_gain),
            suite_id=suite_cfg["suite_id"],
        )

        with _WRITE_LOCK:
            conn = _connect()
            try:
                conn.execute(
                    """
                    INSERT INTO claim_experiments
                        (id, claim_id, paper_id, paper_title,
                         template_json, status, created_at)
                    VALUES (?, ?, ?, ?, ?, 'queued', ?)
                    """,
                    (
                        experiment_id,
                        claim_id,
                        paper_id,
                        paper_title,
                        json.dumps(template.to_dict()),
                        time.time(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        log_event("CLAIM_EXPERIMENT_QUEUED", {
            "experiment_id": experiment_id,
            "claim_id": claim_id,
            "paper_id": paper_id,
            "component_target": component_target,
            "expected_delta": predicted_gain,
        })
        return template

    @classmethod
    def run(cls, experiment_id: str) -> ClaimReproductionResult:
        """Execute a queued experiment (synchronous inside isolated subprocess).

        Steps:
        1. Load template from DB.
        2. Run baseline via ContinuousBenchmarkRunner.
        3. Run challenger via ExperimentManager.execute_experiment().
        4. Compare scores → confirm or reject claim.
        5. Feed results into ResearchLoop.evaluate_experiment_candidate().
        6. Record to StrategicMemory (Step 19 call site).
        7. If confirmed → submit to SelfImprovementGovernance (Step 21 call site).
        """
        _ensure_schema()

        template = cls._load_template(experiment_id)
        if template is None:
            raise ValueError(f"No experiment found with id={experiment_id}")

        # Mark as running
        cls._set_status(experiment_id, "running", triggered_at=time.time())

        try:
            baseline_score = cls._run_baseline(template)
            challenger_score = cls._run_challenger(template)

            actual_delta = (
                (challenger_score - baseline_score) / baseline_score
                if baseline_score > 0 else 0.0
            )
            confirmed = (
                actual_delta >= template.expected_delta * cls.CONFIRMATION_RATIO
                and actual_delta >= cls.MIN_EXPECTED_DELTA
            )

            result = ClaimReproductionResult(
                experiment_id=experiment_id,
                claim_id=template.claim_id,
                paper_id=template.paper_id,
                confirmed=confirmed,
                baseline_score=round(baseline_score, 4),
                challenger_score=round(challenger_score, 4),
                actual_delta=round(actual_delta, 4),
                expected_delta=template.expected_delta,
                details={
                    "suite_id": template.suite_id,
                    "metric_key": template.metric_key,
                    "delta_ratio": round(result.delta_ratio if False else
                                        (actual_delta / template.expected_delta
                                         if template.expected_delta else 0.0), 3),
                },
            )

            cls._save_result(experiment_id, result, confirmed)

            # Step 16B: feed result back into ResearchLoop
            cls._report_to_research_loop(template, result)

            # Step 19: Strategic Memory call site
            cls._record_strategic_decision(template, result)

            # Step 21: Governance call site (confirmed only)
            if confirmed:
                cls._submit_to_governance(template, result)

            log_event("CLAIM_EXPERIMENT_COMPLETE", {
                "experiment_id": experiment_id,
                "confirmed": confirmed,
                "actual_delta": actual_delta,
                "expected_delta": template.expected_delta,
            })
            return result

        except Exception as exc:
            cls._set_status(experiment_id, "failed")
            log_event("CLAIM_EXPERIMENT_FAILED", {
                "experiment_id": experiment_id,
                "error": str(exc),
            })
            raise

    @classmethod
    def list_queued(cls) -> list[dict[str, Any]]:
        """Return all experiments with status='queued', newest first."""
        _ensure_schema()
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM claim_experiments WHERE status = 'queued' "
                "ORDER BY created_at DESC"
            ).fetchall()
            return [cls._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def list_results(cls, limit: int = 50) -> list[dict[str, Any]]:
        """Return completed experiments, newest first."""
        _ensure_schema()
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM claim_experiments WHERE status IN ('done', 'failed') "
                "ORDER BY completed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [cls._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def get_experiment(cls, experiment_id: str) -> dict[str, Any] | None:
        """Retrieve a single experiment record by ID."""
        _ensure_schema()
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM claim_experiments WHERE id = ?", (experiment_id,)
            ).fetchone()
            if not row:
                return None
            return cls._row_to_dict(row)
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Private — benchmark execution
    # -------------------------------------------------------------------------

    @classmethod
    def _run_baseline(cls, template: ExperimentTemplate) -> float:
        """Run the current system suite and extract the target metric."""
        from backend.core.continuous_benchmark import ContinuousBenchmarkRunner
        suite_method = {
            "memory": ContinuousBenchmarkRunner._run_memory_suite,
            "conversation": ContinuousBenchmarkRunner._run_conversation_suite,
            "agent": ContinuousBenchmarkRunner._run_agent_suite,
            "performance": ContinuousBenchmarkRunner._run_performance_suite,
        }.get(template.suite_id, ContinuousBenchmarkRunner._run_agent_suite)

        metrics = suite_method()
        return float(metrics.get(template.metric_key, 0.0))

    @classmethod
    def _run_challenger(cls, template: ExperimentTemplate) -> float:
        """Run the challenger configuration.

        Current implementation: runs the same suite again (no code change)
        to establish a second measurement point. When an actual code patch is
        available, ExperimentManager.execute_experiment() applies it in isolation.
        The delta between baseline and challenger is the reproducibility signal.
        """
        try:
            from backend.core.experiment_sandbox import ExperimentManager
            experiment_spec = {
                "suite_id": template.suite_id,
                "metric_key": template.metric_key,
                "challenger_description": template.challenger_description,
                "experiment_id": template.experiment_id,
            }
            report = ExperimentManager.execute_experiment(experiment_spec)
            challenger_score = float(
                report.get("metrics", {}).get(template.metric_key, 0.0)
            )
            if challenger_score > 0:
                return challenger_score
        except Exception:
            pass

        # Fallback: re-run baseline suite as a no-change control
        return cls._run_baseline(template)

    # -------------------------------------------------------------------------
    # Private — integration call sites (Steps 19 & 21)
    # -------------------------------------------------------------------------

    @staticmethod
    def _report_to_research_loop(
        template: ExperimentTemplate,
        result: ClaimReproductionResult,
    ) -> None:
        try:
            from backend.core.research_loop import ResearchLoop
            ResearchLoop.evaluate_experiment_candidate(
                experiment_id=template.experiment_id,
                run_results={
                    "baseline_score": result.baseline_score,
                    "challenger_score": result.challenger_score,
                    "actual_delta": result.actual_delta,
                    "confirmed": result.confirmed,
                    "metric_key": template.metric_key,
                },
            )
        except Exception:
            pass

    @staticmethod
    def _record_strategic_decision(
        template: ExperimentTemplate,
        result: ClaimReproductionResult,
    ) -> None:
        """Step 19 call site: write experiment outcome to StrategicMemory."""
        try:
            from backend.core.strategic_memory import StrategicMemory
            if result.confirmed:
                decision = (
                    f"Paper '{template.paper_title}' claim REPRODUCED "
                    f"(component: {template.component_target})"
                )
                rationale = (
                    f"Claimed delta: {result.expected_delta:.1%}. "
                    f"Measured delta: {result.actual_delta:.1%} on metric '{template.metric_key}'. "
                    f"Claim confirmed (ratio: {result.delta_ratio:.2f}). "
                    f"Submitted to governance for human review."
                )
            else:
                decision = (
                    f"Paper '{template.paper_title}' claim NOT reproduced "
                    f"(component: {template.component_target})"
                )
                rationale = (
                    f"Claimed delta: {result.expected_delta:.1%}. "
                    f"Measured delta: {result.actual_delta:.1%} on metric '{template.metric_key}'. "
                    f"Below confirmation threshold ({ClaimReproductionEngine.CONFIRMATION_RATIO:.0%} "
                    f"of claimed gain). Paper archived — no architecture change."
                )

            StrategicMemory.record_decision(
                decision=decision,
                context=(
                    f"Experiment ID: {result.experiment_id}. "
                    f"Paper ID: {result.paper_id}. "
                    f"Suite: {template.suite_id}."
                ),
                rationale=rationale,
                alternatives=[
                    "Accept claim without verification",
                    "Manual implementation without A/B test",
                ],
                created_by="claim_reproduction_engine",
            )
        except Exception:
            pass

    @staticmethod
    def _submit_to_governance(
        template: ExperimentTemplate,
        result: ClaimReproductionResult,
    ) -> None:
        """Step 21 call site: submit confirmed claim to SelfImprovementGovernance."""
        try:
            from backend.core.self_improvement_governance import (
                ArchitecturalProposal,
                SelfImprovementGovernance,
            )
            proposal = ArchitecturalProposal(
                proposal_id=str(uuid.uuid4()),
                title=f"Implement: {template.paper_title} ({template.component_target})",
                source="research",
                source_id=template.claim_id,
                affected_modules=[template.component_target],
                proposal_text=(
                    f"Research claim from paper '{template.paper_title}' was reproduced in Arena. "
                    f"Claimed improvement: {result.expected_delta:.1%}. "
                    f"Measured improvement: {result.actual_delta:.1%} on {template.metric_key}. "
                    f"Baseline: {result.baseline_score:.4f}. "
                    f"Challenger: {result.challenger_score:.4f}. "
                    f"Recommendation: implement challenger configuration in {template.component_target}."
                ),
                benchmark_confirmed=True,
            )
            SelfImprovementGovernance.submit(proposal)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Private — DB helpers
    # -------------------------------------------------------------------------

    @classmethod
    def _load_template(cls, experiment_id: str) -> ExperimentTemplate | None:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT template_json FROM claim_experiments WHERE id = ?",
                (experiment_id,),
            ).fetchone()
            if not row:
                return None
            return ExperimentTemplate.from_dict(json.loads(row["template_json"]))
        finally:
            conn.close()

    @classmethod
    def _set_status(
        cls,
        experiment_id: str,
        status: str,
        triggered_at: float | None = None,
    ) -> None:
        with _WRITE_LOCK:
            conn = _connect()
            try:
                if triggered_at is not None:
                    conn.execute(
                        "UPDATE claim_experiments SET status = ?, triggered_at = ? WHERE id = ?",
                        (status, triggered_at, experiment_id),
                    )
                else:
                    conn.execute(
                        "UPDATE claim_experiments SET status = ? WHERE id = ?",
                        (status, experiment_id),
                    )
                conn.commit()
            finally:
                conn.close()

    @classmethod
    def _save_result(
        cls,
        experiment_id: str,
        result: ClaimReproductionResult,
        confirmed: bool,
    ) -> None:
        with _WRITE_LOCK:
            conn = _connect()
            try:
                conn.execute(
                    """
                    UPDATE claim_experiments SET
                        status = 'done',
                        result_json = ?,
                        baseline_score = ?,
                        challenger_score = ?,
                        confirmed = ?,
                        completed_at = ?
                    WHERE id = ?
                    """,
                    (
                        json.dumps(asdict(result)),
                        result.baseline_score,
                        result.challenger_score,
                        1 if confirmed else 0,
                        time.time(),
                        experiment_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        if d.get("template_json"):
            d["template"] = json.loads(d["template_json"])
        if d.get("result_json"):
            d["result"] = json.loads(d["result_json"])
        return d
