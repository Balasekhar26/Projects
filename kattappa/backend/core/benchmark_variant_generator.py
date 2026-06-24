"""Step 17: Dynamic Benchmark Evolution (EvoArena).

Prevents Goodhart's Law score inflation by generating surface-different but
semantically equivalent benchmark variants each run. When a suite's score
improvement drops below 2% for 3 consecutive runs (plateau), the variant pool
is automatically expanded.

Design rules:
- Mutation is rule-based (deterministic, fast, fully testable).
- LLM is never called; no network dependency.
- Variants are stored in SQLite and drawn randomly at run time.
- Retired variants are never deleted (audit trail).
- StrategicMemory.record_decision() is called on plateau detection.
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
import string
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root
from backend.core.logger import log_event


# ---------------------------------------------------------------------------
# Domain constants for rule-based mutation
# ---------------------------------------------------------------------------

_FIRST_NAMES = [
    "Alice", "Bob", "Carlos", "Diana", "Ethan", "Fatima", "George", "Hannah",
    "Ivan", "Julia", "Kenji", "Layla", "Marcus", "Nina", "Omar", "Priya",
    "Ravi", "Sara", "Thomas", "Uma", "Victor", "Wren", "Xiao", "Yuki", "Zara",
]

_FRUITS = [
    "apples", "mangoes", "bananas", "oranges", "grapes", "peaches", "kiwis",
    "strawberries", "blueberries", "watermelon", "pears", "cherries",
]

_CITIES = [
    "Tokyo", "Berlin", "Lagos", "Mumbai", "São Paulo", "Cairo", "Toronto",
    "Sydney", "Seoul", "Paris", "Istanbul", "Nairobi", "Buenos Aires",
]

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_COLORS = [
    "red", "blue", "green", "purple", "orange", "teal", "indigo", "amber",
]

_ACTIVITIES = [
    "running", "reading", "cooking", "painting", "coding", "hiking",
    "swimming", "gardening", "writing", "cycling",
]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkCase:
    """A single benchmark test case."""
    case_id: str
    suite_id: str                      # 'memory' | 'conversation' | 'agent' | 'performance'
    input_text: str                    # the prompt / question fed to the system
    expected_answer: str               # ground-truth answer or keyword to match
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BenchmarkCase":
        return cls(
            case_id=d["case_id"],
            suite_id=d["suite_id"],
            input_text=d["input_text"],
            expected_answer=d["expected_answer"],
            metadata=d.get("metadata", {}),
        )


@dataclass
class PlateauReport:
    """Result of detect_plateau()."""
    suite_id: str
    plateau_detected: bool
    run_scores: list[float]            # last N scores checked
    mean_improvement: float            # avg delta across window
    variants_generated: int = 0


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

_WRITE_LOCK = threading.Lock()


def _db_path() -> Path:
    p = runtime_data_root() / "backend" / "data" / "benchmark_variants.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS benchmark_variants (
    id             TEXT PRIMARY KEY,
    suite_id       TEXT NOT NULL,
    seed_case_id   TEXT,
    case_json      TEXT NOT NULL,
    generation     INTEGER NOT NULL DEFAULT 1,
    created_at     REAL NOT NULL,
    retired        INTEGER NOT NULL DEFAULT 0,
    score_history  TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_bv_suite ON benchmark_variants(suite_id);
CREATE INDEX IF NOT EXISTS idx_bv_retired ON benchmark_variants(retired);

CREATE TABLE IF NOT EXISTS benchmark_suite_runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    suite_id   TEXT NOT NULL,
    run_score  REAL NOT NULL,
    run_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bsr_suite ON benchmark_suite_runs(suite_id, run_at DESC);
"""

_schema_ensured: set[str] = set()


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
# Mutation Engine (rule-based, no LLM)
# ---------------------------------------------------------------------------

