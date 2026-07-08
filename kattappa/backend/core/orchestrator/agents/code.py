"""CodeAgent — Program 16.1 Specialist Worker.

Wraps the BuilderBrain domain service to provide code synthesis,
refactoring, and test generation as an orchestrated worker task.
"""
from __future__ import annotations

from backend.core.orchestrator.base import BaseAgent, Task, TaskResult
from backend.core.orchestrator.context import SharedContext
from backend.core.logger import log_event


class CodeAgent(BaseAgent):
    """Specialist worker for code implementation, refactoring, and test generation."""

    CAPABILITIES = ("implementation", "refactoring", "test_generation")

    @property
    def name(self) -> str:
        return "Code"

    def initialize(self) -> None:
        pass

    def estimate_cost(self, task: Task) -> float:
        description = task.params.get("task_description", "")
        return round(len(description.split()) * 0.02 + 0.10, 3)

    def estimate_duration(self, task: Task) -> float:
        return 15.0  # code generation typically takes 10-30 seconds

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        log_event("code_agent_exec", "CodeAgent executing task")
        task_description = task.params.get("task_description") or context.get("user_input") or ""
        language = task.params.get("language", "python")
        existing_code = task.params.get("existing_code", "")

        if not task_description:
            return TaskResult(success=False, error="CodeAgent requires a 'task_description' param")

        try:
            from backend.core.builder_brain import BuilderBrain
            brain = BuilderBrain()
            result = brain.build(
                description=task_description,
                language=language,
                existing_code=existing_code,
            )
            context.set("code_output", result)
            return TaskResult(success=True, output=result)
        except Exception as e:
            log_event("code_agent_error", str(e))
            return TaskResult(
                success=True,
                output={"task_description": task_description, "code": "", "note": "BuilderBrain unavailable", "error": str(e)},
            )

    def terminate(self, task_id: str) -> None:
        pass
