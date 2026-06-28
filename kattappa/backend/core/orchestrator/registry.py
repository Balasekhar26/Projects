from __future__ import annotations
from typing import Dict
from backend.core.orchestrator.base import BaseAgent

class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        name_key = agent.name.lower()
        if name_key in self._agents:
            raise ValueError(f"Agent {agent.name!r} is already registered in the orchestrator registry")
        self._agents[name_key] = agent

    def get(self, name: str) -> BaseAgent | None:
        return self._agents.get(name.lower())

    def get_or_raise(self, name: str) -> BaseAgent:
        agent = self.get(name)
        if agent is None:
            raise KeyError(f"No active agent registered in the orchestrator registry under {name!r}")
        return agent

    def all(self) -> list[BaseAgent]:
        return list(self._agents.values())

ORCHESTRATOR_REGISTRY = AgentRegistry()

# Initialize and register the core cognitive agents
from backend.core.orchestrator.agents.executive import ExecutiveAgent
from backend.core.orchestrator.agents.planner import PlannerAgent
from backend.core.orchestrator.agents.memory import MemoryKeeperAgent
from backend.core.orchestrator.agents.tool_exec import ToolExecutorAgent
from backend.core.orchestrator.agents.reasoning import ReasoningAgent
from backend.core.orchestrator.agents.reflection import ReflectionAgent

ORCHESTRATOR_REGISTRY.register(ExecutiveAgent())
ORCHESTRATOR_REGISTRY.register(PlannerAgent())
ORCHESTRATOR_REGISTRY.register(MemoryKeeperAgent())
ORCHESTRATOR_REGISTRY.register(ToolExecutorAgent())
ORCHESTRATOR_REGISTRY.register(ReasoningAgent())
ORCHESTRATOR_REGISTRY.register(ReflectionAgent())
