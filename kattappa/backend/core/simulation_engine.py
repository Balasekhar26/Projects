"""Simulation Engine — Phase K16.5.

Evaluates candidate execution plans by simulating outcome state transitions,
predicting risks and utility values using the World Model, and returning
the optimal plan branch.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass
class SimulationBranchResult:
    branch_id: str
    steps: List[Dict[str, Any]]
    expected_utility: float  # Score from 0.0 to 1.0
    predicted_risk: float  # Score from 0.0 to 1.0
    completion_probability: float  # Score from 0.0 to 1.0
    reason: str


class SimulationEngine:
    """Simulates plan scenarios and computes optimal execution paths."""
    REVIEW_THRESHOLD = 0.10

    @classmethod
    def simulate_plans(
        cls,
        candidate_plans: List[Dict[str, Any]],
        world_state_context: Dict[str, Any]
    ) -> List[SimulationBranchResult]:
        """Simulates outcome state transitions for candidate plans."""
        log_event("simulation_engine_start", f"Simulating {len(candidate_plans)} plan branches")
        results = []

        for idx, plan in enumerate(candidate_plans):
            branch_id = plan.get("id") or f"branch-{idx}"
            steps = plan.get("steps") or []
            
            # Predict outcome per step using mock/transient World Model transitions
            accumulated_risk = 0.0
            accumulated_utility = 1.0
            failures = 0

            for step in steps:
                action = step.get("action", "").lower()
                
                # Simple rule-based prediction transitions:
                # 1. Shell commands carry execution risks
                if "shell" in action or "terminal" in action:
                    accumulated_risk += 0.25
                # 2. Deleting files carries high risk
                if "delete" in action or "remove" in action:
                    accumulated_risk += 0.40
                # 3. Actions with invalid params degrade completion probability
                if not step.get("params"):
                    accumulated_utility *= 0.8
                    failures += 1

            # Normalize risk and compute completion probability
            predicted_risk = min(1.0, accumulated_risk)
            completion_prob = max(0.0, 1.0 - (failures * 0.3))
            
            # Utility = (completion_prob * (1 - risk)) * goal_alignment
            expected_utility = completion_prob * (1.0 - (predicted_risk * 0.5))

            results.append(
                SimulationBranchResult(
                    branch_id=branch_id,
                    steps=steps,
                    expected_utility=round(expected_utility, 3),
                    predicted_risk=round(predicted_risk, 3),
                    completion_probability=round(completion_prob, 3),
                    reason=f"Risk: {predicted_risk:.2f}, Completion Probability: {completion_prob:.2f}"
                )
            )

        # Sort branches descending by expected utility
        results.sort(key=lambda b: b.expected_utility, reverse=True)
        
        if results:
            log_event("simulation_engine_complete", f"Best branch: {results[0].branch_id} (utility={results[0].expected_utility})")
        return results

    @classmethod
    def get_best_plan(
        cls,
        candidate_plans: List[Dict[str, Any]],
        world_state_context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Simulates all candidates and returns the plan dict with highest utility."""
        branches = cls.simulate_plans(candidate_plans, world_state_context)
        if not branches:
            return None
        
        best_branch = branches[0]
        # Locate the original plan dict matching best branch id
        for plan in candidate_plans:
            if plan.get("id") == best_branch.branch_id:
                # Inject simulation metadata
                plan["simulation"] = {
                    "expected_utility": best_branch.expected_utility,
                    "predicted_risk": best_branch.predicted_risk,
                    "completion_probability": best_branch.completion_probability,
                    "reason": best_branch.reason
                }
                return plan
        return candidate_plans[0]

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



@dataclass(frozen=True)
class PlanStep:
    step_id: str
    agent: str
    action: str
    reason: str = ""
    expected_outcome: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int) -> "PlanStep":
        return cls(
            step_id=str(data.get("step_id") or data.get("id") or f"step_{index + 1}"),
            agent=str(data.get("agent") or data.get("owner") or "unknown").strip().lower(),
            action=str(data.get("action") or data.get("action_type") or "UNKNOWN").strip().upper(),
            reason=str(data.get("reason") or data.get("description") or ""),
            expected_outcome=str(data.get("expected_outcome") or data.get("expected") or ""),
            metadata={k: v for k, v in data.items() if k not in {
                "step_id", "id", "agent", "owner", "action", "action_type",
                "reason", "description", "expected_outcome", "expected",
            }},
        )


@dataclass(frozen=True)
class StepPrediction:
    step_id: str
    agent: str
    action: str
    success_probability: float
    failure_probability: float
    resource_cost: float = 0.0
    risk_score: float = 0.0
    rollback_risk: float = 0.0
    expected_duration_ms: int = 0
    adjustments: list[dict[str, Any]] = field(default_factory=list)
    evidence_count: int = 0


@dataclass(frozen=True)
class Risk:
    name: str
    probability: float
    impact: float

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



