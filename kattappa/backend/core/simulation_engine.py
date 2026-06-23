"""Simulation Engine (Tier 2).

Predict before acting: between Plan and Execute, run a seeded Monte-Carlo over a
scenario's risk model to estimate success/failure and rank the dominant risks.

    Plan -> SIMULATE -> Validate -> Execute

Deterministic (seeded) so the same scenario always yields the same prediction.
It predicts; it never executes.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


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
    expected_duration_ms: int
    rollback_risk: float
    confidence_score: float
    evidence_count: int
    adjustments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "agent": self.agent,
            "action": self.action,
            "success_probability": round(self.success_probability, 4),
            "failure_probability": round(self.failure_probability, 4),
            "expected_duration_ms": self.expected_duration_ms,
            "rollback_risk": round(self.rollback_risk, 4),
            "confidence_score": round(self.confidence_score, 4),
            "evidence_count": self.evidence_count,
            "adjustments": self.adjustments,
        }


@dataclass(frozen=True)
class PlanSimulationReport:
    goal: str
    workflow_id: str
    success_probability: float
    failure_probability: float
    estimated_duration_ms: int
    rollback_risk: float
    rollback_risk_level: str
    step_predictions: list[StepPrediction]
    likely_failures: list[dict[str, Any]]
    policy_adjustments: list[dict[str, Any]]
    reflection_signals: list[dict[str, Any]]
    recommendation: str
    data_sources: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "workflow_id": self.workflow_id,
            "success_probability": round(self.success_probability, 4),
            "failure_probability": round(self.failure_probability, 4),
            "success_pct": round(self.success_probability * 100, 1),
            "failure_pct": round(self.failure_probability * 100, 1),
            "estimated_duration_ms": self.estimated_duration_ms,
            "estimated_duration_seconds": round(self.estimated_duration_ms / 1000, 2),
            "rollback_risk": round(self.rollback_risk, 4),
            "rollback_risk_level": self.rollback_risk_level,
            "step_predictions": [step.to_dict() for step in self.step_predictions],
            "likely_failures": self.likely_failures,
            "policy_adjustments": self.policy_adjustments,
            "reflection_signals": self.reflection_signals,
            "recommendation": self.recommendation,
            "data_sources": self.data_sources,
        }


class SimulationEngine:
    REVIEW_THRESHOLD = 0.10  # failure rate above which a human review is advised
    DEFAULT_AGENT_SUCCESS = {
        "browser": 0.78,
        "researcher": 0.76,
        "coder": 0.74,
        "file": 0.76,
        "desktop": 0.62,
        "voice": 0.70,
        "terminal": 0.68,
        "monitoring": 0.90,
        "memory_service": 0.86,
    }

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

    @classmethod
    def simulate_plan(
        cls,
        plan: list[dict[str, Any]],
        *,
        goal: str = "",
        workflow_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> PlanSimulationReport:
        """Predict plan success before execution using local experience data."""
        steps = [PlanStep.from_dict(raw, index) for index, raw in enumerate(plan)]
        active_policies = cls._load_active_policies()
        reflection = cls._load_latest_reflection_report()
        reflection_agent_stats = cls._reflection_agent_stats(reflection)
        reflection_recs = cls._reflection_recommendations(reflection)

        predictions: list[StepPrediction] = []
        policy_adjustments: list[dict[str, Any]] = []
        reflection_signals: list[dict[str, Any]] = []

        for step in steps:
            prediction, policies, signals = cls._predict_step(
                step,
                active_policies=active_policies,
                reflection_agent_stats=reflection_agent_stats,
                reflection_recommendations=reflection_recs,
                context=context or {},
            )
            predictions.append(prediction)
            policy_adjustments.extend(policies)
            reflection_signals.extend(signals)

        if not predictions:
            return PlanSimulationReport(
                goal=goal,
                workflow_id=workflow_id,
                success_probability=1.0,
                failure_probability=0.0,
                estimated_duration_ms=0,
                rollback_risk=0.0,
                rollback_risk_level="low",
                step_predictions=[],
                likely_failures=[],
                policy_adjustments=[],
                reflection_signals=[],
                recommendation="no executable steps supplied",
                data_sources=cls._source_summary(active_policies, reflection),
            )

        success_probability = 1.0
        rollback_safe_probability = 1.0
        estimated_duration_ms = 0
        for prediction in predictions:
            success_probability *= prediction.success_probability
            rollback_safe_probability *= (1.0 - prediction.rollback_risk)
            estimated_duration_ms += prediction.expected_duration_ms

        rollback_risk = _clamp(1.0 - rollback_safe_probability)
        likely_failures = sorted(
            (
                {
                    "step_id": prediction.step_id,
                    "agent": prediction.agent,
                    "action": prediction.action,
                    "failure_probability": round(prediction.failure_probability, 4),
                    "reason": cls._failure_reason(prediction),
                }
                for prediction in predictions
                if prediction.failure_probability >= 0.10
            ),
            key=lambda item: item["failure_probability"],
            reverse=True,
        )
        recommendation = cls._plan_recommendation(success_probability, rollback_risk)

        return PlanSimulationReport(
            goal=goal,
            workflow_id=workflow_id,
            success_probability=_clamp(success_probability),
            failure_probability=_clamp(1.0 - success_probability),
            estimated_duration_ms=estimated_duration_ms,
            rollback_risk=rollback_risk,
            rollback_risk_level=cls._risk_level(rollback_risk),
            step_predictions=predictions,
            likely_failures=likely_failures,
            policy_adjustments=policy_adjustments,
            reflection_signals=reflection_signals,
            recommendation=recommendation,
            data_sources=cls._source_summary(active_policies, reflection),
        )

    @classmethod
    def _predict_step(
        cls,
        step: PlanStep,
        *,
        active_policies: list[dict[str, Any]],
        reflection_agent_stats: dict[str, dict[str, Any]],
        reflection_recommendations: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> tuple[StepPrediction, list[dict[str, Any]], list[dict[str, Any]]]:
        from backend.core.action_memory import ActionMemory

        action_stats = ActionMemory.get_action_type_statistics(step.action)
        agent_stats = ActionMemory.get_agent_statistics(step.agent).to_dict()
        action_count = int(action_stats.get("total_executions") or 0)
        agent_count = int(agent_stats.get("total_actions") or 0)
        default_success = cls.DEFAULT_AGENT_SUCCESS.get(step.agent, 0.68)

        if action_count:
            raw_success = float(action_stats.get("success_rate") or 0.0)
            evidence_count = action_count
            avg_duration_ms = int(action_stats.get("avg_duration_ms") or 0)
            avg_confidence = float(action_stats.get("avg_confidence") or 0.0)
            rollback_count = int(action_stats.get("rollback_count") or 0)
            rollback_risk = rollback_count / action_count
        elif agent_count:
            raw_success = float(agent_stats.get("success_rate") or default_success)
            evidence_count = agent_count
            avg_duration_ms = int(agent_stats.get("avg_duration_ms") or 0)
            avg_confidence = float(agent_stats.get("avg_confidence") or 0.0)
            rollback_risk = float(agent_stats.get("rollback_rate") or 0.0)
        else:
            raw_success = default_success
            evidence_count = 0
            avg_duration_ms = cls._default_duration_ms(step)
            avg_confidence = 0.50
            rollback_risk = cls._default_rollback_risk(step)

        base_success = cls._smooth_success(raw_success, default_success, evidence_count)
        success_probability = base_success * (0.85 + 0.15 * avg_confidence)
        adjustments: list[dict[str, Any]] = []
        policy_adjustments = cls._policy_adjustments(step, active_policies)
        for adjustment in policy_adjustments:
            success_probability += float(adjustment.get("success_delta", 0.0))
            avg_duration_ms += int(adjustment.get("duration_delta_ms", 0))
            rollback_risk += float(adjustment.get("rollback_delta", 0.0))
            adjustments.append(adjustment)

        reflection_adjustments = cls._reflection_adjustments(
            step, reflection_agent_stats, reflection_recommendations
        )
        for adjustment in reflection_adjustments:
            success_probability += float(adjustment.get("success_delta", 0.0))
            rollback_risk += float(adjustment.get("rollback_delta", 0.0))
            adjustments.append(adjustment)

        success_probability = _clamp(success_probability, 0.02, 0.99)
        rollback_risk = _clamp(rollback_risk, 0.0, 0.95)
        avg_duration_ms = max(0, avg_duration_ms or cls._default_duration_ms(step))

        return (
            StepPrediction(
                step_id=step.step_id,
                agent=step.agent,
                action=step.action,
                success_probability=success_probability,
                failure_probability=1.0 - success_probability,
                expected_duration_ms=avg_duration_ms,
                rollback_risk=rollback_risk,
                confidence_score=avg_confidence,
                evidence_count=evidence_count,
                adjustments=adjustments,
            ),
            policy_adjustments,
            reflection_adjustments,
        )

    @staticmethod
    def _smooth_success(observed: float, fallback: float, count: int) -> float:
        prior_weight = 5
        return ((observed * count) + (fallback * prior_weight)) / (count + prior_weight)

    @staticmethod
    def _default_duration_ms(step: PlanStep) -> int:
        if step.action.startswith("BROWSER_"):
            return 1800
        if step.action.startswith("DESKTOP_"):
            return 2200
        if "FILE" in step.action:
            return 900
        if "TEST" in step.action:
            return 5000
        return 1200

    @staticmethod
    def _default_rollback_risk(step: PlanStep) -> float:
        if step.action.startswith("DESKTOP_"):
            return 0.12
        if any(term in step.action for term in ("WRITE", "CREATE", "DELETE", "PATCH")):
            return 0.10
        return 0.03

    @classmethod
    def _policy_adjustments(
        cls, step: PlanStep, active_policies: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        adjustments: list[dict[str, Any]] = []
        for policy in active_policies:
            condition = policy.get("condition") or {}
            effect = policy.get("effect") or {}
            if not cls._policy_matches_step(step, condition):
                continue
            effect_action = str(effect.get("action", "")).lower()
            delta = 0.0
            rollback_delta = 0.0
            duration_delta_ms = 0
            if effect_action == "block":
                delta = -0.70
            elif effect_action == "defer":
                delta = -0.15
                duration_delta_ms = int(effect.get("cooldown_sec") or 0) * 1000
            elif effect_action == "limit_retries":
                delta = -0.05
                rollback_delta = -0.02
            elif effect_action == "cooldown":
                delta = -0.04
                duration_delta_ms = int(effect.get("cooldown_sec") or 1) * 1000
            elif effect_action == "prefer":
                alternative = str(effect.get("alternative_agent") or "")
                if alternative and alternative != step.agent:
                    delta = -0.03
            adjustments.append({
                "source": "strategy_policy",
                "policy_id": policy.get("policy_id", ""),
                "title": policy.get("title", ""),
                "step_id": step.step_id,
                "agent": step.agent,
                "action": step.action,
                "effect": effect_action,
                "success_delta": round(delta, 4),
                "rollback_delta": round(rollback_delta, 4),
                "duration_delta_ms": duration_delta_ms,
            })
        return adjustments

    @staticmethod
    def _policy_matches_step(step: PlanStep, condition: dict[str, Any]) -> bool:
        agent = str(condition.get("agent") or "").strip().lower()
        action_type = str(condition.get("action_type") or condition.get("action") or "").strip().upper()
        if agent and agent != step.agent:
            return False
        if action_type and action_type != step.action:
            return False
        return bool(agent or action_type)

    @classmethod
    def _reflection_adjustments(
        cls,
        step: PlanStep,
        agent_stats: dict[str, dict[str, Any]],
        recommendations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        adjustments: list[dict[str, Any]] = []
        stats = agent_stats.get(step.agent)
        if stats:
            success_rate = float(stats.get("success_rate") or 0.0)
            avg_confidence = float(stats.get("avg_confidence") or 0.0)
            if success_rate and success_rate < 0.70:
                adjustments.append({
                    "source": "reflection_agent_stats",
                    "step_id": step.step_id,
                    "agent": step.agent,
                    "action": step.action,
                    "metric": "low_agent_success_rate",
                    "value": round(success_rate, 4),
                    "success_delta": round((success_rate - 0.70) * 0.35, 4),
                    "rollback_delta": 0.03,
                })
            if avg_confidence and avg_confidence < 0.65:
                adjustments.append({
                    "source": "reflection_agent_stats",
                    "step_id": step.step_id,
                    "agent": step.agent,
                    "action": step.action,
                    "metric": "low_dve_confidence",
                    "value": round(avg_confidence, 4),
                    "success_delta": -0.06,
                    "rollback_delta": 0.02,
                })

        haystack_terms = {step.agent, step.action.lower(), step.action.lower().replace("_", " ")}
        priority_delta = {
            "CRITICAL": -0.25,
            "HIGH": -0.15,
            "MEDIUM": -0.08,
            "LOW": -0.03,
        }
        for rec in recommendations:
            text = " ".join(
                str(rec.get(key, ""))
                for key in ("category", "observation", "recommendation", "target")
            ).lower()
            if not any(term and term in text for term in haystack_terms):
                continue
            priority = str(rec.get("priority") or "LOW").upper()
            adjustments.append({
                "source": "reflection_recommendation",
                "recommendation_id": rec.get("id", ""),
                "priority": priority,
                "step_id": step.step_id,
                "agent": step.agent,
                "action": step.action,
                "success_delta": priority_delta.get(priority, -0.03),
                "rollback_delta": 0.02 if priority in {"CRITICAL", "HIGH"} else 0.0,
            })
        return adjustments

    @staticmethod
    def _load_json_file(path: Path, fallback: Any) -> Any:
        try:
            if not path.exists():
                return fallback
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return fallback

    @classmethod
    def _load_active_policies(cls) -> list[dict[str, Any]]:
        path = runtime_data_root() / "backend" / "data" / "policy_ledger.json"
        raw = cls._load_json_file(path, [])
        if not isinstance(raw, list):
            return []
        active = []
        for policy in raw:
            if not isinstance(policy, dict):
                continue
            status = str(policy.get("status", "")).upper()
            if status in {"ACCEPTED", "ACTIVE"}:
                active.append(policy)
        return active

    @classmethod
    def _load_latest_reflection_report(cls) -> dict[str, Any] | None:
        path = runtime_data_root() / "backend" / "data" / "reflection_reports.json"
        raw = cls._load_json_file(path, [])
        if isinstance(raw, list) and raw:
            latest = raw[-1]
            return latest if isinstance(latest, dict) else None
        if isinstance(raw, dict):
            return raw
        return None

    @staticmethod
    def _reflection_agent_stats(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        if not report:
            return {}
        stats = report.get("agent_stats") or []
        if not isinstance(stats, list):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for item in stats:
            if isinstance(item, dict) and item.get("agent"):
                result[str(item["agent"]).lower()] = item
        return result

    @staticmethod
    def _reflection_recommendations(report: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not report:
            return []
        recommendations = report.get("recommendations") or []
        return [item for item in recommendations if isinstance(item, dict)] if isinstance(recommendations, list) else []

    @staticmethod
    def _risk_level(risk: float) -> str:
        if risk >= 0.50:
            return "high"
        if risk >= 0.20:
            return "medium"
        return "low"

    @staticmethod
    def _failure_reason(prediction: StepPrediction) -> str:
        if prediction.adjustments:
            sources = sorted({str(item.get("source", "adjustment")) for item in prediction.adjustments})
            return "historical risk plus " + ", ".join(sources)
        if prediction.evidence_count:
            return "historical action memory failure rate"
        return "cold-start estimate; no action memory history yet"

    @staticmethod
    def _plan_recommendation(success_probability: float, rollback_risk: float) -> str:
        if success_probability < 0.50:
            return "revise plan before execution: predicted success is too low"
        if success_probability < 0.75:
            return "run with caution: request review or add fallback steps"
        if rollback_risk >= 0.35:
            return "proceed to validation, but prepare rollback chain"
        return "acceptable risk: proceed to validation"

    @staticmethod
    def _source_summary(
        active_policies: list[dict[str, Any]], reflection: dict[str, Any] | None
    ) -> dict[str, Any]:
        return {
            "action_memory": "enabled",
            "strategy_policies_loaded": len(active_policies),
            "reflection_report_loaded": reflection is not None,
            "reflection_report_id": reflection.get("report_id") if isinstance(reflection, dict) else None,
        }
