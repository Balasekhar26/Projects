"""Unit tests for Program 22.0: Continuous Evaluation Harness.

Verifies trajectory metrics calculation, report aggregation, and 15% regression checks.
"""
from __future__ import annotations

import pytest

from backend.core.learning.trajectory_builder import Trajectory
from backend.core.evaluation.harness import EvaluationHarness


class TestEvaluationHarness:
    def test_evaluate_single_trajectory_success(self):
        t = Trajectory(
            goal_id="deploy-harness",
            plan_id="p-100",
            planner_version="HTN-v1",
            success=True,
            predicted_duration=10.0,
            actual_duration=11.0,  # 10% latency dev
            predicted_cost=2.0,
            actual_cost=2.0,
            failures_count=0,
            recoveries_count=0,
            combined_score=90.0,
            nodes_executed=["SetupWorkspace", "PullBaseImage", "mock-run"]  # "mock-run" contains "mock" -> 1 hallucination
        )

        metrics = EvaluationHarness.evaluate_trajectory(t)

        assert metrics["goal_id"] == "deploy-harness"
        assert metrics["success"] is True
        assert metrics["planning_quality"] == 0.90
        assert metrics["task_completion_rate"] == 1.0  # no failed nodes
        assert metrics["tool_reliability"] == 1.0
        assert metrics["latency_deviation"] == 0.1
        assert metrics["cost_deviation"] == 0.0
        assert metrics["hallucination_frequency"] == round(1 / 3, 3)

    def test_evaluate_single_trajectory_failure_with_recoveries(self):
        t = Trajectory(
            goal_id="deploy-harness",
            plan_id="p-200",
            planner_version="HTN-v1",
            success=False,
            predicted_duration=10.0,
            actual_duration=15.0,  # 50% latency dev
            predicted_cost=2.0,
            actual_cost=3.0,  # 50% cost dev
            failures_count=1,
            recoveries_count=1,
            combined_score=40.0,
            nodes_executed=["SetupWorkspace", "failed:PullBaseImage"]
        )

        metrics = EvaluationHarness.evaluate_trajectory(t)

        assert metrics["success"] is False
        assert metrics["planning_quality"] == 0.40
        assert metrics["task_completion_rate"] == 0.5  # 1/2 nodes completed
        assert metrics["recovery_success_rate"] == 0.0  # recovery ran but run still failed
        assert metrics["tool_reliability"] == 0.5  # 1 failed node

    def test_aggregate_harness_metrics(self):
        t1 = Trajectory("g1", "p1", "v1", success=True, predicted_duration=10, actual_duration=10, predicted_cost=1, actual_cost=1, failures_count=0, recoveries_count=0, combined_score=90.0, nodes_executed=["A"])
        t2 = Trajectory("g2", "p2", "v1", success=True, predicted_duration=10, actual_duration=10, predicted_cost=1, actual_cost=1, failures_count=0, recoveries_count=1, combined_score=80.0, nodes_executed=["A"])
        
        report = EvaluationHarness.aggregate_harness_metrics([t1, t2])

        assert report["total_runs"] == 2
        assert report["overall_success_rate"] == 1.0
        assert report["avg_planning_quality"] == 0.85
        assert report["avg_recovery_success_rate"] == 1.0  # 1 recovery run, success=True

    def test_detect_harness_regressions(self):
        baseline = {
            "overall_success_rate": 0.95,
            "avg_planning_quality": 0.90,
            "avg_task_completion_rate": 0.95,
            "avg_recovery_success_rate": 0.90,
            "avg_tool_reliability": 0.95,
            "avg_hallucination_frequency": 0.05,
            "avg_latency_deviation": 0.10,
            "avg_cost_deviation": 0.05
        }

        # 1. Healthy comparison -> no regressions
        current_healthy = baseline.copy()
        current_healthy["avg_planning_quality"] = 0.88  # tiny drop, <15%
        regressions_none = EvaluationHarness.detect_harness_regressions(current_healthy, baseline)
        assert len(regressions_none) == 0

        # 2. Regression comparison -> drops in success rate and spike in latency
        current_regressed = baseline.copy()
        current_regressed["overall_success_rate"] = 0.70  # drops >15%
        current_regressed["avg_latency_deviation"] = 0.25  # increases >15%
        
        regressions = EvaluationHarness.detect_harness_regressions(current_regressed, baseline)
        assert len(regressions) == 2
        assert any("Overall success rate" in r for r in regressions)
        assert any("Average latency deviation" in r for r in regressions)
