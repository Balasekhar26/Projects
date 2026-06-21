from __future__ import annotations

import json

import pytest

from backend.core.agent_registry import (
    DEFAULT_REGISTRY,
    AgentDefinition,
    AgentKind,
    AgentRegistry,
    MemoryLayer,
    MemoryPermission,
    build_default_registry,
)


EXPECTED_AGENTS = {
    "Scientist", "Engineer", "Planner", "Builder",
    "Teacher", "Poet", "Security", "Memory Keeper", "Critic",
}


@pytest.fixture
def registry() -> AgentRegistry:
    return build_default_registry()


# ---------------------------------------------------------------------------
# All eight required agents exist with the required fields
# ---------------------------------------------------------------------------

def test_all_agents_registered(registry):
    assert len(registry) == 9
    assert set(registry.names()) == EXPECTED_AGENTS


def test_critic_is_read_only_specialist(registry):
    critic = registry.get_or_raise("Critic")
    assert critic.kind is AgentKind.LLM_SPECIALIST
    assert critic.priority == 70
    assert critic.veto is False
    assert critic.can_read(MemoryLayer.REFLECTION)
    # Critic must never hold write access to any layer.
    for layer in MemoryLayer:
        assert not critic.can_write(layer), layer
    assert critic.has_tool("assumption_checker")


def test_critic_executes_before_planner(registry):
    names = registry.names()  # priority-ordered
    assert names.index("Critic") < names.index("Planner")


def test_every_agent_has_required_fields(registry):
    for agent in registry.all():
        assert isinstance(agent.name, str) and agent.name.strip()
        assert isinstance(agent.purpose, str) and agent.purpose.strip()
        assert isinstance(agent.tools, tuple) and len(agent.tools) >= 1
        assert isinstance(agent.memory_permissions, dict) or hasattr(agent.memory_permissions, "get")
        assert 0 <= agent.priority <= 100


def test_priorities_are_unique(registry):
    priorities = [a.priority for a in registry.all()]
    assert len(priorities) == len(set(priorities))


def test_all_sorted_by_priority_descending(registry):
    priorities = [a.priority for a in registry.all()]
    assert priorities == sorted(priorities, reverse=True)
    # Security (veto, mandatory) is the highest-priority agent.
    assert registry.all()[0].name == "Security"


# ---------------------------------------------------------------------------
# Per-agent memory permissions match the architecture
# ---------------------------------------------------------------------------

def test_scientist_reads_semantic_only(registry):
    sci = registry.get_or_raise("Scientist")
    assert sci.can_read(MemoryLayer.SEMANTIC)
    assert not sci.can_write(MemoryLayer.SEMANTIC)
    assert not sci.can_read(MemoryLayer.WORKING)


def test_engineer_read_write_working_and_strategic(registry):
    eng = registry.get_or_raise("Engineer")
    assert eng.can_write(MemoryLayer.WORKING)
    assert eng.can_write(MemoryLayer.STRATEGIC)
    assert not eng.can_read(MemoryLayer.RELATIONSHIP)


def test_builder_reads_working_only(registry):
    builder = registry.get_or_raise("Builder")
    assert builder.can_read(MemoryLayer.WORKING)
    assert not builder.can_write(MemoryLayer.WORKING)


def test_memory_keeper_has_broad_read_write(registry):
    mk = registry.get_or_raise("Memory Keeper")
    for layer in (
        MemoryLayer.EPISODIC, MemoryLayer.SEMANTIC, MemoryLayer.STRATEGIC,
        MemoryLayer.RELATIONSHIP, MemoryLayer.REFLECTION,
    ):
        assert mk.can_write(layer), layer
    assert mk.kind is AgentKind.INFRASTRUCTURE


def test_teacher_and_poet_read_relationship(registry):
    for name in ("Teacher", "Poet"):
        agent = registry.get_or_raise(name)
        assert agent.can_read(MemoryLayer.RELATIONSHIP)
        assert not agent.can_write(MemoryLayer.RELATIONSHIP)


