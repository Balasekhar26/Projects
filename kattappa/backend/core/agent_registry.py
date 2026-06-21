"""Agent Registry for Kattappa's Multi-Agent Mind (Layer 10).

A declarative, typed catalogue of the specialist minds, deterministic
validators, and infrastructure services that the Executive Controller (Layer 9)
can activate. This module is **pure metadata**: it defines *what* each agent is,
*what tools* it may use, *what memory it may touch*, and *its orchestration
priority*. It deliberately does not execute agents, call models, or read/write
memory — and it does not import or modify the existing memory system, so it is
safe to register at import time.

Each agent exposes the five required attributes:

* ``name``               - unique identifier
* ``purpose``            - one-line mission
* ``tools``              - tools the agent is permitted to use
* ``memory_permissions`` - per-layer NONE / READ / READ_WRITE grants
* ``priority``           - orchestration precedence (0-100, higher acts first /
                           carries more authority in consensus)

The integrated architecture distinguishes three *kinds* of agent — LLM
specialists, deterministic validators (which hold veto power), and
infrastructure services — so that the orchestrator can treat them differently.
That distinction is carried on :class:`AgentDefinition.kind` without changing the
uniform five-field contract above.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MemoryLayer(str, Enum):
    """The memory layers an agent may be granted access to.

    These are *names only* — this module never touches the real memory stores.
    """

    SENSORY = "sensory"
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    STRATEGIC = "strategic"
    RELATIONSHIP = "relationship"
    REFLECTION = "reflection"


class MemoryPermission(str, Enum):
    NONE = "none"
    READ = "read"
    READ_WRITE = "read_write"

    @property
    def can_read(self) -> bool:
        return self in (MemoryPermission.READ, MemoryPermission.READ_WRITE)

    @property
    def can_write(self) -> bool:
        return self is MemoryPermission.READ_WRITE


class AgentKind(str, Enum):
    LLM_SPECIALIST = "llm_specialist"            # reasons via a model
    DETERMINISTIC_VALIDATOR = "validator"        # rule-based, may hold veto
    INFRASTRUCTURE = "infrastructure"            # a service, not a reasoner


class ActivationCost(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentDefinition:
    """Immutable description of a single agent."""

    name: str
    purpose: str
    tools: tuple[str, ...]
    memory_permissions: Mapping[MemoryLayer, MemoryPermission]
    priority: int
    kind: AgentKind = AgentKind.LLM_SPECIALIST
    activation_cost: ActivationCost = ActivationCost.MEDIUM
    veto: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Agent name cannot be empty")
        if not self.purpose or not self.purpose.strip():
            raise ValueError(f"Agent {self.name!r} must have a purpose")
        if not 0 <= self.priority <= 100:
            raise ValueError(f"Agent {self.name!r} priority must be 0-100, got {self.priority}")
        # Only deterministic validators may hold veto power.
        if self.veto and self.kind is not AgentKind.DETERMINISTIC_VALIDATOR:
            raise ValueError(f"Agent {self.name!r}: only validators may hold veto power")
        # Freeze the collections so a registered agent cannot be mutated.
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(
            self, "memory_permissions", MappingProxyType(dict(self.memory_permissions))
        )

    # -- memory permission helpers ----------------------------------------
    def permission_for(self, layer: MemoryLayer) -> MemoryPermission:
        return self.memory_permissions.get(layer, MemoryPermission.NONE)

    def can_read(self, layer: MemoryLayer) -> bool:
        return self.permission_for(layer).can_read

    def can_write(self, layer: MemoryLayer) -> bool:
        return self.permission_for(layer).can_write

    def has_tool(self, tool: str) -> bool:
        return tool in self.tools

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "tools": list(self.tools),
            "memory_permissions": {
                layer.value: perm.value for layer, perm in self.memory_permissions.items()
            },
            "priority": self.priority,
            "kind": self.kind.value,
            "activation_cost": self.activation_cost.value,
            "veto": self.veto,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class AgentRegistry:
    """A collection of unique :class:`AgentDefinition` objects."""

    def __init__(self, agents: Iterable[AgentDefinition] | None = None) -> None:
        self._agents: dict[str, AgentDefinition] = {}
        for agent in agents or ():
            self.register(agent)

    def register(self, agent: AgentDefinition) -> AgentDefinition:
        key = agent.name.lower()
        if key in self._agents:
            raise ValueError(f"Agent {agent.name!r} is already registered")
        self._agents[key] = agent
        return agent

    def get(self, name: str) -> AgentDefinition | None:
        return self._agents.get(name.lower())

    def get_or_raise(self, name: str) -> AgentDefinition:
        agent = self.get(name)
        if agent is None:
            raise KeyError(f"No agent registered under {name!r}")
        return agent

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name.lower() in self._agents

    def __len__(self) -> int:
        return len(self._agents)

    def names(self) -> list[str]:
        return [agent.name for agent in self.all()]

    def all(self) -> list[AgentDefinition]:
        """All agents, highest priority first (stable by name on ties)."""
        return sorted(self._agents.values(), key=lambda a: (-a.priority, a.name))

    # -- queries -----------------------------------------------------------
    def by_kind(self, kind: AgentKind) -> list[AgentDefinition]:
        return [a for a in self.all() if a.kind is kind]

    def with_tool(self, tool: str) -> list[AgentDefinition]:
        return [a for a in self.all() if a.has_tool(tool)]

    def with_memory_access(
        self, layer: MemoryLayer, permission: MemoryPermission = MemoryPermission.READ
    ) -> list[AgentDefinition]:
        """Agents that can at least ``permission`` the given layer."""
        if permission is MemoryPermission.READ_WRITE:
            return [a for a in self.all() if a.can_write(layer)]
        return [a for a in self.all() if a.can_read(layer)]

    def writers_of(self, layer: MemoryLayer) -> list[AgentDefinition]:
        return self.with_memory_access(layer, MemoryPermission.READ_WRITE)

    def veto_holders(self) -> list[AgentDefinition]:
        return [a for a in self.all() if a.veto]

    def to_dict(self) -> dict[str, Any]:
        return {"agents": [a.to_dict() for a in self.all()]}


# ---------------------------------------------------------------------------
# Default agents (the eight required by the integrated architecture)
# ---------------------------------------------------------------------------

def _build_default_agents() -> list[AgentDefinition]:
    return [
        AgentDefinition(
            name="Scientist",
            purpose="First-principles validation: physics, mathematics, algorithms, feasibility.",
            tools=("symbolic_solver", "physics_simulator", "web_research"),
            memory_permissions={MemoryLayer.SEMANTIC: MemoryPermission.READ},
            priority=80,
            kind=AgentKind.LLM_SPECIALIST,
            activation_cost=ActivationCost.HIGH,
            description="Answers 'Can this work, and why?' with evidence and a feasibility estimate.",
        ),
        AgentDefinition(
            name="Engineer",
            purpose="System architecture, embedded/hardware, and software system design.",
            tools=("architecture_modeler", "hardware_register_map", "schema_generator"),
            memory_permissions={
                MemoryLayer.WORKING: MemoryPermission.READ_WRITE,
                MemoryLayer.STRATEGIC: MemoryPermission.READ_WRITE,
            },
            priority=75,
            kind=AgentKind.LLM_SPECIALIST,
            activation_cost=ActivationCost.HIGH,
            description="Answers 'How do we build it?' across hardware and software.",
        ),
        AgentDefinition(
            name="Planner",
            purpose="Convert objectives into sequenced roadmaps, dependencies, and critical paths.",
            tools=("critical_path_analyzer", "dag_task_generator"),
            memory_permissions={
                MemoryLayer.STRATEGIC: MemoryPermission.READ_WRITE,
                MemoryLayer.WORKING: MemoryPermission.READ_WRITE,
            },
            priority=60,
            kind=AgentKind.LLM_SPECIALIST,
            activation_cost=ActivationCost.MEDIUM,
            description="Answers 'What should happen next?' as a dependency-aware plan.",
        ),
        AgentDefinition(
            name="Builder",
            purpose="Convert validated designs into implementation artifacts: code, files, tests.",
            tools=("code_generator", "compiler", "linter"),
            memory_permissions={MemoryLayer.WORKING: MemoryPermission.READ},
            priority=55,
            kind=AgentKind.LLM_SPECIALIST,
            activation_cost=ActivationCost.HIGH,
            description="Answers 'How do we implement this?' as concrete artifacts.",
        ),
        AgentDefinition(
            name="Critic",
            purpose="Adversarial review: challenge assumptions, find edge cases and failure modes.",
            tools=("edge_case_analysis", "failure_mode_mapping", "assumption_checker"),
            memory_permissions={MemoryLayer.REFLECTION: MemoryPermission.READ},
            priority=70,
            kind=AgentKind.LLM_SPECIALIST,
            activation_cost=ActivationCost.MEDIUM,
            description="Produces only objections; never writes memory, plans, or routes.",
        ),
        AgentDefinition(
            name="Teacher",
            purpose="Deconstruct complexity into mastery-level explanations and learning paths.",
            tools=("formatter", "mermaid_diagrammer"),
            memory_permissions={MemoryLayer.RELATIONSHIP: MemoryPermission.READ},
            priority=40,
            kind=AgentKind.LLM_SPECIALIST,
            activation_cost=ActivationCost.LOW,
            description="Adapts depth to the user's tracked expertise level.",
        ),
        AgentDefinition(
            name="Poet",
            purpose="Naming, branding, presentation, storytelling, and UI microcopy.",
            tools=("lexical_map", "semantic_similarity"),
            memory_permissions={MemoryLayer.RELATIONSHIP: MemoryPermission.READ},
            priority=30,
            kind=AgentKind.LLM_SPECIALIST,
            activation_cost=ActivationCost.LOW,
            description="Lightweight creative specialist; matches the user's tone.",
        ),
        AgentDefinition(
            name="Security",
            purpose="Threat modelling, vulnerability and privacy review of plans before execution.",
            tools=("static_analysis", "cve_lookup", "threat_model_db"),
            memory_permissions={MemoryLayer.PROCEDURAL: MemoryPermission.READ},
            priority=100,
            kind=AgentKind.DETERMINISTIC_VALIDATOR,
            activation_cost=ActivationCost.MEDIUM,
            veto=True,
            description="Deterministic validator with veto authority over unsafe plans.",
        ),
        AgentDefinition(
            name="Memory Keeper",
            purpose="Single point of memory retrieval, deduplication, promotion, and context assembly.",
            tools=("vector_index", "deduplicator", "context_assembler"),
            memory_permissions={
                MemoryLayer.EPISODIC: MemoryPermission.READ_WRITE,
                MemoryLayer.SEMANTIC: MemoryPermission.READ_WRITE,
                MemoryLayer.STRATEGIC: MemoryPermission.READ_WRITE,
                MemoryLayer.RELATIONSHIP: MemoryPermission.READ_WRITE,
                MemoryLayer.REFLECTION: MemoryPermission.READ_WRITE,
            },
            priority=90,
            kind=AgentKind.INFRASTRUCTURE,
            activation_cost=ActivationCost.LOW,
            description="Infrastructure service, not a reasoner; specialists never query memory directly.",
        ),
    ]


def build_default_registry() -> AgentRegistry:
    """A fresh registry populated with the eight standard agents."""
    return AgentRegistry(_build_default_agents())


# Module-level shared registry.
DEFAULT_REGISTRY = build_default_registry()
