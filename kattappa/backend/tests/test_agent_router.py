from __future__ import annotations

import json

import pytest

from backend.core.agent_router import (
    ACTIVATION_MATRIX,
    DEFAULT_ROUTER,
    AgentRouter,
    BudgetManager,
    IntentCategory,
    RouterMode,
    classify_intent,
    is_security_sensitive,
)


@pytest.fixture
def router() -> AgentRouter:
    return AgentRouter()


# ---------------------------------------------------------------------------
# Modes & budgets
# ---------------------------------------------------------------------------

def test_mode_caps_and_budgets():
    assert RouterMode.ECO.max_agents == 1
    assert RouterMode.BALANCED.max_agents == 3
    assert RouterMode.BEAST.max_agents == 5
    assert RouterMode.ECO.token_budget == 1500
    assert RouterMode.BALANCED.token_budget == 6000
    assert RouterMode.BEAST.token_budget == 20000


def test_mode_coerce():
    assert RouterMode.coerce("beast") is RouterMode.BEAST
    assert RouterMode.coerce(RouterMode.ECO) is RouterMode.ECO
    with pytest.raises(ValueError):
        RouterMode.coerce("ludicrous")


def test_budget_split():
    alloc = BudgetManager.allocate(RouterMode.BEAST, 4)
    assert alloc.total_token_budget == 20000
    assert alloc.per_agent_token_budget == 5000
    assert BudgetManager.allocate(RouterMode.ECO, 0).per_agent_token_budget == 1500


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

def test_intent_classification():
    assert classify_intent("Design an RF mesh node topology for DEWS") is IntentCategory.ARCHITECTURE
    assert classify_intent("Implement a function to parse logs") is IntentCategory.CODING
    assert classify_intent("Explain Ohm's law") is IntentCategory.TEACHING
    assert classify_intent("Give my project a cool name") is IntentCategory.NAMING
    assert classify_intent("What did I work on last week") is IntentCategory.MEMORY
    assert classify_intent("Prove this algorithm's feasibility") is IntentCategory.RESEARCH
    assert classify_intent("hello there friend") is IntentCategory.GENERAL


def test_empty_prompt_is_general():
    assert classify_intent("   ") is IntentCategory.GENERAL


def test_activation_matrix_covers_all_intents():
    for intent in IntentCategory:
        assert intent in ACTIVATION_MATRIX


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def test_research_routes_to_scientist_and_critic(router):
    decision = router.route("Prove the feasibility of this approach", mode=RouterMode.BEAST)
    assert decision.intent is IntentCategory.RESEARCH
    assert set(decision.agents) == {"Scientist", "Critic"}


def test_architecture_routes_full_set_in_beast(router):
    decision = router.route("Design an RF mesh node topology", mode=RouterMode.BEAST)
    assert decision.intent is IntentCategory.ARCHITECTURE
    assert set(decision.agents) == {"Scientist", "Engineer", "Critic", "Planner", "Security"}
    # Priority ordering: Security(100) first, Critic before Planner.
    assert decision.agents[0] == "Security"
    assert decision.agents.index("Critic") < decision.agents.index("Planner")


def test_teaching_single_agent(router):
    decision = router.route("Explain how a transformer works", mode=RouterMode.BALANCED)
    assert decision.agents == ("Teacher",)
    assert decision.estimated_cost.value == "low"


def test_naming_routes_to_poet(router):
    decision = router.route("Suggest a cool name for the project", mode=RouterMode.ECO)
    assert decision.agents == ("Poet",)


def test_memory_routes_to_memory_keeper(router):
    decision = router.route("recall what we decided about the schema", mode=RouterMode.BALANCED)
    assert decision.agents == ("Memory Keeper",)


# ---------------------------------------------------------------------------
# Budget clamping
# ---------------------------------------------------------------------------

def test_balanced_clamps_architecture_to_three_by_priority(router):
    decision = router.route("Design an embedded system architecture", mode=RouterMode.BALANCED)
    assert len(decision.agents) == 3
    # Highest-priority three survive: Security(100), Scientist(80), Engineer(75).
    assert set(decision.agents) == {"Security", "Scientist", "Engineer"}
    assert set(decision.dropped_agents) == {"Critic", "Planner"}


def test_eco_clamps_to_single_highest_priority(router):
    decision = router.route("Design an embedded system architecture", mode=RouterMode.ECO)
    assert len(decision.agents) == 1
    assert decision.agents == ("Security",)


def test_per_agent_budget_scales_with_count(router):
    decision = router.route("Design an RF mesh topology", mode=RouterMode.BEAST)
    assert decision.budget.agent_count == len(decision.agents)
    assert decision.budget.per_agent_token_budget == 20000 // len(decision.agents)


# ---------------------------------------------------------------------------
# Security mandatory activation
# ---------------------------------------------------------------------------

def test_security_forced_on_sensitive_prompt(router):
    # Coding intent normally includes Security, but a teaching-style prompt that
    # touches credentials must still pull Security in.
    decision = router.route("Explain how to store a password securely", mode=RouterMode.BEAST)
    assert decision.security_mandatory is True
    assert "Security" in decision.agents


def test_is_security_sensitive_detection():
    assert is_security_sensitive("deploy to production with the api token")
    assert not is_security_sensitive("write a haiku about the ocean")


# ---------------------------------------------------------------------------
# Determinism & safety
# ---------------------------------------------------------------------------

def test_routing_is_deterministic(router):
    prompt = "Design an RF mesh node topology for DEWS"
    d1 = router.route(prompt, mode=RouterMode.BEAST)
    d2 = router.route(prompt, mode=RouterMode.BEAST)
    assert d1.to_dict() == d2.to_dict()


def test_router_is_sole_activator():
    # Hard safety rule: agents cannot activate other agents. Agent definitions
    # expose no activation capability — only the router produces an agent set.
    from backend.core.agent_registry import DEFAULT_REGISTRY
    for agent in DEFAULT_REGISTRY.all():
        assert not hasattr(agent, "activate")
        assert not hasattr(agent, "route")


def test_decision_is_json_serialisable(router):
    decision = router.route("Design an RF mesh node", mode=RouterMode.BALANCED)
    payload = json.dumps(decision.to_dict())
    data = json.loads(payload)
    assert data["intent"] == "architecture"
    assert "agents" in data and "budget" in data


def test_default_router_works():
    decision = DEFAULT_ROUTER.route("Explain recursion")
    assert decision.mode is RouterMode.BALANCED  # default mode
    assert decision.agents == ("Teacher",)
