"""Execution Scorer Scorecard Compiler (Program 13.0).
"""
from __future__ import annotations

from typing import List
from backend.core.evaluation.scorecard import Scorecard
from backend.core.evaluation.plan_evaluator import PlanEvaluation


class ExecutionScorer:
    """Aggregates plan evaluation runs to compile and rank scorecard metrics."""

    @staticmethod
    def compile_scorecard(planner_version: str, evaluations: List[PlanEvaluation]) -> Scorecard:
        """Translates a collection of evaluations into a balanced Scorecard."""
        if not evaluations:
            return Scorecard(planner_version=planner_version)

        total = len(evaluations)
        successes = sum(1 for e in evaluations if e.success)
        recoveries = sum(1 for e in evaluations if e.recovery_triggered)
        approvals = sum(1 for e in evaluations if e.user_approved)

        total_dur_err = sum(e.duration_error for e in evaluations)
        total_cost_err = sum(e.cost_error for e in evaluations)

        scorecard = Scorecard(
            planner_version=planner_version,
            total_plans=total,
            success_rate=round(successes / total, 3),
            avg_duration_error=round(total_dur_err / total, 3),
            avg_cost_error=round(total_cost_err / total, 3),
            recovery_rate=round(recoveries / total, 3),
            user_approval_rate=round(approvals / total, 3),
        )
        
        # Calculate combined rating out of 100
        scorecard.compute_combined_score()
        return scorecard