class _RuleBasedMutator:
    """Applies deterministic surface-level substitutions to a seed case.

    Preserves semantic structure and expected-answer type so the test
    remains validly answerable after mutation.
    """

    _FRUIT_PATTERN = re.compile(
        r"\b(" + "|".join(_FRUITS) + r")\b", re.IGNORECASE
    )
    _NAME_PATTERN = re.compile(
        r"\b(" + "|".join(_FIRST_NAMES) + r")\b"
    )
    _DAY_PATTERN = re.compile(
        r"\b(" + "|".join(_DAYS) + r")\b", re.IGNORECASE
    )
    _COLOR_PATTERN = re.compile(
        r"\b(" + "|".join(_COLORS) + r")\b", re.IGNORECASE
    )
    _CITY_PATTERN = re.compile(
        r"\b(" + "|".join(_CITIES) + r")\b"
    )
    _NUMBER_PATTERN = re.compile(r"\b(\d{1,4})\b")

    @classmethod
    def mutate(
        cls,
        seed: BenchmarkCase,
        rng: random.Random,
        generation: int,
    ) -> BenchmarkCase:
        """Return a new BenchmarkCase with surface mutations applied."""
        text = seed.input_text
        expected = seed.expected_answer

        text, expected = cls._swap_fruit(text, expected, rng)
        text, expected = cls._swap_name(text, expected, rng)
        text, expected = cls._swap_day(text, expected, rng)
        text, expected = cls._swap_color(text, expected, rng)
        text, expected = cls._swap_city(text, expected, rng)
        text, expected = cls._perturb_numbers(text, expected, rng)

        return BenchmarkCase(
            case_id=f"var_{uuid.uuid4().hex[:10]}",
            suite_id=seed.suite_id,
            input_text=text,
            expected_answer=expected,
            metadata={
                **seed.metadata,
                "seed_case_id": seed.case_id,
                "generation": generation,
                "mutation_ts": time.time(),
            },
        )

    @classmethod
    def _swap_fruit(
        cls, text: str, expected: str, rng: random.Random
    ) -> tuple[str, str]:
        match = cls._FRUIT_PATTERN.search(text)
        if not match:
            return text, expected
        old = match.group(0)
        new = rng.choice([f for f in _FRUITS if f.lower() != old.lower()])
        text = cls._FRUIT_PATTERN.sub(new, text)
        expected = re.sub(re.escape(old), new, expected, flags=re.IGNORECASE)
        return text, expected

    @classmethod
    def _swap_name(
        cls, text: str, expected: str, rng: random.Random
    ) -> tuple[str, str]:
        match = cls._NAME_PATTERN.search(text)
        if not match:
            return text, expected
        old = match.group(0)
        new = rng.choice([n for n in _FIRST_NAMES if n != old])
        text = re.sub(r"\b" + re.escape(old) + r"\b", new, text)
        expected = re.sub(r"\b" + re.escape(old) + r"\b", new, expected)
        return text, expected

    @classmethod
    def _swap_day(
        cls, text: str, expected: str, rng: random.Random
    ) -> tuple[str, str]:
        match = cls._DAY_PATTERN.search(text)
        if not match:
            return text, expected
        old = match.group(0)
        new = rng.choice([d for d in _DAYS if d.lower() != old.lower()])
        text = cls._DAY_PATTERN.sub(new, text)
        expected = re.sub(re.escape(old), new, expected, flags=re.IGNORECASE)
        return text, expected

    @classmethod
    def _swap_color(
        cls, text: str, expected: str, rng: random.Random
    ) -> tuple[str, str]:
        match = cls._COLOR_PATTERN.search(text)
        if not match:
            return text, expected
        old = match.group(0)
        new = rng.choice([c for c in _COLORS if c.lower() != old.lower()])
        text = cls._COLOR_PATTERN.sub(new, text)
        expected = re.sub(re.escape(old), new, expected, flags=re.IGNORECASE)
        return text, expected

    @classmethod
    def _swap_city(
        cls, text: str, expected: str, rng: random.Random
    ) -> tuple[str, str]:
        match = cls._CITY_PATTERN.search(text)
        if not match:
            return text, expected
        old = match.group(0)
        new = rng.choice([c for c in _CITIES if c != old])
        text = re.sub(r"\b" + re.escape(old) + r"\b", new, text)
        expected = re.sub(r"\b" + re.escape(old) + r"\b", new, expected)
        return text, expected

    @classmethod
    def _perturb_numbers(
        cls, text: str, expected: str, rng: random.Random
    ) -> tuple[str, str]:
        """Replace the first standalone integer with a nearby value (±10–30%)."""
        match = cls._NUMBER_PATTERN.search(text)
        if not match:
            return text, expected
        old_val = int(match.group(0))
        if old_val == 0:
            return text, expected
        delta = max(1, int(old_val * rng.uniform(0.10, 0.30)))
        new_val = old_val + rng.choice([-delta, delta])
        new_val = max(1, new_val)
        text = text[:match.start()] + str(new_val) + text[match.end():]
        expected = re.sub(r"\b" + re.escape(str(old_val)) + r"\b", str(new_val), expected)
        return text, expected


