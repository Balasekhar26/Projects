"""Unit tests for Program 16.1 Specialist Worker Agent Foundation.

Tests are structured to validate:
  1. Spawn quota constants and exception are correctly defined
  2. Each specialist agent (Research, Code, Browser, Evaluation) initializes
     and executes without import errors, returning a valid TaskResult
  3. Agents are registered in ORCHESTRATOR_REGISTRY
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from backend.core.orchestrator.base import (
    Task, TaskResult, MAX_CHILDREN_PER_AGENT, MAX_TOTAL_AGENTS,
    SpawnQuotaExceeded, MAX_AGENT_DEPTH,
)
from backend.core.orchestrator.context import SharedContext


# ── 1. Spawn Quota Constants & Exception ────────────────────────────────────

class TestSpawnQuota:
    def test_max_children_per_agent_defined(self):
        assert MAX_CHILDREN_PER_AGENT == 5

    def test_max_total_agents_defined(self):
        assert MAX_TOTAL_AGENTS == 20

    def test_spawn_quota_exceeded_exception_message(self):
        with pytest.raises(SpawnQuotaExceeded) as exc_info:
            raise SpawnQuotaExceeded("active agents=21 exceeds limit=20")
        assert "Spawn quota exceeded" in str(exc_info.value)
        assert "active agents=21" in str(exc_info.value)

    def test_all_depth_and_quota_constants_are_positive(self):
        assert MAX_AGENT_DEPTH > 0
        assert MAX_CHILDREN_PER_AGENT > 0
        assert MAX_TOTAL_AGENTS > MAX_CHILDREN_PER_AGENT


# ── 2. ResearchAgent ────────────────────────────────────────────────────────

class TestResearchAgent:
    def _make_task(self, **params) -> Task:
        return Task(task_id="r-1", agent_name="Research", action="research",
                    params=params, delegation_depth=1)

    def test_name_is_research(self):
        from backend.core.orchestrator.agents.research import ResearchAgent
        assert ResearchAgent().name == "Research"

    def test_capabilities_declared(self):
        from backend.core.orchestrator.agents.research import ResearchAgent
        assert "web_search" in ResearchAgent.CAPABILITIES

    def test_initialize_does_not_raise(self):
        from backend.core.orchestrator.agents.research import ResearchAgent
        ResearchAgent().initialize()

    def test_execute_returns_taskresult_even_when_service_unavailable(self):
        from backend.core.orchestrator.agents.research import ResearchAgent
        agent = ResearchAgent()
        task = self._make_task(query="quantum computing trends", max_results=3)
        ctx = SharedContext({})
        result = agent.execute(task, ctx)
        assert isinstance(result, TaskResult)

    def test_execute_fails_without_query(self):
        from backend.core.orchestrator.agents.research import ResearchAgent
        agent = ResearchAgent()
        task = self._make_task()  # no query
        ctx = SharedContext({})
        result = agent.execute(task, ctx)
        assert result.success is False
        assert "query" in (result.error or "").lower()

    def test_estimate_cost_positive(self):
        from backend.core.orchestrator.agents.research import ResearchAgent
        task = Task(task_id="r-2", agent_name="Research", action="research",
                    params={"query": "AI planning", "max_results": 5})
        cost = ResearchAgent().estimate_cost(task)
        assert cost > 0


# ── 3. CodeAgent ────────────────────────────────────────────────────────────

class TestCodeAgent:
    def _make_task(self, **params) -> Task:
        return Task(task_id="c-1", agent_name="Code", action="implement",
                    params=params, delegation_depth=1)

    def test_name_is_code(self):
        from backend.core.orchestrator.agents.code import CodeAgent
        assert CodeAgent().name == "Code"

    def test_capabilities_declared(self):
        from backend.core.orchestrator.agents.code import CodeAgent
        assert "implementation" in CodeAgent.CAPABILITIES

    def test_execute_returns_taskresult_even_when_service_unavailable(self):
        from backend.core.orchestrator.agents.code import CodeAgent
        task = self._make_task(task_description="Write a binary search function", language="python")
        ctx = SharedContext({})
        result = CodeAgent().execute(task, ctx)
        assert isinstance(result, TaskResult)

    def test_execute_fails_without_task_description(self):
        from backend.core.orchestrator.agents.code import CodeAgent
        task = self._make_task()
        ctx = SharedContext({})
        result = CodeAgent().execute(task, ctx)
        assert result.success is False

    def test_estimate_duration_is_positive(self):
        from backend.core.orchestrator.agents.code import CodeAgent
        task = Task(task_id="c-2", agent_name="Code", action="implement",
                    params={"task_description": "sort algorithm"})
        assert CodeAgent().estimate_duration(task) > 0


# ── 4. BrowserAgent ─────────────────────────────────────────────────────────

class TestBrowserAgent:
    def _make_task(self, **params) -> Task:
        return Task(task_id="b-1", agent_name="Browser", action="navigate",
                    params=params, delegation_depth=1)

    def test_name_is_browser(self):
        from backend.core.orchestrator.agents.browser import BrowserAgent
        assert BrowserAgent().name == "Browser"

    def test_capabilities_declared(self):
        from backend.core.orchestrator.agents.browser import BrowserAgent
        assert "scraping" in BrowserAgent.CAPABILITIES

    def test_execute_returns_taskresult_even_when_service_unavailable(self):
        from backend.core.orchestrator.agents.browser import BrowserAgent
        task = self._make_task(url="https://example.com", action="navigate")
        ctx = SharedContext({})
        result = BrowserAgent().execute(task, ctx)
        assert isinstance(result, TaskResult)

    def test_execute_fails_without_url(self):
        from backend.core.orchestrator.agents.browser import BrowserAgent
        task = self._make_task()  # no url
        ctx = SharedContext({})
        result = BrowserAgent().execute(task, ctx)
        assert result.success is False


# ── 5. EvaluationAgent ──────────────────────────────────────────────────────

class TestEvaluationAgent:
    def _make_task(self, **params) -> Task:
        return Task(task_id="e-1", agent_name="Evaluation", action="score",
                    params=params, delegation_depth=1)

    def test_name_is_evaluation(self):
        from backend.core.orchestrator.agents.evaluation import EvaluationAgent
        assert EvaluationAgent().name == "Evaluation"

    def test_capabilities_declared(self):
        from backend.core.orchestrator.agents.evaluation import EvaluationAgent
        assert "scorecard_generation" in EvaluationAgent.CAPABILITIES

    def test_execute_returns_taskresult_even_when_service_unavailable(self):
        from backend.core.orchestrator.agents.evaluation import EvaluationAgent
        task = self._make_task(
            plan_id="p-42",
            actual_metrics={"duration": 12.0, "cost": 0.5},
            predicted_metrics={"duration": 10.0, "cost": 0.4},
            planner_version="HTN-v1.1",
        )
        ctx = SharedContext({})
        result = EvaluationAgent().execute(task, ctx)
        assert isinstance(result, TaskResult)

    def test_estimate_cost_is_minimal(self):
        from backend.core.orchestrator.agents.evaluation import EvaluationAgent
        task = Task(task_id="e-2", agent_name="Evaluation", action="score", params={})
        assert EvaluationAgent().estimate_cost(task) < 0.10


# ── 6. Registry contains all 11 agents ─────────────────────────────────────

class TestOrchestratorRegistry:
    def test_all_specialist_agents_registered(self):
        from backend.core.orchestrator.registry import ORCHESTRATOR_REGISTRY
        registered = {a.name for a in ORCHESTRATOR_REGISTRY.all()}
        for expected in ("Research", "Code", "Browser", "Evaluation"):
            assert expected in registered, f"'{expected}' not found in registry"

    def test_original_agents_still_registered(self):
        from backend.core.orchestrator.registry import ORCHESTRATOR_REGISTRY
        registered = {a.name for a in ORCHESTRATOR_REGISTRY.all()}
        for expected in ("Executive", "Planner", "Memory Keeper",
                         "Tool Executor", "Reasoning", "Reflection", "Scientist"):
            assert expected in registered, f"'{expected}' not found in registry"
