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
import time
import sqlite3
import threading
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
    confidence_interval: tuple[float, float] = (0.0, 1.0)
    resource_cost: float = 0.0
    risk_score: float = 0.0

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
            "confidence_interval": [round(x, 4) for x in self.confidence_interval],
            "resource_cost": round(self.resource_cost, 4),
            "risk_score": round(self.risk_score, 4),
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
    _lock = threading.RLock()
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

        from backend.core.workflow_memory import WorkflowMemory

        # 1. Fetch recent workflow runs and goal matches to build historical context
        all_runs = []
        try:
            recent_runs = WorkflowMemory.get_recent_workflow_runs(limit=100)
            for r in recent_runs:
                detailed = WorkflowMemory.get_workflow_run(r["workflow_id"])
                if detailed:
                    all_runs.append(detailed)
        except Exception:
            pass

        if goal:
            try:
                goal_runs = WorkflowMemory.search_workflows_by_goal(goal, limit=50)
                for r in goal_runs:
                    if not any(x["workflow_id"] == r["workflow_id"] for x in all_runs):
                        detailed = WorkflowMemory.get_workflow_run(r["workflow_id"])
                        if detailed:
                            all_runs.append(detailed)
            except Exception:
                pass

        plan_steps_seq = [(s.agent, s.action) for s in steps]
        plan_steps_set = set(plan_steps_seq)

        matching_runs = []
        for r in all_runs:
            r_steps = r.get("steps") or []
            r_seq = [(s["agent"], s["action"]) for s in r_steps]
            r_set = set(r_seq)

            intersection = plan_steps_set.intersection(r_set)
            union = plan_steps_set.union(r_set)
            jaccard = len(intersection) / len(union) if union else 0.0

            goal_match = False
            if goal and r.get("goal"):
                goal_match = (
                    goal.strip().lower() in r["goal"].strip().lower()
                    or r["goal"].strip().lower() in goal.strip().lower()
                )

            if jaccard >= 0.4 or goal_match:
                matching_runs.append({
                    "run": r,
                    "jaccard": jaccard,
                    "goal_match": goal_match,
                    "steps": r_steps,
                    "success": r["success"],
                    "duration_ms": r["total_duration_ms"]
                })

        empirical_successes = sum(1 for m in matching_runs if m["success"])
        empirical_total = len(matching_runs)
        empirical_success_rate = empirical_successes / empirical_total if empirical_total else 1.0

        empirical_rollbacks = sum(1 for m in matching_runs if any(s.get("rollback_executed") for s in m["steps"]))
        empirical_rollback_rate = empirical_rollbacks / empirical_total if empirical_total else 0.0

        empirical_durations = [m["duration_ms"] for m in matching_runs if m["duration_ms"] > 0]
        empirical_avg_duration = sum(empirical_durations) / len(empirical_durations) if empirical_durations else 0.0

        # Find critical failure points (transitions/actions that commonly fail in matching runs)
        empirical_step_failures: dict[tuple[str, str], list[bool]] = {}
        for m in matching_runs:
            for s in m["steps"]:
                key = (s["agent"], s["action"])
                empirical_step_failures.setdefault(key, []).append(s["success"])

        critical_failure_points = []
        for (agent, action), successes_list in empirical_step_failures.items():
            total_attempts = len(successes_list)
            failed_attempts = sum(1 for succ in successes_list if not succ)
            if failed_attempts > 0:
                failure_rate = failed_attempts / total_attempts
                critical_failure_points.append({
                    "agent": agent,
                    "action": action,
                    "failure_rate": round(failure_rate, 4),
                    "failed_attempts": failed_attempts,
                    "total_attempts": total_attempts,
                })
        critical_failure_points.sort(key=lambda x: x["failure_rate"], reverse=True)

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

        # Calibrate success, rollback, and duration using workflow-level empirical memory
        if empirical_total > 0:
            weight = min(0.75, empirical_total / 8.0)
            success_probability = (1.0 - weight) * success_probability + weight * empirical_success_rate
            rollback_risk = (1.0 - weight) * rollback_risk + weight * empirical_rollback_rate
            if empirical_avg_duration > 0:
                estimated_duration_ms = int((1.0 - weight) * estimated_duration_ms + weight * empirical_avg_duration)

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

        # Merge empirical critical failure points from workflow memory
        for cfp in critical_failure_points:
            if not any(lf["agent"] == cfp["agent"] and lf["action"] == cfp["action"] for lf in likely_failures):
                likely_failures.append({
                    "step_id": "empirical_workflow_match",
                    "agent": cfp["agent"],
                    "action": cfp["action"],
                    "failure_probability": cfp["failure_rate"],
                    "reason": f"empirical workflow memory failure rate ({cfp['failed_attempts']}/{cfp['total_attempts']} runs)",
                })
        likely_failures.sort(key=lambda x: x["failure_probability"], reverse=True)

        recommendation = cls._plan_recommendation(success_probability, rollback_risk)

        # Incorporate empirical runs count in source summary
        source_summary = cls._source_summary(active_policies, reflection)
        source_summary["empirical_workflow_runs_matched"] = empirical_total

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
            data_sources=source_summary,
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

        # Step 8.2 Simulation Calibration Adjustment
        try:
            from backend.core.simulation_calibration import SimulationCalibrator
            success_factor = SimulationCalibrator.get_calibration_factor(step.agent, step.action)
            duration_factor = SimulationCalibrator.get_duration_calibration_factor(step.agent, step.action)
            rollback_factor = SimulationCalibrator.get_rollback_calibration_factor(step.agent, step.action)
            success_probability *= success_factor
            avg_duration_ms = int(avg_duration_ms * duration_factor)
            rollback_risk *= rollback_factor
        except Exception:
            pass

        # Apply Step 15 Global Decision Calibration modifier if present
        try:
            global_multiplier = cls.get_global_calibration_modifier()
            success_probability *= global_multiplier
        except Exception:
            pass

        success_probability = _clamp(success_probability, 0.02, 0.99)
        rollback_risk = _clamp(rollback_risk, 0.0, 0.95)
        avg_duration_ms = max(0, avg_duration_ms or cls._default_duration_ms(step))

        # Calculate Wilson interval, resource cost, risk score
        successes_count = int(base_success * evidence_count)
        confidence_interval = cls._wilson_interval(successes_count, evidence_count)

        agent_multipliers = {
            "coder": 1.5,
            "browser": 1.0,
            "desktop": 2.0,
            "terminal": 1.8,
            "file": 1.2,
        }
        agent_mult = agent_multipliers.get(step.agent, 1.2)
        resource_cost = (avg_duration_ms / 1000.0) * agent_mult

        failure_prob = 1.0 - success_probability
        risk_score = failure_prob * 0.7 + rollback_risk * 0.3

        return (
            StepPrediction(
                step_id=step.step_id,
                agent=step.agent,
                action=step.action,
                success_probability=success_probability,
                failure_probability=failure_prob,
                expected_duration_ms=avg_duration_ms,
                rollback_risk=rollback_risk,
                confidence_score=avg_confidence,
                evidence_count=evidence_count,
                adjustments=adjustments,
                confidence_interval=confidence_interval,
                resource_cost=resource_cost,
                risk_score=risk_score,
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

    @classmethod
    def simulate_milestone(cls, goal_id: str, milestone_id: str) -> dict[str, Any]:
        """Simulates execution of a specific milestone and persists simulation results in GoalMemory."""
        from backend.core.goal_memory import GoalMemory
        goal = GoalMemory.get_goal(goal_id)
        if not goal:
            raise KeyError(f"Goal '{goal_id}' not found.")

        milestone = next((m for m in goal.get("milestones", []) if m["milestone_id"] == milestone_id), None)
        if not milestone:
            raise KeyError(f"Milestone '{milestone_id}' not found in goal '{goal_id}'.")

        # Map milestone details to standard agents/actions
        title_lower = milestone["title"].lower()
        if "test" in title_lower or "validate" in title_lower or "verify" in title_lower:
            agent = "coder"
            action = "RUN_TESTS"
        elif "code" in title_lower or "implement" in title_lower or "build" in title_lower or "develop" in title_lower:
            agent = "coder"
            action = "WRITE_FILE"
        elif "search" in title_lower or "research" in title_lower or "find" in title_lower:
            agent = "browser"
            action = "SEARCH_WEB"
        else:
            agent = "browser"
            action = "SEARCH_WEB"

        plan_steps = [
            {"step_id": milestone_id, "agent": agent, "action": action}
        ]

        report = cls.simulate_plan(
            plan=plan_steps,
            goal=milestone["title"],
            workflow_id=f"wf_ms_{milestone_id}"
        )

        metrics = {
            "success_probability": round(report.success_probability, 4),
            "rollback_risk": round(report.rollback_risk, 4),
            "expected_duration_sec": round(float(report.estimated_duration_ms) / 1000.0 if report.estimated_duration_ms > 0 else 600.0, 2),
        }

        # Update milestone record in GoalMemory
        GoalMemory.update_milestone(
            milestone_id=milestone_id,
            expected_duration_sec=metrics["expected_duration_sec"],
            success_probability=metrics["success_probability"],
            rollback_risk=metrics["rollback_risk"]
        )

        return metrics

    @classmethod
    def simulate_project(cls, project_id: str) -> dict[str, Any]:
        """Simulates the execution of a project using Monte Carlo trials and critical path tracing."""
        from backend.core.project_manager_v2 import ProjectManagerV2
        from backend.core.project_memory import ProjectMemory
        from backend.core.goal_manager import GoalManager
        from backend.core.goal_memory import GoalMemory

        project = ProjectManagerV2.get_project_hierarchy(project_id)
        if not project:
            raise KeyError(f"Project '{project_id}' not found.")

        goals = project.get("goals_tree", [])
        if not goals:
            return {
                "completion_probability": 1.0,
                "predicted_finish_date": time.strftime('%Y-%m-%d', time.localtime()),
                "likely_blockers": [],
                "critical_path": [],
                "resource_demand": {}
            }

        # Step 1: Ensure all milestones are simulated
        for goal in goals:
            for m in goal.get("milestones", []):
                if m.get("success_probability") is None:
                    try:
                        cls.simulate_milestone(goal["goal_id"], m["milestone_id"])
                    except Exception:
                        pass

        # Reload project hierarchy to pick up simulated metrics
        project = ProjectManagerV2.get_project_hierarchy(project_id)
        goals = project.get("goals_tree", [])

        # Step 2: Monte Carlo simulation (100 trials)
        trials = 100
        successful_trials = 0
        import random
        for _ in range(trials):
            trial_failed = False
            for goal in goals:
                for m in goal.get("milestones", []):
                    prob = m.get("success_probability")
                    prob = float(prob) if prob is not None else 1.0
                    if random.random() > prob:
                        trial_failed = True
                        break
                if trial_failed:
                    break
            if not trial_failed:
                successful_trials += 1

        completion_probability = round(successful_trials / trials, 4)

        # Step 3: Critical Path Analysis (DAG traversal)
        goal_durations = {}
        goal_milestones = {}
        for goal in goals:
            g_id = goal["goal_id"]
            duration = sum(float(m.get("expected_duration_sec") or 600.0) for m in goal.get("milestones", []))
            goal_durations[g_id] = duration
            goal_milestones[g_id] = [m["title"] for m in goal.get("milestones", [])]

        earliest_start = {}
        earliest_finish = {}

        resolved_order = []
        visited = set()

        def resolve(g_id):
            if g_id in visited:
                return
            visited.add(g_id)
            goal_item = next((g for g in goals if g["goal_id"] == g_id), None)
            if goal_item:
                for dep in goal_item.get("dependencies", []):
                    resolve(dep)
            resolved_order.append(g_id)

        for goal in goals:
            resolve(goal["goal_id"])

        for g_id in resolved_order:
            goal_item = next((g for g in goals if g["goal_id"] == g_id), None)
            deps = goal_item.get("dependencies", []) if goal_item else []
            start_time = max([earliest_finish.get(dep, 0.0) for dep in deps]) if deps else 0.0
            earliest_start[g_id] = start_time
            earliest_finish[g_id] = start_time + goal_durations.get(g_id, 0.0)

        critical_path_duration = max(earliest_finish.values()) if earliest_finish else 0.0
        predicted_finish_time = time.time() + critical_path_duration
        predicted_finish_date = time.strftime('%Y-%m-%d', time.localtime(predicted_finish_time))

        critical_path = []
        if earliest_finish:
            current_g = max(earliest_finish, key=earliest_finish.get)
            while current_g:
                critical_path.extend(goal_milestones.get(current_g, []))
                goal_item = next((g for g in goals if g["goal_id"] == current_g), None)
                deps = goal_item.get("dependencies", []) if goal_item else []
                if deps:
                    current_g = max(deps, key=lambda d: earliest_finish.get(d, 0.0))
                else:
                    current_g = None
            critical_path.reverse()

        likely_blockers = []
        for goal in goals:
            for m in goal.get("milestones", []):
                prob = m.get("success_probability")
                risk = m.get("rollback_risk")
                if (prob is not None and prob < 0.7) or (risk is not None and risk > 0.3):
                    likely_blockers.append({
                        "milestone_id": m["milestone_id"],
                        "title": m["title"],
                        "success_probability": prob,
                        "rollback_risk": risk
                    })

        resource_demand = {}
        for goal in goals:
            for m in goal.get("milestones", []):
                title_lower = m["title"].lower()
                if "test" in title_lower or "validate" in title_lower or "verify" in title_lower:
                    agent = "coder"
                elif "code" in title_lower or "implement" in title_lower or "build" in title_lower or "develop" in title_lower or "write" in title_lower or "create" in title_lower:
                    agent = "coder"
                elif "search" in title_lower or "research" in title_lower or "find" in title_lower:
                    agent = "browser"
                else:
                    agent = "browser"
                
                dur = float(m.get("expected_duration_sec") or 600.0)
                resource_demand[agent] = resource_demand.get(agent, 0.0) + dur

        resource_demand = {k: round(v, 2) for k, v in resource_demand.items()}

        all_milestones = [m for goal in goals for m in goal.get("milestones", [])]
        avg_rollback = sum(float(m.get("rollback_risk") or 0.0) for m in all_milestones) / len(all_milestones) if all_milestones else 0.0

        with ProjectMemory._lock:
            conn = ProjectMemory._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    UPDATE projects
                    SET success_rate = ?, risk_score = ?, predicted_finish = ?
                    WHERE project_id = ?
                    """,
                    (completion_probability, avg_rollback, predicted_finish_time, project_id)
                )
                ProjectMemory._log_event_conn(conn, project_id, "PROJECT_SIMULATED", {
                    "completion_probability": completion_probability,
                    "predicted_finish": predicted_finish_date
                })
                conn.commit()
            except Exception:
                conn.rollback()
            finally:
                conn.close()

        return {
            "completion_probability": completion_probability,
            "predicted_finish_date": predicted_finish_date,
            "likely_blockers": likely_blockers,
            "critical_path": critical_path,
            "resource_demand": resource_demand
        }

    # -- Step 15 Database, Counterfactual, and Calibration APIs ------------
    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        from backend.core.config import load_config
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        with cls._lock:
            # Check dynamically if tables exist to support clean_db/unlink operations in tests
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='simulation_runs'")
            if not cursor.fetchone():
                cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS simulation_runs (
                    run_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    workflow_id TEXT,
                    timestamp REAL NOT NULL,
                    base_success REAL NOT NULL,
                    base_risk REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS counterfactual_scenarios (
                    scenario_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    predicted_success REAL NOT NULL,
                    predicted_risk REAL NOT NULL,
                    predicted_duration_ms INTEGER NOT NULL,
                    recommendation TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES simulation_runs(run_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS decision_forecasts (
                    decision_id TEXT PRIMARY KEY,
                    decision TEXT NOT NULL,
                    predicted_success REAL NOT NULL,
                    predicted_cost REAL NOT NULL,
                    predicted_time TEXT NOT NULL,
                    actual_success REAL,
                    actual_cost REAL,
                    actual_time TEXT,
                    timestamp REAL NOT NULL,
                    status TEXT DEFAULT 'pending'
                );

                CREATE TABLE IF NOT EXISTS forecast_calibration (
                    calibration_id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    total_decisions INTEGER NOT NULL,
                    mean_absolute_error REAL NOT NULL,
                    root_mean_squared_error REAL NOT NULL,
                    details TEXT NOT NULL
                );
                """
            )
            conn.commit()

    @classmethod
    def run_counterfactual_simulations(
        cls,
        plan: list[dict[str, Any]],
        *,
        goal: str = "",
        workflow_id: str = ""
    ) -> dict[str, Any]:
        """Runs standard simulation AND alternate counterfactual branches, logging them to the ledger."""
        import uuid
        run_id = f"sim_{uuid.uuid4().hex[:12]}"
        now = time.time()
        
        # 1. Run Reality Simulation
        reality_report = cls.simulate_plan(plan, goal=goal, workflow_id=workflow_id)
        reality_success = reality_report.success_probability
        reality_risk = reality_report.rollback_risk
        reality_duration = reality_report.estimated_duration_ms
        reality_recommendation = reality_report.recommendation
        
        # 2. Run No Action Simulation
        no_action_success = 0.0
        no_action_risk = 0.0
        no_action_duration = 0
        no_action_rec = "No action taken: goal not achieved, resources preserved."
        
        # 3. Run Delay 7 Days Simulation
        delay_duration = reality_duration + (7 * 24 * 3600 * 1000)
        delay_success = _clamp(reality_success * 0.95, 0.02, 0.99)
        delay_risk = reality_risk
        delay_rec = cls._plan_recommendation(delay_success, delay_risk)
        if "acceptable" in delay_rec:
            delay_rec = "acceptable risk with delay, but watch for dependency drift"
        
        # 4. Run Budget Decreased 50% Simulation
        budget_success = _clamp(reality_success * 0.80, 0.02, 0.99)
        budget_risk = _clamp(reality_risk * 2.0, 0.0, 0.95)
        budget_duration = reality_duration
        budget_rec = cls._plan_recommendation(budget_success, budget_risk)
        if "acceptable" in budget_rec:
            budget_rec = "increased execution risk due to reduced testing budget"
            
        conn = cls._get_sqlite_conn()
        try:
            conn.execute(
                """
                INSERT INTO simulation_runs (run_id, goal, workflow_id, timestamp, base_success, base_risk)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, goal or "Simulation Goal", workflow_id or f"wf_{int(now)}", now, reality_success, reality_risk)
            )
            
            scenarios = [
                ("Reality", {}, reality_success, reality_risk, reality_duration, reality_recommendation),
                ("No Action", {"skip_execution": True}, no_action_success, no_action_risk, no_action_duration, no_action_rec),
                ("Delay 7 Days", {"delay_days": 7}, delay_success, delay_risk, delay_duration, delay_rec),
                ("Budget Decrease 50%", {"budget_factor": 0.5}, budget_success, budget_risk, budget_duration, budget_rec),
            ]
            
            for name, params, succ, risk, dur, rec in scenarios:
                scenario_id = f"scen_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO counterfactual_scenarios (
                        scenario_id, run_id, name, parameters, predicted_success, predicted_risk, predicted_duration_ms, recommendation
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (scenario_id, run_id, name, json.dumps(params), succ, risk, dur, rec)
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
            
        return {
            "run_id": run_id,
            "goal": goal,
            "workflow_id": workflow_id,
            "timestamp": now,
            "scenarios": {
                "Reality": {
                    "predicted_success": reality_success,
                    "predicted_risk": reality_risk,
                    "predicted_duration_ms": reality_duration,
                    "recommendation": reality_recommendation,
                },
                "No Action": {
                    "predicted_success": no_action_success,
                    "predicted_risk": no_action_risk,
                    "predicted_duration_ms": no_action_duration,
                    "recommendation": no_action_rec,
                },
                "Delay 7 Days": {
                    "predicted_success": delay_success,
                    "predicted_risk": delay_risk,
                    "predicted_duration_ms": delay_duration,
                    "recommendation": delay_rec,
                },
                "Budget Decrease 50%": {
                    "predicted_success": budget_success,
                    "predicted_risk": budget_risk,
                    "predicted_duration_ms": budget_duration,
                    "recommendation": budget_rec,
                }
            }
        }

    @staticmethod
    def _wilson_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
        if total == 0:
            return (0.0, 1.0)
        z = 1.96 if confidence == 0.95 else 1.645
        p = successes / total
        denominator = 1 + z**2 / total
        centre_adj_p = p + z**2 / (2 * total)
        adj_sem = z * ((p * (1 - p) + z**2 / (4 * total)) / total) ** 0.5
        low = (centre_adj_p - adj_sem) / denominator
        high = (centre_adj_p + adj_sem) / denominator
        return (max(0.0, low), min(1.0, high))

    @classmethod
    def get_global_calibration_modifier(cls) -> float:
        """Fetch the latest global calibration modifier from forecast_calibration."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT details FROM forecast_calibration ORDER BY timestamp DESC LIMIT 1").fetchone()
                if row:
                    details = json.loads(row["details"])
                    avg_pred = details.get("avg_predicted_success", 1.0)
                    avg_act = details.get("avg_actual_success", 1.0)
                    if avg_pred > 0:
                        ratio = avg_act / avg_pred
                        return max(0.5, min(1.5, ratio))
            except Exception:
                pass
            finally:
                conn.close()
        return 1.0

    @classmethod
    def record_decision_forecast(
        cls,
        decision_id: str,
        decision: str,
        predicted_success: float,
        predicted_cost: float,
        predicted_time: str
    ) -> None:
        """Records a future decision forecast before executive governance approval."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO decision_forecasts (decision_id, decision, predicted_success, predicted_cost, predicted_time, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(decision_id) DO UPDATE SET
                        decision=excluded.decision,
                        predicted_success=excluded.predicted_success,
                        predicted_cost=excluded.predicted_cost,
                        predicted_time=excluded.predicted_time,
                        timestamp=excluded.timestamp
                    """,
                    (decision_id, decision.strip(), max(0.0, min(1.0, predicted_success)), max(0.0, predicted_cost), predicted_time.strip(), time.time())
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def record_decision_outcome(
        cls,
        decision_id: str,
        actual_success: float,
        actual_cost: float,
        actual_time: str
    ) -> None:
        """Records the actual outcome of a decision and marks it as resolved."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    UPDATE decision_forecasts
                    SET actual_success = ?, actual_cost = ?, actual_time = ?, status = 'resolved'
                    WHERE decision_id = ?
                    """,
                    (max(0.0, min(1.0, actual_success)), max(0.0, actual_cost), actual_time.strip(), decision_id)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def recalibrate_from_ledger(cls) -> dict[str, Any]:
        """Calculates prediction errors against reality and records a calibration run."""
        import uuid
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                rows = conn.execute("SELECT * FROM decision_forecasts WHERE status = 'resolved'").fetchall()
                if not rows:
                    return {"status": "no_resolved_decisions", "count": 0}
                
                errors = []
                sq_errors = []
                pred_success_list = []
                act_success_list = []
                
                for r in rows:
                    pred = r["predicted_success"]
                    act = r["actual_success"]
                    pred_success_list.append(pred)
                    act_success_list.append(act)
                    
                    errors.append(abs(pred - act))
                    sq_errors.append((pred - act) ** 2)
                
                mae = sum(errors) / len(errors)
                rmse = (sum(sq_errors) / len(sq_errors)) ** 0.5
                
                avg_pred = sum(pred_success_list) / len(pred_success_list)
                avg_act = sum(act_success_list) / len(act_success_list)
                
                details = {
                    "avg_predicted_success": avg_pred,
                    "avg_actual_success": avg_act,
                    "records": [
                        {
                            "decision_id": r["decision_id"],
                            "decision": r["decision"],
                            "predicted_success": r["predicted_success"],
                            "actual_success": r["actual_success"],
                            "error": abs(r["predicted_success"] - r["actual_success"])
                        }
                        for r in rows
                    ]
                }
                
                calibration_id = f"cal_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO forecast_calibration (calibration_id, timestamp, total_decisions, mean_absolute_error, root_mean_squared_error, details)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (calibration_id, time.time(), len(rows), mae, rmse, json.dumps(details))
                )
                
                # Mark as calibrated
                conn.execute("UPDATE decision_forecasts SET status = 'calibrated' WHERE status = 'resolved'")
                conn.commit()
                
                return {
                    "status": "success",
                    "calibration_id": calibration_id,
                    "total_decisions": len(rows),
                    "mean_absolute_error": round(mae, 4),
                    "root_mean_squared_error": round(rmse, 4),
                }
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
