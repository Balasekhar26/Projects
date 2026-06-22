"""Value Engine (post-Consensus plan preference).

Position in the pipeline:

    Validators -> Consensus -> Trust & Evidence -> VALUE ENGINE -> Policy -> Human -> Execute

Truth comes from validators; acceptability from consensus; evidence from trust.
The Value Engine answers only: "Among already-valid plans, which best matches
Kattappa's operating philosophy?"

Two hard design rules, both enforced here:

* **Lenses are objective projections, not LLM ratings.** Each lens is a
  deterministic function of measurable plan signals (validator/test/reliability
  scores, World-Model blast radius, step/component counts, capability coverage,
  simulation success, goal match...). No model judgment, so no fake independence
  and no prompt-injection of scores.
* **User intent is a GATE, not a weight.** A plan that contradicts explicit user
  intent is disqualified and can never outrank a compliant plan — it does not
  merely lose 20%.

Rank-only contract: the engine always produces an ordering. It never blocks,
vetoes, escalates, or overrides consensus/policy.

Archetype -> lens mapping (output keys):
    Rama=ethics, Brahma=creativity, Shiva=simplification, Krishna=strategy,
    Kattappa=loyalty, Vishwakarma=feasibility.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


# ---------------------------------------------------------------------------
# Plan signals (objective inputs from the existing subsystems)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanSignals:
    name: str
    # Rama / ethics
    validator_score: float = 1.0
    reliability_score: float = 0.5
    test_score: float = 0.5
    safety_score: float = 1.0
    blast_radius: int = 0          # World Model: entities affected (smaller better)
    # Brahma / creativity (the one partly-subjective lens; supplied, not invented)
    novelty: float = 0.5
    # Shiva / simplification
    steps: int = 1
    components: int = 0
    dependencies: int = 0
    # Krishna / strategy
    reversible: bool = True
    optionality: float = 0.5
    resource_preservation: float = 0.5
    # Kattappa / loyalty
    goal_match: float = 0.5
    contradicts_user_intent: bool = False   # the GATE
    # Vishwakarma / feasibility
    capability_coverage: float = 1.0
    sim_success: float = 1.0
    cost_score: float = 0.5        # higher = cheaper
    # Tiebreak only
    trust_score: float = 0.5

    @property
    def complexity(self) -> int:
        return self.steps + self.components + self.dependencies

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanSignals":
        fields = {f for f in cls.__dataclass_fields__ if f != "name"}
        kwargs = {k: data[k] for k in fields if k in data}
        return cls(name=str(data.get("name", "plan")), **kwargs)


# ---------------------------------------------------------------------------
# Lenses (deterministic projections)
# ---------------------------------------------------------------------------

LENSES = ("ethics", "creativity", "simplification", "strategy", "loyalty", "feasibility")


def lens_scores(s: PlanSignals) -> dict[str, float]:
    ethics = _clamp(
        0.30 * s.validator_score + 0.25 * s.reliability_score
        + 0.25 * s.test_score + 0.20 * s.safety_score
    )
    creativity = _clamp(s.novelty)
    simplification = _clamp(1.0 - 0.06 * max(0, s.complexity - 1))
    strategy = _clamp(
        0.40 * (1.0 if s.reversible else 0.0)
        + 0.30 * s.optionality + 0.30 * s.resource_preservation
    )
    loyalty = _clamp(s.goal_match)
    feasibility = _clamp(
        0.40 * s.capability_coverage + 0.35 * s.sim_success + 0.25 * s.cost_score
    )
    return {
        "ethics": round(ethics, 4),
        "creativity": round(creativity, 4),
        "simplification": round(simplification, 4),
        "strategy": round(strategy, 4),
        "loyalty": round(loyalty, 4),
        "feasibility": round(feasibility, 4),
    }


# ---------------------------------------------------------------------------
# Context weight profiles (fixed, auditable; never dynamically skewed)
# ---------------------------------------------------------------------------

class ValueProfile(str, Enum):
    DEFAULT = "default"
    GREENFIELD = "greenfield"
    PRODUCTION = "production"
    INCIDENT = "incident"

    @classmethod
    def coerce(cls, value: "ValueProfile | str") -> "ValueProfile":
        return value if isinstance(value, cls) else cls(str(value).strip().lower())


# weights map archetype emphasis onto the lenses; each profile sums to 1.00
PROFILES: dict[ValueProfile, dict[str, float]] = {
    ValueProfile.DEFAULT: {"ethics": 0.25, "strategy": 0.10, "creativity": 0.25,
                           "simplification": 0.10, "loyalty": 0.20, "feasibility": 0.10},
    ValueProfile.GREENFIELD: {"ethics": 0.20, "strategy": 0.10, "creativity": 0.35,
                              "simplification": 0.10, "loyalty": 0.15, "feasibility": 0.10},
    ValueProfile.PRODUCTION: {"ethics": 0.35, "strategy": 0.10, "creativity": 0.10,
                              "simplification": 0.15, "loyalty": 0.20, "feasibility": 0.10},
    ValueProfile.INCIDENT: {"ethics": 0.30, "strategy": 0.20, "creativity": 0.05,
                            "simplification": 0.10, "loyalty": 0.25, "feasibility": 0.10},
}


def weighted_score(scores: dict[str, float], profile: ValueProfile) -> float:
    weights = PROFILES[profile]
    return round(sum(weights[lens] * scores[lens] for lens in LENSES), 4)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RankedPlan:
    name: str
    final_score: float
    lens_scores: dict[str, float]
    disqualified: bool
    signals: PlanSignals

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "final_score": self.final_score,
            "lens_scores": self.lens_scores,
            "disqualified": self.disqualified,
        }


@dataclass(frozen=True)
class ValueRanking:
    profile: ValueProfile
    ranked: list[RankedPlan]
    selected: RankedPlan | None
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.value,
            "ranked": [r.to_dict() for r in self.ranked],
            "selected": self.selected.to_dict() if self.selected else None,
            "warning": self.warning,
        }


class ValueEngine:
    """Ranks valid plans by value alignment. Never blocks, vetoes, or overrides."""

    @classmethod
    def score_plan(cls, signals: PlanSignals) -> dict[str, float]:
        """The required output: per-lens scores for a single plan."""
        return lens_scores(signals)

    @classmethod
    def rank(
        cls, plans: list[PlanSignals], profile: ValueProfile | str = ValueProfile.DEFAULT
    ) -> ValueRanking:
        profile = ValueProfile.coerce(profile)
        ranked: list[RankedPlan] = []
        for s in plans:
            scores = lens_scores(s)
            final = weighted_score(scores, profile)
            ranked.append(RankedPlan(s.name, final, scores, s.contradicts_user_intent, s))

        # Gate: disqualified plans sort strictly below qualified ones, then by
        # final score, then deterministic tiebreakers.
        def key(r: RankedPlan) -> tuple:
            s = r.signals
            return (
                1 if r.disqualified else 0,
                -r.final_score,
                -s.goal_match,        # 1. higher user alignment
                -s.trust_score,       # 2. higher trust
                s.complexity,         # 3. lower complexity
                s.blast_radius,       # 4. smaller blast radius
                -s.cost_score,        # 5. lower cost (higher cost_score)
                r.name,
            )

        ranked.sort(key=key)
        selected = ranked[0] if ranked else None
        warning = ""
        if selected is not None and selected.disqualified:
            warning = "all candidates conflict with explicit user intent"
        return ValueRanking(profile, ranked, selected, warning)

    # -- consensus integration --------------------------------------------
    @classmethod
    def rank_after_consensus(
        cls,
        consensus_decision: Any,
        plans: list[PlanSignals],
        profile: ValueProfile | str = ValueProfile.DEFAULT,
    ) -> ValueRanking | None:
        """Only ranks plans that consensus already approved. Never alters consensus."""
        from backend.core.consensus_engine import ConsensusStatus

        status = getattr(consensus_decision, "status", None)
        if status is not ConsensusStatus.APPROVED:
            return None  # nothing valid to rank; the engine does not act
        return cls.rank(plans, profile)


# ---------------------------------------------------------------------------
# Value Drift Monitor (advisory only)
# ---------------------------------------------------------------------------

def _drift_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "value_drift.json"


class ValueDriftMonitor:
    _lock = threading.Lock()
    _window = 100
    _dominance_threshold = 0.70

    @classmethod
    def _load(cls) -> dict[str, Any]:
        try:
            p = _drift_path()
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"decisions": []}

    @classmethod
    def _save(cls, data: dict[str, Any]) -> None:
        try:
            p = _drift_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def record(cls, ranking: ValueRanking, *, novel: bool = False) -> None:
        if ranking.selected is None:
            return
        with cls._lock:
            data = cls._load()
            decisions = data.setdefault("decisions", [])
            dominant = max(ranking.selected.lens_scores.items(), key=lambda kv: kv[1])[0]
            decisions.append({
                "selected": ranking.selected.name,
                "profile": ranking.profile.value,
                "lens_scores": ranking.selected.lens_scores,
                "dominant_lens": dominant,
                "novel": bool(novel),
                "ts": time.time(),
            })
            data["decisions"] = decisions[-cls._window:]
            cls._save(data)

    @classmethod
    def report(cls) -> dict[str, Any]:
        decisions = cls._load().get("decisions", [])
        n = len(decisions)
        if n == 0:
            return {"decisions": 0, "warnings": []}
        averages = {lens: round(sum(d["lens_scores"][lens] for d in decisions) / n, 4)
                    for lens in LENSES}
        dom_counts: dict[str, int] = {}
        for d in decisions:
            dom_counts[d["dominant_lens"]] = dom_counts.get(d["dominant_lens"], 0) + 1
        novel_ratio = round(sum(1 for d in decisions if d.get("novel")) / n, 4)

        warnings: list[str] = []
        for lens, count in dom_counts.items():
            if count / n >= cls._dominance_threshold:
                warnings.append(
                    f"decision diversity collapsing: '{lens}' dominant in {round(100*count/n)}% "
                    "of recent decisions"
                )
        if novel_ratio <= 0.05 and n >= 20:
            warnings.append("novelty near zero: decisions may be too conservative")

        return {
            "decisions": n,
            "lens_averages": averages,
            "dominant_lens_distribution": dom_counts,
            "novel_ratio": novel_ratio,
            "warnings": warnings,  # advisory only; no automatic corrections
        }

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._save({"decisions": []})