def test_unlisted_layer_defaults_to_none(registry):
    sci = registry.get_or_raise("Scientist")
    assert sci.permission_for(MemoryLayer.REFLECTION) is MemoryPermission.NONE


# ---------------------------------------------------------------------------
# Kinds & veto
# ---------------------------------------------------------------------------

def test_security_is_validator_with_veto(registry):
    sec = registry.get_or_raise("Security")
    assert sec.kind is AgentKind.DETERMINISTIC_VALIDATOR
    assert sec.veto is True
    assert registry.veto_holders() == [sec]


def test_only_security_holds_veto(registry):
    for agent in registry.all():
        if agent.name != "Security":
            assert agent.veto is False


def test_llm_specialists_count(registry):
    specialists = registry.by_kind(AgentKind.LLM_SPECIALIST)
    assert {a.name for a in specialists} == {
        "Scientist", "Engineer", "Planner", "Builder", "Teacher", "Poet", "Critic"
    }


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def test_with_memory_access_read(registry):
    readers = {a.name for a in registry.with_memory_access(MemoryLayer.SEMANTIC)}
    # Scientist (read) and Memory Keeper (read_write) can both read semantic.
    assert "Scientist" in readers
    assert "Memory Keeper" in readers


def test_writers_of_strategic(registry):
    writers = {a.name for a in registry.writers_of(MemoryLayer.STRATEGIC)}
    assert writers == {"Engineer", "Planner", "Memory Keeper"}


def test_with_tool(registry):
    assert {a.name for a in registry.with_tool("compiler")} == {"Builder"}
    assert registry.with_tool("nonexistent_tool") == []


# ---------------------------------------------------------------------------
# Registry mechanics
# ---------------------------------------------------------------------------

def test_get_is_case_insensitive(registry):
    assert registry.get("scientist") is registry.get("SCIENTIST")
    assert "engineer" in registry


def test_get_or_raise_missing(registry):
    with pytest.raises(KeyError):
        registry.get_or_raise("Nonexistent")


def test_duplicate_registration_rejected(registry):
    dup = AgentDefinition(
        name="Scientist",
        purpose="duplicate",
        tools=("x",),
        memory_permissions={},
        priority=10,
    )
    with pytest.raises(ValueError):
        registry.register(dup)


def test_to_dict_is_json_serialisable(registry):
    payload = json.dumps(registry.to_dict())
    data = json.loads(payload)
    assert len(data["agents"]) == 9
    first = data["agents"][0]
    assert set(first) >= {"name", "purpose", "tools", "memory_permissions", "priority"}


# ---------------------------------------------------------------------------
# Validation & immutability
# ---------------------------------------------------------------------------

def test_priority_out_of_range_rejected():
    with pytest.raises(ValueError):
        AgentDefinition("X", "p", ("t",), {}, priority=150)


def test_empty_name_rejected():
    with pytest.raises(ValueError):
        AgentDefinition("  ", "p", ("t",), {}, priority=10)


def test_non_validator_cannot_hold_veto():
    with pytest.raises(ValueError):
        AgentDefinition(
            "X", "p", ("t",), {}, priority=10,
            kind=AgentKind.LLM_SPECIALIST, veto=True,
        )


def test_memory_permissions_are_immutable(registry):
    sci = registry.get_or_raise("Scientist")
    with pytest.raises(TypeError):
        sci.memory_permissions[MemoryLayer.WORKING] = MemoryPermission.READ_WRITE  # type: ignore[index]


def test_tools_coerced_to_tuple():
    agent = AgentDefinition("X", "p", ["a", "b"], {}, priority=10)  # list in, tuple out
    assert isinstance(agent.tools, tuple)
    assert agent.has_tool("a")


def test_default_registry_matches_fresh_build():
    assert set(DEFAULT_REGISTRY.names()) == EXPECTED_AGENTS


# ---------------------------------------------------------------------------
# Constraint: the registry must not touch the existing memory system
# ---------------------------------------------------------------------------

def test_registry_does_not_import_memory_system():
    import backend.core.agent_registry as reg_mod
    import inspect

    source = inspect.getsource(reg_mod)
    assert "human_memory" not in source
    assert "import sqlite3" not in source
