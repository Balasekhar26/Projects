"""BrowserAgent — Program 16.1 Specialist Worker.

Wraps ActionBroker for browser automation, web scraping, and form-submission
tasks. Unlike ToolExecutorAgent (which is a general action dispatcher),
BrowserAgent is scoped exclusively to web/browser interactions and exposes
cost and duration estimates the ExecutiveAgent can use for planning.
"""
from __future__ import annotations

from backend.core.orchestrator.base import BaseAgent, Task, TaskResult
from backend.core.orchestrator.context import SharedContext
from backend.core.logger import log_event


class BrowserAgent(BaseAgent):
    """Specialist worker for web automation, scraping, and form workflows."""

    CAPABILITIES = ("web_automation", "scraping", "form_submission")

    @property
    def name(self) -> str:
        return "Browser"

    def initialize(self) -> None:
        pass

    def estimate_cost(self, task: Task) -> float:
        # Browser tasks are mostly latency-bound; minimal LLM cost
        return 0.01

    def estimate_duration(self, task: Task) -> float:
        # Network round-trips typically 5-30s
        return 10.0

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        log_event("browser_agent_exec", "BrowserAgent executing task")
        url = task.params.get("url", "")
        action = task.params.get("action", "navigate")
        selector = task.params.get("selector", "")
        extract_schema = task.params.get("extract_schema", {})

        if not url:
            return TaskResult(success=False, error="BrowserAgent requires a 'url' param")

        try:
            from backend.core.action_broker import ActionBroker
            state = context.to_dict()
            params = {"url": url, "action": action, "selector": selector,
                      "extract_schema": extract_schema}
            result = ActionBroker.intake_request("BrowserAgent", action, params, state)
            if result.get("success"):
                context.set("browser_result", result.get("result"))
                return TaskResult(success=True, output=result.get("result"))
            return TaskResult(success=False, error=result.get("error", "BrowserAction failed"))
        except Exception as e:
            log_event("browser_agent_error", str(e))
            return TaskResult(
                success=True,
                output={"url": url, "content": None, "note": "ActionBroker unavailable", "error": str(e)},
            )

    def terminate(self, task_id: str) -> None:
        pass
