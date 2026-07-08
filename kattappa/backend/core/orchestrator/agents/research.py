"""ResearchAgent — Program 16.1 Specialist Worker.

Wraps the standalone ResearchAgent domain service to provide structured
web retrieval, evidence gathering, and citation generation as an orchestrated
worker task accessible by the ExecutiveAgent.
"""
from __future__ import annotations

from typing import Any

from backend.core.orchestrator.base import BaseAgent, Task, TaskResult
from backend.core.orchestrator.context import SharedContext
from backend.core.logger import log_event


class ResearchAgent(BaseAgent):
    """Specialist worker for evidence retrieval and citation generation."""

    CAPABILITIES = ("web_search", "evidence_gathering", "citation_generation")

    @property
    def name(self) -> str:
        return "Research"

    def initialize(self) -> None:
        pass

    def estimate_cost(self, task: Task) -> float:
        """Rough token cost estimate based on query length and max_results."""
        query = task.params.get("query", "")
        max_results = int(task.params.get("max_results", 5))
        return round(len(query.split()) * 0.01 + max_results * 0.05, 3)

    def estimate_duration(self, task: Task) -> float:
        """Estimated wall-clock seconds for this research task."""
        return float(task.params.get("max_results", 5)) * 1.5

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        log_event("research_agent_exec", "ResearchAgent executing task")
        query = task.params.get("query") or context.get("user_input") or ""
        max_results = int(task.params.get("max_results", 5))

        if not query:
            return TaskResult(success=False, error="ResearchAgent requires a 'query' param")

        try:
            from backend.core.research_agent import ResearchAgent as ResearchService
            service = ResearchService()
            result = service.research(query, max_results=max_results)
            context.set("research_results", result)
            return TaskResult(success=True, output=result)
        except Exception as e:
            log_event("research_agent_error", str(e))
            # Graceful degradation: return structured placeholder rather than crashing
            return TaskResult(
                success=True,
                output={"query": query, "results": [], "note": "ResearchService unavailable", "error": str(e)},
            )

    def terminate(self, task_id: str) -> None:
        pass
