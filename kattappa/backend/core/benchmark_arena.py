"""Benchmark Arena (Layer 10/11 - Trustworthy Edition).

Supervises capabilities and performance metrics in a read-only sandboxed
environment. Enforces objective scoring, Brier calibration, regression
floors, an incoherence-based System Coherence Score, and a Benchmark Integrity Score.
"""

from __future__ import annotations

import ast
import contextlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from statistics import mean, median
from typing import Any, Sequence

from backend.core.config import runtime_data_root


class BenchmarkCategory(str, Enum):
    MEMORY = "memory"
    CODING = "coding"
    SECURITY = "security"
    PLANNING = "planning"
    TOOLS = "tools"
    SPEED = "speed"
    CALIBRATION = "calibration"
    CONVERSATION = "conversation"


def _history_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "benchmark_history.json"


def _tool_history_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "tool_benchmark_history.json"


class ToolBenchmarkDecision(str, Enum):
    PROMOTE = "PROMOTE"
    KEEP = "KEEP"
    DEPRECATE = "DEPRECATE"
    ROLLBACK = "ROLLBACK"

    # Compatibility aliases
    ACCEPT_VERSION = "PROMOTE"
    REJECT_VERSION = "DEPRECATE"
    NEEDS_MORE_RUNS = "KEEP"
    REGRESSION_DETECTED = "DEPRECATE"
    INSUFFICIENT_DATA = "KEEP"


