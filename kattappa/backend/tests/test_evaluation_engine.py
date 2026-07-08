"""Unit tests for Program 13.0 Evaluation Layer Foundation.
"""
from __future__ import annotations

import pytest
from backend.core.evaluation.scorecard import Scorecard
from backend.core.evaluation.metric_registry import MetricRegistry
from backend.core.evaluation.plan_evaluator import PlanEvaluator, PlanEvaluation
from backend.core.evaluation.execution_scorer import ExecutionScorer
from backend.core.evaluation.regression_detector import RegressionDetector
from backend.core.evaluation.planner_leaderboard import PlannerLeaderboard


def test_plan_evaluator_drift_scores():
    """Verifies duration and cost error calculation, along with risk underestimation checks."""
    evaluator = PlanEvaluator()

    predicted = {
        "expected_duration": 10.0,
        "expected_cost": 2.0,
        "risk_score": 0.15,
    }

    actual = {
        "duration": 15.0,
        "cost": 3.0,
        "success": True,
        "recovery_triggered": False,
        "user_approved": True,
        "risk_event_occurred": True,  # Actual risk event occurred!
    }

    evaluation = evaluator.evaluate("plan-1", predicted, actual)

    # absolute percentage errors:
    # Duration: |15.0 - 10.0| / 10.0 = 0.50
    # Cost: |3.0 - 2.0| / 2.0 = 0.50
    assert evaluation.duration_error == 0.50
    assert evaluation.cost_error == 0.50
    assert evaluation.success is True
    # Risk was underestimated because predicted risk (0.15) was < 0.3 but a risk event occurred!
    assert evaluation.risk_underestimated is True


def test_execution_scorer_and_scorecard_compilation():
    """Verifies compiling list of evaluations yields correct balanced scorecard values."""
    evals = [
        PlanEvaluation(
            plan_id="plan-1",
            duration_error=0.10,
            cost_error=0.05,
            success=True,
            recovery_triggered=False,
            user_approved=True,
            risk_underestimated=False,
        ),
        PlanEvaluation(
            plan_id="plan-2",
            duration_error=0.20,
            cost_error=0.15,
            success=True,
            recovery_triggered=True,  # 1 recovery trigger
            user_approved=True,
            risk_underestimated=False,
        ),
        PlanEvaluation(
            plan_id="plan-3",
            duration_error=0.30,
            cost_error=0.10,
            success=False,             # 1 failure
            recovery_triggered=False,
            user_approved=False,       # 1 non-approval
            risk_underestimated=True,
        ),
    ]

    scorecard = ExecutionScorer.compile_scorecard("HTN-v1.1", evals)

    # Success rate: 2/3 = 0.667
    assert scorecard.success_rate == 0.667
    # Recovery rate: 1/3 = 0.333
    assert scorecard.recovery_rate == 0.333
    # User approval: 2/3 = 0.667
    assert scorecard.user_approval_rate == 0.667

    # Average errors:
    # Duration: (0.10 + 0.20 + 0.30) / 3 = 0.20
    # Cost: (0.05 + 0.15 + 0.10) / 3 = 0.10
    assert scorecard.avg_duration_error == 0.20
    assert scorecard.avg_cost_error == 0.10

    # Verify combined score computation:
    # w_success = 0.40 -> 0.667 * 0.40 = 0.2668
    # w_duration_accuracy = 0.20 -> (1.0 - 0.20) * 0.20 = 0.16
    # w_cost_accuracy = 0.15 -> (1.0 - 0.10) * 0.15 = 0.135
    # w_recovery_penalty = 0.15 -> (1.0 - 0.333) * 0.15 = 0.10005
    # w_approval = 0.10 -> 0.667 * 0.10 = 0.0667
    # Total sum = 0.2668 + 0.16 + 0.135 + 0.10005 + 0.0667 = 0.72855
    # score = 72.86
    assert scorecard.combined_score == 72.86


def test_metric_registry_thresholds():
    """Verifies registry flags metrics crossing bounds."""
    registry = MetricRegistry()

    # Success rate < 0.8 should trigger warning
    assert registry.check_threshold("success_rate", 0.75) is True
    assert registry.check_threshold("success_rate", 0.85) is False

    # Duration error > 0.30 should trigger warning (is_lower_better=True)
    assert registry.check_threshold("avg_duration_error", 0.35) is True
    assert registry.check_threshold("avg_duration_error", 0.25) is False


def test_regression_detector():
    """Verifies that performance degradations trigger regression warnings."""
    detector = RegressionDetector()

    baseline = Scorecard(
        planner_version="HTN-v1.1",
        total_plans=10,
        success_rate=0.95,
        avg_duration_error=0.10,
        avg_cost_error=0.05,
        recovery_rate=0.0,
        user_approval_rate=1.0,
        combined_score=95.0,
    )

    current_degraded = Scorecard(
        planner_version="HTN-v1.2",
        total_plans=10,
        success_rate=0.88,  # Degraded > 5%
        avg_duration_error=0.12,
        avg_cost_error=0.06,
        recovery_rate=0.0,
        user_approval_rate=1.0,
        combined_score=89.0,  # Degraded > 5 points
    )

    result = detector.detect_regression(current_degraded, baseline)
    assert result["has_regression"] is True
    assert len(result["degradations"]) >= 2


def test_planner_leaderboard():
    """Verifies registering and sorting scorecard versions."""
    leaderboard = PlannerLeaderboard()

    v1 = Scorecard("HTN-v1.1", combined_score=82.5)
    v2 = Scorecard("HTN-v1.2", combined_score=89.4)
    v3 = Scorecard("MCTS-v1.0", combined_score=86.1)

    leaderboard.register_scorecard(v1)
    leaderboard.register_scorecard(v2)
    leaderboard.register_scorecard(v3)

    rankings = leaderboard.get_rankings()
    assert len(rankings) == 3
    # Sorted descending by combined_score: HTN-v1.2 (89.4), MCTS-v1.0 (86.1), HTN-v1.1 (82.5)
    assert rankings[0].planner_version == "HTN-v1.2"
    assert rankings[1].planner_version == "MCTS-v1.0"
    assert rankings[2].planner_version == "HTN-v1.1"
