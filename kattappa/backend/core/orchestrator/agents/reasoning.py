from __future__ import annotations
from typing import Any
from backend.core.orchestrator.base import BaseAgent, Task, TaskResult
from backend.core.orchestrator.context import SharedContext
from backend.core.logger import log_event

class ReasoningAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Reasoning"

    def initialize(self) -> None:
        pass

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        log_event("reasoning_agent_exec", "Reasoning Agent executing task")
        prompt = task.params.get("prompt") or context.get("user_input") or ""
        try:
            from backend.core.agent_router import DEFAULT_ROUTER
            routing = DEFAULT_ROUTER.route(prompt)
            context.set("reasoning_output", routing.to_dict())
            return TaskResult(success=True, output=routing.to_dict())
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    def terminate(self, task_id: str) -> None:
        pass
