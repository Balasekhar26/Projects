from __future__ import annotations
from typing import Any
from backend.core.orchestrator.base import BaseAgent, Task, TaskResult
from backend.core.orchestrator.context import SharedContext
from backend.core.logger import log_event
from backend.core.reflection_engine import ReflectionEngine

class ReflectionAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Reflection"

    def initialize(self) -> None:
        pass

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        log_event("reflection_agent_exec", "Reflection Agent executing task")
        try:
            task_id = task.params.get("task_id")
            if task_id or "success" in task.params:
                domain = task.params.get("domain") or "planning"
                statement = task.params.get("statement") or task.params.get("problem") or "Execution check"
                success = task.params.get("success", True)
                confidence = float(task.params.get("confidence", 0.8))
                res = ReflectionEngine.reflect_and_learn(
                    task_id=task_id or task.task_id,
                    domain=domain,
                    statement=statement,
                    success=success,
                    confidence=confidence,
                )
            else:
                problem = task.params.get("problem") or "Execution check"
                cause = task.params.get("cause") or "Standard flow validation"
                improvement = task.params.get("improvement") or "Continuous monitoring"
                res = ReflectionEngine.reflect(problem, cause, improvement)
            return TaskResult(success=True, output=res)
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    def terminate(self, task_id: str) -> None:
        pass