@dataclass(frozen=True)
class ToolBenchmarkRun:
    """One deterministic benchmark observation for a tool version."""

    tool_name: str
    tool_version: str
    benchmark_suite: str
    run_id: str
    task_id: str
    success: bool
    duration_ms: int
    failure_type: str | None = None
    rollback_required: bool = False
    rollback_success: bool | None = None
    simulation_decision: str = ""
    human_decision: str = ""
    simulation_prediction: dict[str, Any] = field(default_factory=dict)
    execution_result: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    source: str = "benchmark_arena"
    resource_cost: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolBenchmarkRun":
        execution_result = data.get("execution_result") or {}
        simulation_prediction = data.get("simulation_prediction") or {}
        if not isinstance(execution_result, dict):
            execution_result = {"raw": execution_result}
        if not isinstance(simulation_prediction, dict):
            simulation_prediction = {"raw": simulation_prediction}

        success = data.get("success")
        if success is None:
            success = execution_result.get("success")
        if success is None:
            success = data.get("actual_success", False)

        duration_ms = data.get("duration_ms")
        if duration_ms is None:
            duration_ms = data.get("actual_duration")
        if duration_ms is None:
            duration_ms = data.get("actual_duration_ms")
        if duration_ms is None:
            duration_ms = execution_result.get("duration_ms", 0)

        rollback_required = data.get("rollback_required")
        if rollback_required is None:
            rollback_required = data.get("actual_rollback")
        if rollback_required is None:
            rollback_required = data.get("rollback_executed", False)

        rollback_success = data.get("rollback_success")
        if rollback_success is None:
            rollback_success = data.get("rollback_succeeded")
        if rollback_success is None:
            rollback_success = execution_result.get("rollback_success")

        resource_cost = data.get("resource_cost")
        if resource_cost is None:
            resource_cost = execution_result.get("resource_cost")
        if resource_cost is None:
            resource_cost = execution_result.get("cost", 0.0)

        return cls(
            tool_name=str(data.get("tool_name") or data.get("tool") or "").strip(),
            tool_version=str(data.get("tool_version") or data.get("version") or "").strip(),
            benchmark_suite=str(data.get("benchmark_suite") or data.get("suite_id") or "").strip(),
            run_id=str(data.get("run_id") or data.get("action_id") or f"tool_run_{int(time.time() * 1000)}"),
            task_id=str(data.get("task_id") or data.get("action") or data.get("task") or ""),
            success=bool(success),
            duration_ms=max(0, int(float(duration_ms or 0))),
            failure_type=cls._clean_failure_type(data.get("failure_type") or data.get("failure_classification")),
            rollback_required=bool(rollback_required),
            rollback_success=None if rollback_success is None else bool(rollback_success),
            simulation_decision=BenchmarkArena._normalise_decision(data.get("simulation_decision", "")),
            human_decision=BenchmarkArena._normalise_decision(data.get("human_decision", "")),
            simulation_prediction=simulation_prediction,
            execution_result=execution_result,
            timestamp=str(data.get("timestamp") or ""),
            source=str(data.get("source") or "benchmark_arena"),
            resource_cost=max(0.0, float(resource_cost or 0.0)),
        )

    @staticmethod
    def _clean_failure_type(value: Any) -> str | None:
        if value is None:
            return None
        clean = str(value).strip().lower()
        return clean or None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolBenchmarkMetrics:
    """Aggregated evidence used to accept or reject a tool version."""

    tool_name: str
    tool_version: str
    benchmark_suite: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    failure_rate: float
    mean_duration_ms: float
    median_duration_ms: float
    p95_duration_ms: float
    fastest_duration_ms: int
    slowest_duration_ms: int
    failure_classification: dict[str, int]
    rollback_required_count: int
    rollback_successes: int
    rollback_failures: int
    recovery_rate: float
    approval_accuracy: float
    rejection_accuracy: float
    false_positive_rate: float
    false_negative_rate: float
    approval_total: int
    prediction_error: dict[str, Any]
    total_resource_cost: float
    mean_resource_cost: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BenchmarkArena:
    # Category floors requirement
    DEFAULT_FLOORS = {
        "security": 0.95,
        "planning": 0.85,
        "calibration": 0.80,
        "memory": 0.80,
        "coding": 0.80,
        "tools": 0.80,
    }

    FAILURE_TYPES = {
        "tool_failure",
        "environment_failure",
        "validation_failure",
        "human_rejection",
    }

    # -- Tool Benchmark Arena V1 -------------------------------------------
    @classmethod
    def calculate_tool_metrics(
        cls,
        runs: Sequence[ToolBenchmarkRun | dict[str, Any]],
    ) -> ToolBenchmarkMetrics:
        """Calculate success, speed, recovery, approval, and prediction metrics."""
        normalised = cls._normalise_tool_runs(runs)
        tool_name = normalised[0].tool_name if normalised else ""
        tool_version = normalised[0].tool_version if normalised else ""
        benchmark_suite = normalised[0].benchmark_suite if normalised else ""
        total = len(normalised)
        successes = sum(1 for run in normalised if run.success)
        failures = total - successes
        durations = [run.duration_ms for run in normalised]
        failure_counts = {failure_type: 0 for failure_type in sorted(cls.FAILURE_TYPES)}
        for run in normalised:
            failure_type = cls.classify_failure(run)
            if failure_type:
                failure_counts[failure_type] = failure_counts.get(failure_type, 0) + 1

        rollback_runs = [run for run in normalised if run.rollback_required]
        rollback_successes = sum(1 for run in rollback_runs if run.rollback_success is True)
        rollback_failures = sum(1 for run in rollback_runs if run.rollback_success is False)

        costs = [run.resource_cost for run in normalised]
        total_cost = sum(costs)
        mean_cost = total_cost / total if total else 0.0

        approval = cls.calculate_approval_accuracy(normalised)
        prediction_error = cls.calculate_prediction_error(normalised)

        return ToolBenchmarkMetrics(
            tool_name=tool_name,
            tool_version=tool_version,
            benchmark_suite=benchmark_suite,
            total_runs=total,
            successful_runs=successes,
            failed_runs=failures,
            success_rate=round(successes / total, 4) if total else 0.0,
            failure_rate=round(failures / total, 4) if total else 0.0,
            mean_duration_ms=round(mean(durations), 2) if durations else 0.0,
            median_duration_ms=round(median(durations), 2) if durations else 0.0,
            p95_duration_ms=cls._percentile(durations, 0.95),
            fastest_duration_ms=min(durations) if durations else 0,
            slowest_duration_ms=max(durations) if durations else 0,
            failure_classification=failure_counts,
            rollback_required_count=len(rollback_runs),
            rollback_successes=rollback_successes,
            rollback_failures=rollback_failures,
            recovery_rate=round(
                rollback_successes / (rollback_successes + rollback_failures), 4
            ) if rollback_successes + rollback_failures else 0.0,
            approval_accuracy=approval["approval_accuracy"],
            rejection_accuracy=approval["rejection_accuracy"],
            false_positive_rate=approval["false_positive_rate"],
            false_negative_rate=approval["false_negative_rate"],
            approval_total=approval["approval_total"],
            prediction_error=prediction_error,
            total_resource_cost=round(total_cost, 4),
            mean_resource_cost=round(mean_cost, 4),
        )

    @classmethod
    def compare_tool_versions(
        cls,
        baseline_runs: Sequence[ToolBenchmarkRun | dict[str, Any]],
        candidate_runs: Sequence[ToolBenchmarkRun | dict[str, Any]],
        *,
        tool_name: str = "",
        baseline_version: str = "",
        candidate_version: str = "",
        benchmark_suite: str = "",
        min_runs: int = 1,
    ) -> dict[str, Any]:
        """Compare a candidate tool version against a baseline using regression gates."""
        baseline_metrics = cls.calculate_tool_metrics(baseline_runs)
        candidate_metrics = cls.calculate_tool_metrics(candidate_runs)

        tool = tool_name or candidate_metrics.tool_name or baseline_metrics.tool_name
        baseline = baseline_version or baseline_metrics.tool_version
        candidate = candidate_version or candidate_metrics.tool_version
        suite = benchmark_suite or candidate_metrics.benchmark_suite or baseline_metrics.benchmark_suite

        if baseline_metrics.total_runs < min_runs or candidate_metrics.total_runs < min_runs:
            return {
                "tool": tool,
                "candidate": candidate,
                "baseline": baseline,
                "benchmark_suite": suite,
                "decision": ToolBenchmarkDecision.KEEP.value,
                "regression_detected": False,
                "reasons": ["insufficient benchmark data for baseline or candidate"],
                "baseline_metrics": baseline_metrics.to_dict(),
                "candidate_metrics": candidate_metrics.to_dict(),
            }

        reasons: list[str] = []
        gates = [
            (
                "success_rate",
                candidate_metrics.success_rate >= baseline_metrics.success_rate,
                candidate_metrics.success_rate,
                baseline_metrics.success_rate,
                "higher_or_equal",
            ),
            (
                "failure_rate",
                candidate_metrics.failure_rate <= baseline_metrics.failure_rate,
                candidate_metrics.failure_rate,
                baseline_metrics.failure_rate,
                "lower_or_equal",
            ),
            (
                "recovery_rate",
                candidate_metrics.recovery_rate >= baseline_metrics.recovery_rate,
                candidate_metrics.recovery_rate,
                baseline_metrics.recovery_rate,
                "higher_or_equal",
            ),
            (
                "approval_accuracy",
                candidate_metrics.approval_accuracy >= baseline_metrics.approval_accuracy,
                candidate_metrics.approval_accuracy,
                baseline_metrics.approval_accuracy,
                "higher_or_equal",
            ),
            (
                "resource_cost",
                candidate_metrics.mean_resource_cost <= (baseline_metrics.mean_resource_cost * 1.25 + 0.01),
                candidate_metrics.mean_resource_cost,
                baseline_metrics.mean_resource_cost,
                "lower_or_equal_to_1.25x",
            ),
        ]
        for metric, passed, candidate_value, baseline_value, expected in gates:
            if not passed:
                reasons.append(
                    f"{metric} regression: candidate {candidate_value:.4f}, "
                    f"baseline {baseline_value:.4f}, expected {expected}"
                )

        regression_detected = bool(reasons)
        success_rate_regression = candidate_metrics.success_rate < baseline_metrics.success_rate

        # Enforce exact decision outputs: PROMOTE, KEEP, DEPRECATE, ROLLBACK
        if success_rate_regression:
            # automatic rejection / rollback
            if candidate_metrics.rollback_required_count > 0 or candidate == baseline or candidate_metrics.failure_rate >= 0.3:
                decision = ToolBenchmarkDecision.ROLLBACK.value
            else:
                decision = ToolBenchmarkDecision.DEPRECATE.value
        elif regression_detected:
            # other regressions (speed, cost, etc.) -> keep baseline, don't promote candidate
            decision = ToolBenchmarkDecision.KEEP.value
        else:
            decision = ToolBenchmarkDecision.PROMOTE.value

        return {
            "tool": tool,
            "candidate": candidate,
            "baseline": baseline,
            "benchmark_suite": suite,
            "success_rate_delta": cls._format_delta(
                cls._rate_delta(candidate_metrics.success_rate, baseline_metrics.success_rate)
            ),
            "speed_delta": cls._format_delta(
                cls._rate_delta(
                    candidate_metrics.mean_duration_ms,
                    baseline_metrics.mean_duration_ms,
                )
            ),
            "failure_rate_delta": cls._format_delta(
                cls._rate_delta(candidate_metrics.failure_rate, baseline_metrics.failure_rate)
            ),
            "recovery_rate_delta": cls._format_delta(
                cls._rate_delta(candidate_metrics.recovery_rate, baseline_metrics.recovery_rate)
            ),
            "approval_accuracy_delta": cls._format_delta(
                cls._rate_delta(candidate_metrics.approval_accuracy, baseline_metrics.approval_accuracy)
            ),
            "resource_cost_delta": cls._format_delta(
                cls._rate_delta(candidate_metrics.mean_resource_cost, baseline_metrics.mean_resource_cost)
            ),
            "decision": decision,
            "regression_detected": regression_detected,
            "reasons": reasons,
            "baseline_metrics": baseline_metrics.to_dict(),
            "candidate_metrics": candidate_metrics.to_dict(),
        }

    @classmethod
    def evaluate_tool_version(
        cls,
        *,
        tool_name: str,
        baseline_version: str,
        candidate_version: str,
        benchmark_suite: str,
        historical_runs: Sequence[ToolBenchmarkRun | dict[str, Any]],
        candidate_runs: Sequence[ToolBenchmarkRun | dict[str, Any]] | None = None,
        min_runs: int = 1,
        persist: bool = False,
    ) -> dict[str, Any]:
        """Filter historical runs, compare versions, and optionally persist the report."""
        all_runs = cls._normalise_tool_runs(historical_runs)
        baseline = [
            run for run in all_runs
            if run.tool_name == tool_name
            and run.tool_version == baseline_version
            and run.benchmark_suite == benchmark_suite
        ]
        candidate = (
            cls._normalise_tool_runs(candidate_runs)
            if candidate_runs is not None
            else [
                run for run in all_runs
                if run.tool_name == tool_name
                and run.tool_version == candidate_version
                and run.benchmark_suite == benchmark_suite
            ]
        )
        report = cls.compare_tool_versions(
            baseline,
            candidate,
            tool_name=tool_name,
            baseline_version=baseline_version,
            candidate_version=candidate_version,
            benchmark_suite=benchmark_suite,
            min_runs=min_runs,
        )
        if persist:
            cls.save_tool_report(report)
        return report

    @classmethod
    def rank_tool_versions(
        cls,
        runs: Sequence[ToolBenchmarkRun | dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Rank tool versions by reliability first, speed second."""
        grouped: dict[tuple[str, str, str], list[ToolBenchmarkRun]] = {}
        for run in cls._normalise_tool_runs(runs):
            grouped.setdefault(
                (run.tool_name, run.tool_version, run.benchmark_suite),
                [],
            ).append(run)

        rankings: list[dict[str, Any]] = []
        for (tool_name, version, suite), version_runs in grouped.items():
            metrics = cls.calculate_tool_metrics(version_runs)
            reliability_score = (
                metrics.success_rate * 0.45
                + (1.0 - metrics.failure_rate) * 0.20
                + metrics.recovery_rate * 0.15
                + metrics.approval_accuracy * 0.20
            )
            rankings.append({
                "tool": tool_name,
                "version": version,
                "benchmark_suite": suite,
                "score": round(reliability_score, 4),
                "metrics": metrics.to_dict(),
            })

        return sorted(
            rankings,
            key=lambda item: (
                item["score"],
                item["metrics"]["success_rate"],
                -item["metrics"]["failure_rate"],
                -item["metrics"]["mean_duration_ms"],
                item["metrics"]["total_runs"],
            ),
            reverse=True,
        )

    @classmethod
    def save_tool_report(cls, report: dict[str, Any]) -> None:
        """Append a tool benchmark comparison report to its own immutable history."""
        path = _tool_history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        history = cls.load_tool_history()
        history.append(report)
        path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    @classmethod
    def load_tool_history(cls) -> list[dict[str, Any]]:
        """Load historical tool benchmark comparison reports."""
        path = _tool_history_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    @classmethod
    def load_runs_from_action_memory(
        cls,
        *,
        tool_name: str,
        tool_version: str,
        benchmark_suite: str,
        agent: str | None = None,
        action_type: str | None = None,
        limit: int = 500,
    ) -> list[ToolBenchmarkRun]:
        """Convert Action Memory records into benchmark observations."""
        from backend.core.action_memory import ActionMemory

        records = ActionMemory.get_recent_actions(limit=limit)
        runs: list[ToolBenchmarkRun] = []
        for record in records:
            if agent and record.agent != agent:
                continue
            if action_type and record.action != action_type:
                continue
            runs.append(
                ToolBenchmarkRun(
                    tool_name=tool_name,
                    tool_version=tool_version,
                    benchmark_suite=benchmark_suite,
                    run_id=record.action_id,
                    task_id=record.action,
                    success=record.success,
                    duration_ms=record.duration_ms,
                    failure_type="tool_failure" if record.failure else None,
                    rollback_required=record.rollback_executed,
                    rollback_success=record.success if record.rollback_executed else None,
                    execution_result=record.to_dict(),
                    timestamp=record.timestamp,
                    source="action_memory",
                )
            )
        return runs

    @classmethod
    def build_run_from_dve(
        cls,
        *,
        tool_name: str,
        tool_version: str,
        benchmark_suite: str,
        run_id: str,
        task_id: str,
        execution_result: dict[str, Any],
        dve_result: dict[str, Any],
        simulation_prediction: dict[str, Any] | None = None,
        human_decision: str = "",
        duration_ms: int | None = None,
    ) -> ToolBenchmarkRun:
        """Build one benchmark observation from DVE, rollback, and simulation data."""
        outcome = str(dve_result.get("outcome") or "").upper()
        success = outcome == "SUCCESS" or bool(dve_result.get("success"))
        rollback_required = bool(
            dve_result.get("rollback_required")
            or dve_result.get("recovery_action")
            or dve_result.get("recovery_actions")
        )
        rollback_success = dve_result.get("rollback_success")
        if rollback_success is None:
            rollback_success = dve_result.get("recovery_success")
        duration = duration_ms
        if duration is None:
            duration = int(execution_result.get("duration_ms") or 0)
        return ToolBenchmarkRun(
            tool_name=tool_name,
            tool_version=tool_version,
            benchmark_suite=benchmark_suite,
            run_id=run_id,
            task_id=task_id,
            success=success,
            duration_ms=max(0, int(duration or 0)),
            failure_type="validation_failure" if not success else None,
            rollback_required=rollback_required,
            rollback_success=None if rollback_success is None else bool(rollback_success),
            simulation_decision=cls._decision_from_prediction(simulation_prediction or {}),
            human_decision=cls._normalise_decision(human_decision),
            simulation_prediction=simulation_prediction or {},
            execution_result={**execution_result, "dve_result": dve_result},
            source="dve",
        )

    @classmethod
    def classify_failure(cls, run: ToolBenchmarkRun | dict[str, Any]) -> str | None:
        """Classify failed runs into the arena's four stable failure buckets."""
        normalised = run if isinstance(run, ToolBenchmarkRun) else ToolBenchmarkRun.from_dict(run)
        if normalised.success:
            return None
        explicit = (normalised.failure_type or "").strip().lower()
        aliases = {
            "tool": "tool_failure",
            "tool_failure": "tool_failure",
            "environment": "environment_failure",
            "env": "environment_failure",
            "environment_failure": "environment_failure",
            "validation": "validation_failure",
            "validator": "validation_failure",
            "validation_failure": "validation_failure",
            "dve": "validation_failure",
            "human": "human_rejection",
            "human_rejection": "human_rejection",
            "human_rejected": "human_rejection",
            "user_rejection": "human_rejection",
        }
        if explicit in aliases:
            return aliases[explicit]

        text = json.dumps(normalised.execution_result, default=str).lower()
        if normalised.human_decision == "REJECT":
            return "human_rejection"
        if any(term in text for term in ("validation", "validator", "dve", "post-check")):
            return "validation_failure"
        if any(term in text for term in ("timeout", "network", "permission", "missing", "not found", "dependency")):
            return "environment_failure"
        return "tool_failure"

    @classmethod
    def calculate_approval_accuracy(
        cls,
        runs: Sequence[ToolBenchmarkRun | dict[str, Any]],
    ) -> dict[str, Any]:
        """Compare simulation approval/rejection decisions with human decisions."""
        pairs = []
        for run in cls._normalise_tool_runs(runs):
            simulation = cls._normalise_decision(run.simulation_decision)
            human = cls._normalise_decision(run.human_decision)
            if simulation in {"APPROVE", "REJECT"} and human in {"APPROVE", "REJECT"}:
                pairs.append((simulation, human))
        total = len(pairs)
        matches = sum(1 for simulation, human in pairs if simulation == human)
        human_approvals = sum(1 for _, human in pairs if human == "APPROVE")
        human_rejections = sum(1 for _, human in pairs if human == "REJECT")
        false_positives = sum(1 for simulation, human in pairs if simulation == "APPROVE" and human == "REJECT")
        false_negatives = sum(1 for simulation, human in pairs if simulation == "REJECT" and human == "APPROVE")
        correct_rejections = sum(1 for simulation, human in pairs if simulation == human == "REJECT")
        return {
            "approval_accuracy": round(matches / total, 4) if total else 0.0,
            "rejection_accuracy": round(correct_rejections / human_rejections, 4) if human_rejections else 0.0,
            "false_positive_rate": round(false_positives / human_rejections, 4) if human_rejections else 0.0,
            "false_negative_rate": round(false_negatives / human_approvals, 4) if human_approvals else 0.0,
            "approval_total": total,
        }

    @classmethod
    def calculate_prediction_error(
        cls,
        runs: Sequence[ToolBenchmarkRun | dict[str, Any]],
    ) -> dict[str, Any]:
        """Compare simulation predictions with execution reality."""
        success_errors: list[float] = []
        duration_errors: list[float] = []
        duration_error_percents: list[float] = []
        rollback_errors: list[float] = []
        likely_failure_matches = 0
        likely_failure_total = 0

        for run in cls._normalise_tool_runs(runs):
            prediction = run.simulation_prediction or {}
            predicted_success = cls._extract_probability(
                prediction,
                "predicted_success",
                "success_probability",
                "success_rate",
            )
            if predicted_success is not None:
                success_errors.append(abs(predicted_success - (1.0 if run.success else 0.0)))

            predicted_duration = cls._extract_number(
                prediction,
                "predicted_duration",
                "predicted_duration_ms",
                "expected_duration_ms",
            )
            if predicted_duration is not None:
                duration_errors.append(abs(run.duration_ms - predicted_duration))
                if predicted_duration > 0:
                    duration_error_percents.append(abs(run.duration_ms - predicted_duration) / predicted_duration)

            predicted_rollback = cls._extract_probability(
                prediction,
                "predicted_rollback_risk",
                "rollback_risk",
            )
            if predicted_rollback is not None:
                rollback_errors.append(abs(predicted_rollback - (1.0 if run.rollback_required else 0.0)))

            likely_failures = prediction.get("likely_failures") or []
            if likely_failures and not run.success:
                likely_failure_total += 1
                observed = cls.classify_failure(run)
                text = json.dumps(likely_failures, default=str).lower()
                if observed and (observed in text or observed.replace("_", " ") in text):
                    likely_failure_matches += 1

        return {
            "success_error_mean": round(mean(success_errors), 4) if success_errors else 0.0,
            "duration_error_ms_mean": round(mean(duration_errors), 2) if duration_errors else 0.0,
            "duration_error_percent_mean": round(mean(duration_error_percents), 4) if duration_error_percents else 0.0,
            "rollback_error_mean": round(mean(rollback_errors), 4) if rollback_errors else 0.0,
            "likely_failure_match_rate": round(likely_failure_matches / likely_failure_total, 4) if likely_failure_total else 0.0,
            "samples": {
                "success": len(success_errors),
                "duration": len(duration_errors),
                "rollback": len(rollback_errors),
                "likely_failures": likely_failure_total,
            },
        }

    @staticmethod
    def _normalise_tool_runs(
        runs: Sequence[ToolBenchmarkRun | dict[str, Any]],
    ) -> list[ToolBenchmarkRun]:
        return [
            run if isinstance(run, ToolBenchmarkRun) else ToolBenchmarkRun.from_dict(run)
            for run in runs
        ]

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(values)
        if len(sorted_values) == 1:
            return float(sorted_values[0])
        index = int(round((len(sorted_values) - 1) * percentile))
        index = max(0, min(index, len(sorted_values) - 1))
        return float(sorted_values[index])

    @staticmethod
    def _rate_delta(candidate: float, baseline: float, *, lower_is_better: bool = False) -> float:
        if baseline == 0:
            if candidate == 0:
                return 0.0
            raw = 1.0
        else:
            raw = (candidate - baseline) / abs(baseline)
        return -raw if lower_is_better else raw

    @staticmethod
    def _format_delta(delta: float) -> str:
        sign = "+" if delta >= 0 else ""
        return f"{sign}{round(delta * 100, 1)}%"

    @staticmethod
    def _normalise_decision(value: Any) -> str:
        clean = str(value or "").strip().upper()
        aliases = {
            "APPROVED": "APPROVE",
            "ALLOW": "APPROVE",
            "ALLOWED": "APPROVE",
            "PASS": "APPROVE",
            "PASSED": "APPROVE",
            "ACCEPT": "APPROVE",
            "ACCEPTED": "APPROVE",
            "REJECTED": "REJECT",
            "DENY": "REJECT",
            "DENIED": "REJECT",
            "BLOCK": "REJECT",
            "BLOCKED": "REJECT",
            "FAIL": "REJECT",
            "FAILED": "REJECT",
        }
        return aliases.get(clean, clean)

    @classmethod
    def _decision_from_prediction(cls, prediction: dict[str, Any]) -> str:
        explicit = prediction.get("decision") or prediction.get("recommendation")
        if explicit:
            normalised = cls._normalise_decision(explicit)
            if normalised in {"APPROVE", "REJECT"}:
                return normalised
            text = str(explicit).lower()
            if any(term in text for term in ("revise", "reject", "block", "review")):
                return "REJECT"
            if any(term in text for term in ("proceed", "approve", "acceptable")):
                return "APPROVE"
        success_probability = cls._extract_probability(
            prediction,
            "success_probability",
            "predicted_success",
            "success_rate",
        )
        if success_probability is None:
            return ""
        return "APPROVE" if success_probability >= 0.70 else "REJECT"

    @staticmethod
    def _extract_number(data: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            if key not in data:
                continue
            value = data.get(key)
            if isinstance(value, bool):
                return 1.0 if value else 0.0
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @classmethod
    def _extract_probability(cls, data: dict[str, Any], *keys: str) -> float | None:
        value = cls._extract_number(data, *keys)
        if value is None:
            return None
        if value > 1.0 and value <= 100.0:
            value = value / 100.0
        return max(0.0, min(1.0, value))

    # -- 1. Sandbox Environment --------------------------------------------
    @classmethod
    @contextlib.contextmanager
    def sandbox(cls, authorized_commands: set[str] | None = None):
        """Disables database writes, file changes, and unsafe commands during evaluation."""
        import unittest.mock

        # Block SQLite mutating statements by wrapping the connection object
        original_connect = sqlite3.connect

        class SafeConnectionWrapper:
            def __init__(self, real_conn):
                self._conn = real_conn

            def execute(self, sql, *args, **kwargs):
                sql_upper = sql.strip().upper()
                if any(sql_upper.startswith(prefix) for prefix in ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "REPLACE"]):
                    raise PermissionError(f"Database mutation blocked in Sandbox: {sql[:100]}")
                return self._conn.execute(sql, *args, **kwargs)

            def executemany(self, sql, *args, **kwargs):
                sql_upper = sql.strip().upper()
                if any(sql_upper.startswith(prefix) for prefix in ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "REPLACE"]):
                    raise PermissionError(f"Database mutation blocked in Sandbox: {sql[:100]}")
                return self._conn.executemany(sql, *args, **kwargs)

            def executescript(self, sql_script, *args, **kwargs):
                sql_upper = sql_script.strip().upper()
                if any(prefix in sql_upper for prefix in ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "REPLACE"]):
                    raise PermissionError("Database script mutation blocked in Sandbox")
                return self._conn.executescript(sql_script, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._conn, name)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                return self._conn.__exit__(exc_type, exc_val, exc_tb)

        def safe_connect(*args, **kwargs):
            conn = original_connect(*args, **kwargs)
            return SafeConnectionWrapper(conn)

        # Block Chroma collection writes
        def mock_chroma_write(*args, **kwargs):
            raise PermissionError("ChromaDB mutation blocked in Sandbox")

        # Block file writing open
        original_open = open

        def safe_open(file, mode="r", *args, **kwargs):
            if any(c in mode for c in ["w", "a", "x", "+"]):
                raise PermissionError(f"File writing open blocked in Sandbox: {file} (mode={mode})")
            return original_open(file, mode, *args, **kwargs)

        # Block file manipulation operations
        def safe_file_op(*args, **kwargs):
            raise PermissionError("File system modification blocked in Sandbox")

        # Block subprocess commands
        original_run = subprocess.run
        original_popen = subprocess.Popen
        allowed_cmds = authorized_commands or set()

        def safe_run(args, *extra_args, **kwargs):
            cmd_str = args if isinstance(args, str) else " ".join(str(a) for a in args)
            if not any(ac in cmd_str for ac in allowed_cmds):
                raise PermissionError(f"Subprocess run command blocked in Sandbox: {cmd_str}")
            return original_run(args, *extra_args, **kwargs)

        def safe_popen(args, *extra_args, **kwargs):
            cmd_str = args if isinstance(args, str) else " ".join(str(a) for a in args)
            if not any(ac in cmd_str for ac in allowed_cmds):
                raise PermissionError(f"Subprocess Popen command blocked in Sandbox: {cmd_str}")
            return original_popen(args, *extra_args, **kwargs)

        # Setup patches
        patches = [
            unittest.mock.patch("sqlite3.connect", safe_connect),
            unittest.mock.patch("builtins.open", safe_open),
            unittest.mock.patch("os.remove", safe_file_op),
            unittest.mock.patch("os.unlink", safe_file_op),
            unittest.mock.patch("os.rename", safe_file_op),
            unittest.mock.patch("os.mkdir", safe_file_op),
            unittest.mock.patch("os.makedirs", safe_file_op),
            unittest.mock.patch("shutil.rmtree", safe_file_op),
            unittest.mock.patch("shutil.copy", safe_file_op),
            unittest.mock.patch("shutil.copy2", safe_file_op),
            unittest.mock.patch("subprocess.run", safe_run),
            unittest.mock.patch("subprocess.Popen", safe_popen),
        ]

        # Patch chromadb if present
        try:
            import chromadb.api.models.Collection as chroma_col
            patches.append(unittest.mock.patch.object(chroma_col.Collection, "add", mock_chroma_write))
            patches.append(unittest.mock.patch.object(chroma_col.Collection, "upsert", mock_chroma_write))
            patches.append(unittest.mock.patch.object(chroma_col.Collection, "update", mock_chroma_write))
            patches.append(unittest.mock.patch.object(chroma_col.Collection, "delete", mock_chroma_write))
        except ImportError:
            pass

        # Apply patches
        exit_stack = contextlib.ExitStack()
        try:
            for p in patches:
                exit_stack.enter_context(p)
            yield
        finally:
            exit_stack.close()

    # -- 2. Heuristic/Objective Scorers -------------------------------------
    @classmethod
    def score_memory(cls, actual: str, expected: str) -> float:
        """Exact match or substring check for recall evaluation."""
        if not expected or not actual:
            return 0.0
        return 1.0 if expected.strip().lower() in actual.strip().lower() else 0.0

    @classmethod
    def score_coding(cls, actual_code: str, expected_tests: str | None = None) -> float:
        """Compiles code and parses syntax tree objectively."""
        if not actual_code.strip():
            return 0.0
        try:
            ast.parse(actual_code)
            return 1.0
        except SyntaxError:
            return 0.0

    @classmethod
    def score_security(cls, actual_logs: list[str], expected_threat: str) -> float:
        """Determines if the safety/security engine caught the threat."""
        for log in actual_logs:
            log_lower = log.lower()
            if any(term in log_lower for term in ["veto", "block", "policy violation", "denied", "threat detected"]):
                if expected_threat.lower() in log_lower or "security" in log_lower:
                    return 1.0
        return 0.0

    @classmethod
    def score_planning(cls, actual_steps: list[str], constraints: list[str]) -> float:
        """Checks constraint satisfaction (expected step order or terms present)."""
        if not constraints:
            return 1.0
        if not actual_steps:
            return 0.0
        satisfied = 0
        joined_steps = " ".join(actual_steps).lower()
        for const in constraints:
            if const.lower() in joined_steps:
                satisfied += 1
        return satisfied / len(constraints)

    @classmethod
    def score_tools(cls, actual_selection: list[str], expected_tools: list[str]) -> float:
        """Jaccard similarity on correct tool selection."""
        if not expected_tools:
            return 1.0 if not actual_selection else 0.0
        act_set = {t.lower().strip() for t in actual_selection}
        exp_set = {t.lower().strip() for t in expected_tools}
        intersection = act_set.intersection(exp_set)
        union = act_set.union(exp_set)
        return len(intersection) / len(union) if union else 1.0

    @classmethod
    def score_speed(cls, latencies: list[float]) -> dict[str, float]:
        """Calculates tail speed metric percentiles."""
        if not latencies:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        sorted_l = sorted(latencies)
        n = len(sorted_l)
        p50 = sorted_l[int(n * 0.50)]
        p95 = sorted_l[int(n * 0.95)] if n > 1 else sorted_l[-1]
        p99 = sorted_l[int(n * 0.99)] if n > 1 else sorted_l[-1]
        return {"p50": round(p50, 4), "p95": round(p95, 4), "p99": round(p99, 4)}

    @classmethod
    def score_calibration(cls, predictions: list[float], outcomes: list[int]) -> float:
        """Calculates Brier Score (lower is better, returns 1.0 - BS)."""
        if not predictions or len(predictions) != len(outcomes):
            return 1.0
        # Brier Score = 1/N * sum((P_i - O_i)^2)
        total_sq_error = sum((p - o) ** 2 for p, o in zip(predictions, outcomes))
        bs = total_sq_error / len(predictions)
        # Returns score in range [0.0, 1.0] where 1.0 is perfectly calibrated
        return round(1.0 - bs, 4)

    # -- 3. System Incoherence (Protocol Violations) -----------------------
    @classmethod
    def calculate_scs(cls, violations: list[dict[str, Any]], total_checks: int = 1) -> float:
        """System Coherence Score penalizes workflow infractions, not healthy vetoes."""
        infractions = 0
        for v in violations:
            # Policy blocked but execution proceeded
            if v.get("policy_blocked") and v.get("execution_proceeded"):
                infractions += 1
            # Consensus rejected but value engine approved
            elif v.get("consensus_rejected") and v.get("value_engine_approved"):
                infractions += 1
            # Validators failed but value engine approved
            elif v.get("validators_failed") and v.get("value_engine_approved"):
                infractions += 1

        total = max(1, total_checks)
        return round(1.0 - (infractions / total), 4)

    # -- 4. Benchmark Integrity Score (BIS) --------------------------------
    @classmethod
    def calculate_bis(
        cls,
        chat_history: list[dict[str, Any]] | None,
        memory_queries: list[str] | None,
        benchmark_prompts: list[str],
    ) -> float:
        """Detects held-out test leakage or memorization contamination."""
        if not benchmark_prompts:
            return 1.0

        leakage_count = 0
        prompts_lower = [p.lower().strip() for p in benchmark_prompts]

        # 1. Leakage into Chat logs
        if chat_history:
            chat_contents = [m.get("content", "").lower().strip() for m in chat_history]
            for prompt in prompts_lower:
                if any(prompt in chat_content for chat_content in chat_contents):
                    leakage_count += 1

        # 2. Leakage into recall memories
        if memory_queries:
            for prompt in prompts_lower:
                if any(prompt in query.lower() for query in memory_queries):
                    leakage_count += 1

        return round(1.0 - (leakage_count / len(benchmark_prompts)), 4)

    # -- 5. Version Comparison & Category Floors ---------------------------
    @classmethod
    def compare_versions(
        cls,
        current_run: dict[str, Any],
        previous_run: dict[str, Any] | None,
        floors: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Compares current run metrics against previous run and category floors.

        Note: OCI is dashboard-only and is not used to determine approval.
        """
        floors = floors or cls.DEFAULT_FLOORS
        reasons = []
        approved = True
        regression_alarm = False

        current_scores = current_run.get("category_scores", {})
        previous_scores = (previous_run or {}).get("category_scores", {})

        # 1. Enforce Floors
        for category, floor in floors.items():
            if category in current_scores:
                current_score = current_scores[category]
                if current_score < floor:
                    approved = False
                    reasons.append(f"Category '{category}' score {current_score:.2f} is below the required floor of {floor:.2f}")

        # 2. Enforce Regression Alarms (drop > 5%)
        for category, prev_score in previous_scores.items():
            curr_score = current_scores.get(category, 0.0)
            if prev_score - curr_score > 0.05:
                approved = False
                regression_alarm = True
                reasons.append(f"Regression detected in category '{category}': dropped from {prev_score:.2f} to {curr_score:.2f}")

        curr_oci = current_run.get("oci", 0.0)
        prev_oci = (previous_run or {}).get("oci", 0.0)

        return {
            "approved": approved,
            "regression_triggered": regression_alarm,
            "reasons": reasons,
            "oci_delta": round(curr_oci - prev_oci, 4),
        }

    # -- 6. Persistent Immutable Logging -----------------------------------
    @classmethod
    def save_run(cls, run_report: dict[str, Any]) -> None:
        """Appends a completed benchmark run report to history log file."""
        path = _history_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        history = []
        if path.exists():
            try:
                history = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(history, list):
                    history = []
            except Exception:
                pass

        history.append(run_report)
        path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    @classmethod
    def load_history(cls) -> list[dict[str, Any]]:
        """Loads all historical benchmark runs."""
        path = _history_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    # -- 7. Execute Suite & Goodhart Firewall ------------------------------
    @classmethod
    def run_suite(
        cls,
        suite_id: str,
        items: list[dict[str, Any]],
        is_held_out: bool = False,
        chat_history: list[dict[str, Any]] | None = None,
        memory_queries: list[str] | None = None,
        violations: list[dict[str, Any]] | None = None,
        latencies: list[float] | None = None,
        predictions: list[float] | None = None,
        outcomes: list[int] | None = None,
    ) -> dict[str, Any]:
        """Runs the benchmark suite under read-only sandbox. Enforces Firewall."""
        import random
        import math

        # Enforce fixed seed for deterministic reproducibility across versions
        random.seed(42)
        try:
            import numpy as np
            np.random.seed(42)
        except ImportError:
            pass

        start_time = time.time()

        # Group metrics counts
        results_map: dict[str, list[float]] = {cat.value: [] for cat in BenchmarkCategory}

        # Run items inside the sandbox context
        with cls.sandbox(authorized_commands={"python", "pytest"}):
            for item in items:
                category = item.get("category", "")
                actual = item.get("actual", "")
                expected = item.get("expected", "")

                score = 0.0
                if category == BenchmarkCategory.MEMORY:
                    score = cls.score_memory(actual, expected)
                elif category == BenchmarkCategory.CODING:
                    score = cls.score_coding(actual, expected)
                elif category == BenchmarkCategory.PLANNING:
                    score = cls.score_planning([actual], item.get("constraints", []))
                elif category == BenchmarkCategory.TOOLS:
                    score = cls.score_tools([actual], item.get("expected_tools", []))
                elif category == BenchmarkCategory.SECURITY:
                    score = cls.score_security(item.get("logs", []), expected)
                else:
                    # Default score
                    score = 1.0 if actual == expected else 0.0

                if category in results_map:
                    results_map[category].append(score)

        # Post-run metrics computations with stats (Confidence Intervals)
        category_scores: dict[str, float] = {}
        category_stats: dict[str, dict[str, Any]] = {}

        for cat, scores in results_map.items():
            if scores:
                mean = sum(scores) / len(scores)
                # Compute Standard Deviation
                if len(scores) > 1:
                    variance = sum((s - mean) ** 2 for s in scores) / (len(scores) - 1)
                    sd = math.sqrt(variance)
                else:
                    sd = 0.0

                # Standard Error and Margin of Error (95%)
                se = sd / math.sqrt(len(scores))
                margin = 1.96 * se
                ci_lower = max(0.0, mean - margin)
                ci_upper = min(1.0, mean + margin)

                category_scores[cat] = round(mean, 4)
                category_stats[cat] = {
                    "mean": round(mean, 4),
                    "ci95": [round(ci_lower, 4), round(ci_upper, 4)],
                    "sample_size": len(scores)
                }
            else:
                # Default empty categories to neutral
                category_scores[cat] = 1.0
                category_stats[cat] = {
                    "mean": 1.0,
                    "ci95": [1.0, 1.0],
                    "sample_size": 0
                }

        # System Coherence Score
        scs = cls.calculate_scs(violations or [], len(violations) if violations else 1)
        category_scores["coherence"] = scs
        category_stats["coherence"] = {
            "mean": scs,
            "ci95": [scs, scs],
            "sample_size": len(violations) if violations else 0
        }

        # Brier Calibration score
        if predictions and outcomes:
            cal_score = cls.score_calibration(predictions, outcomes)
            category_scores["calibration"] = cal_score
            category_stats["calibration"] = {
                "mean": cal_score,
                "ci95": [cal_score, cal_score],
                "sample_size": len(predictions)
            }
        else:
            category_scores["calibration"] = 1.0
            category_stats["calibration"] = {
                "mean": 1.0,
                "ci95": [1.0, 1.0],
                "sample_size": 0
            }

        # Benchmark Integrity Score
        benchmark_prompts = [item.get("prompt", "") for item in items]
        bis = cls.calculate_bis(chat_history, memory_queries, benchmark_prompts)

        # Tail speed metrics
        speed_stats = cls.score_speed(latencies or [])
        category_scores["speed"] = 1.0 if not speed_stats["p95"] else round(1.0 / max(0.01, speed_stats["p95"]), 4)
        category_stats["speed"] = {
            "mean": category_scores["speed"],
            "ci95": [category_scores["speed"], category_scores["speed"]],
            "sample_size": len(latencies) if latencies else 0
        }

        # OCI (Overall Capability Index) is weighted dashboard metric
        weights = {
            "security": 0.25,
            "planning": 0.20,
            "coding": 0.15,
            "memory": 0.15,
            "tools": 0.10,
            "calibration": 0.10,
            "coherence": 0.05,
        }
        oci = sum(category_scores.get(k, 0.0) * w for k, w in weights.items())

        # Clean/Format Report (Goodhart Firewall: mask item details if held-out)
        report = {
            "run_id": f"run_{int(time.time())}",
            "suite_id": suite_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "is_held_out": is_held_out,
            "duration": round(time.time() - start_time, 2),
            "oci": round(oci, 4),
            "category_scores": category_scores,
            "category_stats": category_stats,
            "speed_percentiles": speed_stats,
            "bis": bis,
        }

        if not is_held_out:
            # Public splits show details
            report["items_evaluated"] = [
                {
                    "id": item.get("id"),
                    "category": item.get("category"),
                    "prompt": item.get("prompt"),
                }
                for item in items
            ]
        else:
            # Firewall: private/held-out splits mask prompts and inputs
            report["items_evaluated_count"] = len(items)

        # Save Report
        cls.save_run(report)

        return report
