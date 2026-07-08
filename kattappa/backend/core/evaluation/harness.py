"""Continuous Evaluation Harness (Program 22.0).

Benchmarks and validates plan quality, task completion, recovery reliability,
hallucination rates, tool errors, latencies, and transaction costs.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from backend.core.learning.trajectory_builder import Trajectory

logger = logging.getLogger(__name__)


class EvaluationHarness:
    """Calculates continuous system integration performance metrics and triggers regression alerts."""

    @classmethod
    def evaluate_trajectory(cls, trajectory: Trajectory) -> Dict[str, Any]:
        """Runs metric calculations on a single execution trajectory."""
        nodes = trajectory.nodes_executed or []
        total_nodes = len(nodes)
        
        # 1. Planning Quality (success rate parameter + base score)
        plan_quality = trajectory.combined_score / 100.0

        # 2. Task Completion Rate
        failed_count = sum(1 for n in nodes if n.startswith("failed:"))
        # If successfully completed without overall failure, target nodes completed
        completed_ratio = (total_nodes - failed_count) / total_nodes if total_nodes else 0.0

        # 3. Recovery Success Rate
        recovery_success = 0.0
        if trajectory.recoveries_count > 0:
            # Simple metric: if successes occurred after repairs, recovery succeeded
            recovery_success = 1.0 if trajectory.success else 0.0

        # 4. Hallucination Frequency
        # Scans for invalid/unregistered indicators or ungrounded coordinate fallback placeholders
        hallucinations = 0
        hallucination_indicators = ["untrusted", "mock", "placeholder", "fake", "unknown"]
        for node in nodes:
            if any(ind in node.lower() for ind in hallucination_indicators):
                hallucinations += 1
        hallucination_rate = hallucinations / total_nodes if total_nodes else 0.0

        # 5. Tool Reliability
        # Node errors frequency
        tool_reliability = 1.0 - (failed_count / total_nodes if total_nodes else 0.0)

        # 6. Latency Deviation
        latency_dev = 0.0
        if trajectory.predicted_duration > 0:
            latency_dev = abs(trajectory.actual_duration - trajectory.predicted_duration) / trajectory.predicted_duration

        # 7. Cost Deviation
        cost_dev = 0.0
        if trajectory.predicted_cost > 0:
            cost_dev = abs(trajectory.actual_cost - trajectory.predicted_cost) / trajectory.predicted_cost

        return {
            "goal_id": trajectory.goal_id,
            "success": trajectory.success,
            "planning_quality": round(plan_quality, 3),
            "task_completion_rate": round(completed_ratio, 3),
            "recovery_success_rate": round(recovery_success, 3),
            "hallucination_frequency": round(hallucination_rate, 3),
            "tool_reliability": round(tool_reliability, 3),
            "latency_deviation": round(latency_dev, 3),
            "cost_deviation": round(cost_dev, 3),
            "actual_duration": trajectory.actual_duration,
            "actual_cost": trajectory.actual_cost
        }

    @classmethod
    def aggregate_harness_metrics(cls, trajectories: List[Trajectory]) -> Dict[str, Any]:
        """Compiles a report summarizing performance across multiple trajectories."""
        if not trajectories:
            return {}

        total_runs = len(trajectories)
        success_runs = sum(1 for t in trajectories if t.success)
        
        sum_planning_quality = 0.0
        sum_completion_rate = 0.0
        sum_recovery_success = 0.0
        sum_hallucinations = 0.0
        sum_reliability = 0.0
        sum_latency_dev = 0.0
        sum_cost_dev = 0.0
        
        recovery_runs_count = 0

        for t in trajectories:
            metrics = cls.evaluate_trajectory(t)
            sum_planning_quality += metrics["planning_quality"]
            sum_completion_rate += metrics["task_completion_rate"]
            sum_hallucinations += metrics["hallucination_frequency"]
            sum_reliability += metrics["tool_reliability"]
            sum_latency_dev += metrics["latency_deviation"]
            sum_cost_dev += metrics["cost_deviation"]

            if t.recoveries_count > 0:
                recovery_runs_count += 1
                sum_recovery_success += metrics["recovery_success_rate"]

        return {
            "total_runs": total_runs,
            "overall_success_rate": round(success_runs / total_runs, 3),
            "avg_planning_quality": round(sum_planning_quality / total_runs, 3),
            "avg_task_completion_rate": round(sum_completion_rate / total_runs, 3),
            "avg_recovery_success_rate": round(sum_recovery_success / recovery_runs_count, 3) if recovery_runs_count else 1.0,
            "avg_hallucination_frequency": round(sum_hallucinations / total_runs, 3),
            "avg_tool_reliability": round(sum_reliability / total_runs, 3),
            "avg_latency_deviation": round(sum_latency_dev / total_runs, 3),
            "avg_cost_deviation": round(sum_cost_dev / total_runs, 3)
        }

    @classmethod
    def detect_harness_regressions(
        cls,
        current: Dict[str, Any],
        baseline: Dict[str, Any]
    ) -> List[str]:
        """Detects performance degradations greater than 15% against the baseline."""
        regressions = []
        
        # Helper to check drop in positive metrics
        def check_drop(metric: str, label: str):
            curr_val = current.get(metric, 1.0)
            base_val = baseline.get(metric, 1.0)
            if curr_val < base_val * 0.85:  # drops by more than 15%
                regressions.append(f"{label} degraded from {base_val:.3f} to {curr_val:.3f} (>15% drop)")

        # Helper to check increase in negative metrics (cost, latency dev, hallucination rate)
        def check_rise(metric: str, label: str):
            curr_val = current.get(metric, 0.0)
            base_val = baseline.get(metric, 0.0)
            # Avoid division by zero, check absolute increases
            if base_val > 0 and curr_val > base_val * 1.15:  # increases by more than 15%
                regressions.append(f"{label} increased from {base_val:.3f} to {curr_val:.3f} (>15% rise)")
            elif base_val == 0 and curr_val > 0.15:
                regressions.append(f"{label} increased from 0.000 to {curr_val:.3f} (>15% absolute rise)")

        check_drop("overall_success_rate", "Overall success rate")
        check_drop("avg_planning_quality", "Average planning quality")
        check_drop("avg_task_completion_rate", "Average task completion rate")
        check_drop("avg_recovery_success_rate", "Average recovery success rate")
        check_drop("avg_tool_reliability", "Average tool reliability")
        
        check_rise("avg_hallucination_frequency", "Average hallucination frequency")
        check_rise("avg_latency_deviation", "Average latency deviation")
        check_rise("avg_cost_deviation", "Average cost deviation")

        if regressions:
            logger.warning("ContinuousEvaluationHarness: Regressions detected! — %s", regressions)

        return regressions
