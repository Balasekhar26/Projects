"""ScientistAgent — Phase K14.

Runs the hypothesis candidate proposer, runs the Disprover check, and commits
the outcomes to the Knowledge Graph depending on the survival probability.
"""
from __future__ import annotations

from typing import Any

from backend.core.orchestrator.base import BaseAgent, Task, TaskResult
from backend.core.orchestrator.context import SharedContext
from backend.core.logger import log_event
from backend.core.scientist import Scientist


class ScientistAgent(BaseAgent):
    """Orchestrates candidate hypothesis proposals and falsification trials."""

    @property
    def name(self) -> str:
        return "Scientist"

    def initialize(self) -> None:
        pass

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        log_event("scientist_agent_exec", "Scientist Agent executing task")

        domain = task.params.get("domain") or "planning"
        statement = task.params.get("statement") or context.get("user_input") or "Hypothesis candidate"
        confidence = float(task.params.get("confidence", 0.8))
        evidence = task.params.get("evidence") or []

        try:
            # 1. Propose candidates
            candidates = Scientist.propose_hypotheses(
                domain=domain,
                context={
                    "statement": statement,
                    "confidence": confidence,
                    "evidence": evidence,
                }
            )

            # 2. Evaluate and commit the primary proposed candidate
            if not candidates:
                return TaskResult(success=False, error="No hypothesis candidates could be generated")

            candidate = candidates[0]
            result = Scientist.evaluate_and_commit(candidate)

            context.set("scientist_outcome", result)
            return TaskResult(success=True, output=result)

        except Exception as e:
            log_event("scientist_agent_error", str(e))
            return TaskResult(success=False, error=str(e))

    def terminate(self, task_id: str) -> None:
        pass
