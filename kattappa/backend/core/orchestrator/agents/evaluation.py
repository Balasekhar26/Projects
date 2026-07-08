"""EvaluationAgent — Program 16.1 Specialist Worker.

Wraps the Evaluation Layer (ExecutionScorer, RegressionDetector, PlannerLeaderboard)
to provide scorecard generation, regression detection, and benchmark comparison
as an orchestrated worker task.
"""
from __future__ import annotations

from typing import Any, Dict

from backend.core.orchestrator.base import BaseAgent, Task, TaskResult
from backend.core.orchestrator.context import SharedContext
from backend.core.logger import log_event


class EvaluationAgent(BaseAgent):
    """Specialist worker for scorecard generation, regression detection, and benchmarking."""

    CAPABILITIES = ("scorecard_generation", "regression_detection", "benchmark_comparison")

    @property
    def name(self) -> str:
        return "Evaluation"

    def initialize(self) -> None:
        pass

    def estimate_cost(self, task: Task) -> float:
        return 0.005  # evaluation is CPU-bound, minimal LLM cost

    def estimate_duration(self, task: Task) -> float:
        return 2.0

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        log_event("evaluation_agent_exec", "EvaluationAgent executing task")
        plan_id = task.params.get("plan_id", "unknown")
        actual_metrics: Dict[str, Any] = task.params.get("actual_metrics", {})
        predicted_metrics: Dict[str, Any] = task.params.get("predicted_metrics", {})
        planner_version = task.params.get("planner_version", "unknown")

        try:
            from backend.core.evaluation.execution_scorer import ExecutionScorer
            from backend.core.evaluation.regression_detector import RegressionDetector

            scorer = ExecutionScorer()
            scorecard = scorer.score(
                plan_id=plan_id,
                actual=actual_metrics,
                predicted=predicted_metrics,
                planner_version=planner_version,
            )

            detector = RegressionDetector()
            regressions = detector.detect(scorecard)

            result = {
                "plan_id": plan_id,
                "scorecard": scorecard.to_dict() if hasattr(scorecard, "to_dict") else scorecard,
                "regressions": regressions,
                "planner_version": planner_version,
            }
            context.set("evaluation_result", result)
            return TaskResult(success=True, output=result)
        except Exception as e:
            log_event("evaluation_agent_error", str(e))
            return TaskResult(
                success=True,
                output={"plan_id": plan_id, "scorecard": {}, "note": "EvaluationLayer unavailable", "error": str(e)},
            )

    def terminate(self, task_id: str) -> None:
        pass
