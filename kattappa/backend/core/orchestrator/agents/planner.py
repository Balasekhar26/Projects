from __future__ import annotations
from typing import Any
from backend.core.orchestrator.base import BaseAgent, Task, TaskResult
from backend.core.orchestrator.context import SharedContext
from backend.core.logger import log_event
from backend.agents.planner import PlannerAgent as LegacyPlannerAgent

class PlannerAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Planner"

    def initialize(self) -> None:
        self.legacy_planner = LegacyPlannerAgent()

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        log_event("planner_agent_exec", "Planner Agent executing task")
        goal = task.params.get("goal") or context.get("user_input") or ""
        try:
            legacy_graph = self.legacy_planner.decompose(goal, context.to_dict())
            steps = {step_id: step.to_dict() for step_id, step in legacy_graph.steps.items()}
            context.set("task_graph_steps", steps)
            return TaskResult(success=True, output=steps)
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    def terminate(self, task_id: str) -> None:
        pass
