"""Simulation Engine (Tier 2).

Predict before acting: between Plan and Execute, run a seeded Monte-Carlo over a
scenario's risk model to estimate success/failure and rank the dominant risks.

    Plan -> SIMULATE -> Validate -> Execute

Deterministic (seeded) so the same scenario always yields the same prediction.
It predicts; it never executes.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Risk:
    name: str
    probability: float   # chance this risk occurs in a trial
    impact: float        # given it occurs, chance it causes failure

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Risk":
        return cls(
            name=str(data.get("name", "risk")),
            probability=max(0.0, min(1.0, float(data.get("probability", 0.0)))),
            impact=max(0.0, min(1.0, float(data.get("impact", 0.0)))),
        )


@dataclass(frozen=True)
class Scenario:
    name: str
    base_success_prob: float = 1.0
    risks: tuple[Risk, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scenario":
        return cls(
            name=str(data.get("name", "scenario")),
            base_success_prob=max(0.0, min(1.0, float(data.get("base_success_prob", 1.0)))),
            risks=tuple(Risk.from_dict(r) for r in data.get("risks", [])),
        )


@dataclass(frozen=True)
class SimulationReport:
    scenario: str
    trials: int
    seed: int
    success_rate: float
    failure_rate: float
    top_risks: list[dict[str, Any]] = field(default_factory=list)
    recommendation: str = ""

    @property
    def success_pct(self) -> float:
        return round(self.success_rate * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "trials": self.trials,
            "seed": self.seed,
            "success_rate": round(self.success_rate, 4),
            "failure_rate": round(self.failure_rate, 4),
            "success_pct": self.success_pct,
            "failure_pct": round(self.failure_rate * 100, 1),
            "top_risks": self.top_risks,
            "recommendation": self.recommendation,
        }


class SimulationEngine:
    REVIEW_THRESHOLD = 0.10  # failure rate above which a human review is advised

    @classmethod
    def simulate(cls, scenario: Scenario, *, trials: int = 1000, seed: int = 42) -> SimulationReport:
        rng = random.Random(seed)
        success = 0
        fail_attrib: dict[str, int] = {r.name: 0 for r in scenario.risks}

        for _ in range(trials):
            failed = False
            cause: str | None = None
            if rng.random() > scenario.base_success_prob:
                failed = True  # base uncertainty (unattributed)
            for r in scenario.risks:
                occurred = rng.random() < r.probability
                if occurred and rng.random() < r.impact:
                    if not failed:
                        cause = r.name
                    failed = True
            if failed:
                if cause is not None:
                    fail_attrib[cause] += 1
            else:
                success += 1

        success_rate = success / trials if trials else 0.0
        failure_rate = 1.0 - success_rate
        top_risks = sorted(
            ({"risk": name, "failure_contribution": round(count / trials, 4)}
             for name, count in fail_attrib.items() if count > 0),
            key=lambda d: d["failure_contribution"], reverse=True,
        )
        if failure_rate > cls.REVIEW_THRESHOLD:
            recommendation = "human review advised: failure risk exceeds threshold"
        else:
            recommendation = "acceptable risk: proceed to validation"
        return SimulationReport(
            scenario=scenario.name, trials=trials, seed=seed,
            success_rate=success_rate, failure_rate=failure_rate,
            top_risks=top_risks, recommendation=recommendation,
        )

    @classmethod
    def simulate_dict(cls, raw: dict[str, Any], *, trials: int = 1000, seed: int = 42) -> SimulationReport:
        return cls.simulate(Scenario.from_dict(raw), trials=trials, seed=seed)
