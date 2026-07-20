from __future__ import annotations
from typing import Dict
from backend.core.orchestrator.base import BaseAgent

class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        
        # Defer imports to break circular dependencies during boot
        from backend.core.orchestrator.agents.executive import ExecutiveAgent
        from backend.core.orchestrator.agents.planner import PlannerAgent
        from backend.core.orchestrator.agents.memory import MemoryKeeperAgent
        from backend.core.orchestrator.agents.tool_exec import ToolExecutorAgent
        from backend.core.orchestrator.agents.reasoning import ReasoningAgent
        from backend.core.orchestrator.agents.reflection import ReflectionAgent
        from backend.core.orchestrator.agents.scientist import ScientistAgent
        from backend.core.orchestrator.agents.research import ResearchAgent
        from backend.core.orchestrator.agents.code import CodeAgent
        from backend.core.orchestrator.agents.browser import BrowserAgent
        from backend.core.orchestrator.agents.evaluation import EvaluationAgent

        self.register(ExecutiveAgent())
        self.register(PlannerAgent())
        self.register(MemoryKeeperAgent())
        self.register(ToolExecutorAgent())
        self.register(ReasoningAgent())
        self.register(ReflectionAgent())
        self.register(ScientistAgent())
        self.register(ResearchAgent())
        self.register(CodeAgent())
        self.register(BrowserAgent())
        self.register(EvaluationAgent())

    def register(self, agent: BaseAgent) -> None:
        name_key = agent.name.lower()
        if name_key in self._agents:
            raise ValueError(f"Agent {agent.name!r} is already registered in the orchestrator registry")
        self._agents[name_key] = agent

    def get(self, name: str) -> BaseAgent | None:
        self._ensure_initialized()
        return self._agents.get(name.lower())

    def get_or_raise(self, name: str) -> BaseAgent:
        self._ensure_initialized()
        agent = self.get(name)
        if agent is None:
            raise KeyError(f"No active agent registered in the orchestrator registry under {name!r}")
        return agent

    def all(self) -> list[BaseAgent]:
        self._ensure_initialized()
        return list(self._agents.values())

ORCHESTRATOR_REGISTRY = AgentRegistry()
