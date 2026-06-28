from __future__ import annotations
from typing import Any
from backend.core.orchestrator.base import BaseAgent, Task, TaskResult
from backend.core.orchestrator.context import SharedContext
from backend.core.logger import log_event
from backend.core.action_broker import ActionBroker

class ToolExecutorAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Tool Executor"

    def initialize(self) -> None:
        pass

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        log_event("tool_agent_exec", "Tool Executor Agent executing task")
        action = task.params.get("action") or task.action
        params = task.params.get("params") or task.params
        
        try:
            state = context.to_dict()
            res = ActionBroker.intake_request("OrchestrationAgent", action, params, state)
            if res.get("success"):
                return TaskResult(success=True, output=res.get("result"))
            else:
                return TaskResult(success=False, error=res.get("error") or "Execution failed")
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    def terminate(self, task_id: str) -> None:
        pass