# ---------------------------------------------------------------------------
# BenchmarkVariantGenerator — public API
# ---------------------------------------------------------------------------

class BenchmarkVariantGenerator:
    """Manages the dynamic pool of benchmark variants per suite.

    Public API
    ----------
    generate_variants(seed, n)   → list[BenchmarkCase]
    register_variant(suite, case) → variant_id
    get_pool(suite_id)           → list[BenchmarkCase]
    mark_retired(variant_id)
    record_run_score(suite_id, score)
    detect_plateau(suite_id, window=3, threshold=0.02) → PlateauReport
    """

    PLATEAU_WINDOW = 3       # consecutive runs to evaluate
    PLATEAU_THRESHOLD = 0.02 # < 2% mean improvement = plateau

    @classmethod
    def generate_variants(
        cls,
        seed_case: BenchmarkCase,
        n: int = 5,
        *,
        seed_int: int | None = None,
    ) -> list[BenchmarkCase]:
        """Generate N surface-mutated variants from a seed case.

        Each variant is registered in the DB immediately.
        Returns the list of newly created BenchmarkCase objects.
        """
        _ensure_schema()
        rng = random.Random(seed_int)  # deterministic if seed given
        variants: list[BenchmarkCase] = []
        generation = cls._next_generation(seed_case.case_id)

        with _WRITE_LOCK:
            conn = _connect()
            try:
                for _ in range(n):
                    variant = _RuleBasedMutator.mutate(seed_case, rng, generation)
                    cls._insert_variant(conn, variant, seed_case.case_id, generation)
                    variants.append(variant)
                conn.commit()
            finally:
                conn.close()

        log_event("BENCHMARK_VARIANTS_GENERATED", {
            "suite_id": seed_case.suite_id,
            "seed_case_id": seed_case.case_id,
            "count": n,
            "generation": generation,
        })
        return variants

    @classmethod
    def register_variant(
        cls,
        suite_id: str,
        case: BenchmarkCase,
        seed_case_id: str | None = None,
    ) -> str:
        """Persist an externally constructed variant into the pool."""
        _ensure_schema()
        with _WRITE_LOCK:
            conn = _connect()
            try:
                cls._insert_variant(conn, case, seed_case_id, generation=1)
                conn.commit()
            finally:
                conn.close()
        return case.case_id

    @classmethod
    def get_pool(
        cls,
        suite_id: str,
        *,
        include_retired: bool = False,
        limit: int = 200,
    ) -> list[BenchmarkCase]:
        """Return the active variant pool for a suite (random draw order)."""
        _ensure_schema()
        conn = _connect()
        try:
            if include_retired:
                rows = conn.execute(
                    "SELECT case_json FROM benchmark_variants WHERE suite_id = ? LIMIT ?",
                    (suite_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT case_json FROM benchmark_variants "
                    "WHERE suite_id = ? AND retired = 0 LIMIT ?",
                    (suite_id, limit),
                ).fetchall()
            cases = [BenchmarkCase.from_dict(json.loads(r["case_json"])) for r in rows]
            random.shuffle(cases)
            return cases
        finally:
            conn.close()

    @classmethod
    def mark_retired(cls, variant_id: str) -> None:
        """Mark a variant as retired (excluded from future draws)."""
        _ensure_schema()
        with _WRITE_LOCK:
            conn = _connect()
            try:
                conn.execute(
                    "UPDATE benchmark_variants SET retired = 1 WHERE id = ?",
                    (variant_id,),
                )
                conn.commit()
            finally:
                conn.close()

    @classmethod
    def record_run_score(cls, suite_id: str, score: float) -> None:
        """Record the mean score from a completed benchmark run for a suite."""
        _ensure_schema()
        with _WRITE_LOCK:
            conn = _connect()
            try:
                conn.execute(
                    "INSERT INTO benchmark_suite_runs (suite_id, run_score, run_at) VALUES (?, ?, ?)",
                    (suite_id, float(score), time.time()),
                )
                conn.commit()
            finally:
                conn.close()

    @classmethod
    def detect_plateau(
        cls,
        suite_id: str,
        *,
        window: int = 3,
        threshold: float = 0.02,
    ) -> PlateauReport:
        """Analyse recent run history for score plateau.

        Returns PlateauReport. If plateau is detected:
        - Logs to StrategicMemory.record_decision() (call site for Step 19).
        - Returns plateau_detected=True so caller can trigger variant expansion.
        """
        _ensure_schema()
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT run_score FROM benchmark_suite_runs "
                "WHERE suite_id = ? ORDER BY run_at DESC LIMIT ?",
                (suite_id, window + 1),
            ).fetchall()
        finally:
            conn.close()

        scores = [r["run_score"] for r in rows]
        if len(scores) < window:
            return PlateauReport(
                suite_id=suite_id,
                plateau_detected=False,
                run_scores=scores,
                mean_improvement=0.0,
            )

        # Scores are newest-first; reverse so we compute forward deltas
        scores_asc = list(reversed(scores[:window]))
        deltas = []
        for i in range(1, len(scores_asc)):
            prev = scores_asc[i - 1]
            if prev > 0:
                deltas.append((scores_asc[i] - prev) / prev)

        mean_improvement = sum(deltas) / len(deltas) if deltas else 0.0
        plateau = mean_improvement < threshold

        if plateau:
            cls._record_plateau_decision(suite_id, scores_asc, mean_improvement)
            log_event("BENCHMARK_PLATEAU_DETECTED", {
                "suite_id": suite_id,
                "mean_improvement": round(mean_improvement, 4),
                "window": window,
            })

        return PlateauReport(
            suite_id=suite_id,
            plateau_detected=plateau,
            run_scores=scores_asc,
            mean_improvement=round(mean_improvement, 4),
        )

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _insert_variant(
        conn: sqlite3.Connection,
        case: BenchmarkCase,
        seed_case_id: str | None,
        generation: int,
    ) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO benchmark_variants
                (id, suite_id, seed_case_id, case_json, generation, created_at, retired, score_history)
            VALUES (?, ?, ?, ?, ?, ?, 0, '[]')
            """,
            (
                case.case_id,
                case.suite_id,
                seed_case_id,
                json.dumps(case.to_dict()),
                generation,
                time.time(),
            ),
        )

    @classmethod
    def _next_generation(cls, seed_case_id: str) -> int:
        """Return max(generation) + 1 for variants derived from this seed."""
        _ensure_schema()
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT MAX(generation) AS mg FROM benchmark_variants WHERE seed_case_id = ?",
                (seed_case_id,),
            ).fetchone()
            return (row["mg"] or 0) + 1
        finally:
            conn.close()

    @staticmethod
    def _record_plateau_decision(
        suite_id: str,
        scores: list[float],
        mean_improvement: float,
    ) -> None:
        """Step 19 call site: write plateau detection to StrategicMemory."""
        try:
            from backend.core.strategic_memory import StrategicMemory
            StrategicMemory.record_decision(
                decision=f"Benchmark plateau detected in suite '{suite_id}'",
                context=(
                    f"Last {len(scores)} run scores: {[round(s, 3) for s in scores]}. "
                    f"Mean improvement: {mean_improvement:.4f} (threshold: "
                    f"{BenchmarkVariantGenerator.PLATEAU_THRESHOLD})."
                ),
                rationale=(
                    "Score improvement fell below the plateau threshold, indicating the system "
                    "may be learning to pass fixed test cases rather than genuinely improving. "
                    "New surface-mutated variants will be generated to prevent Goodhart's Law inflation."
                ),
                alternatives=["Keep static suite", "Switch to LLM-generated variants"],
                created_by="benchmark_variant_generator",
            )
        except Exception:
            # Strategic Memory write failure must never crash the benchmark run
            pass
