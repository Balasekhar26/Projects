"""Deterministic Agent Router (Layer 9, Router v1).

The Router is Kattappa's brainstem: a small, **deterministic** decision layer
that maps an incoming prompt to the minimum set of specialist agents required to
answer it, within the active hardware/cost mode. It contains no LLM call, no
randomness, and no I/O — the same prompt and mode always yield the same routing
decision.

It bundles three concerns from the integrated architecture:

* **Activation Matrix** - intent category -> ordered agent set.
* **Budget Manager**    - mode -> hard agent cap and token budget, split per agent.
* **Router**            - classify intent, apply mandatory Security, clamp to the
                          mode's cap by priority, and estimate cost.

Hard safety rule (enforced structurally): only the Router produces an activation
set. Agents have no API to activate other agents, so recursive
agent -> agent activation loops cannot occur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.core.agent_registry import (
    DEFAULT_REGISTRY,
    ActivationCost,
    AgentRegistry,
)


# ---------------------------------------------------------------------------
# Modes & budgets
# ---------------------------------------------------------------------------

class RouterMode(str, Enum):
    """Hardware/cost tier. Sets the hard agent cap and token budget."""

    ECO = "ECO"
    BALANCED = "BALANCED"
    BEAST = "BEAST"

    @property
    def max_agents(self) -> int:
        return {RouterMode.ECO: 1, RouterMode.BALANCED: 3, RouterMode.BEAST: 6}[self]

    @property
    def token_budget(self) -> int:
        return {RouterMode.ECO: 1500, RouterMode.BALANCED: 6000, RouterMode.BEAST: 20000}[self]

    @classmethod
    def coerce(cls, value: "RouterMode | str") -> "RouterMode":
        if isinstance(value, RouterMode):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError as exc:
            raise ValueError(f"Unknown router mode {value!r}") from exc


@dataclass(frozen=True)
class BudgetAllocation:
    mode: RouterMode
    agent_count: int
    total_token_budget: int
    per_agent_token_budget: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "agent_count": self.agent_count,
            "total_token_budget": self.total_token_budget,
            "per_agent_token_budget": self.per_agent_token_budget,
        }


class BudgetManager:
    """Splits a mode's token budget across the activated agents."""

    @staticmethod
    def allocate(mode: RouterMode, agent_count: int) -> BudgetAllocation:
        total = mode.token_budget
        per_agent = total // agent_count if agent_count > 0 else total
        return BudgetAllocation(mode, agent_count, total, per_agent)


# ---------------------------------------------------------------------------
# Intent classification & activation matrix
# ---------------------------------------------------------------------------

class IntentCategory(str, Enum):
    RESEARCH = "research"
    ARCHITECTURE = "architecture"
    CODING = "coding"
    TEACHING = "teaching"
    NAMING = "naming"
    MEMORY = "memory"
    GENERAL = "general"


# Intent -> ordered agent activation set (from the Router v1 spec).
ACTIVATION_MATRIX: dict[IntentCategory, tuple[str, ...]] = {
    IntentCategory.RESEARCH: ("Scientist", "Critic"),
    IntentCategory.ARCHITECTURE: ("Scientist", "Engineer", "Critic", "Planner", "Security"),
    IntentCategory.CODING: ("Engineer", "Builder", "Security"),
    IntentCategory.TEACHING: ("Teacher",),
    IntentCategory.NAMING: ("Poet",),
    IntentCategory.MEMORY: ("Memory Keeper",),
    IntentCategory.GENERAL: ("Teacher",),
}

# Keyword signals. Checked in a fixed precedence order so classification is
# deterministic when a prompt matches more than one category.
_INTENT_KEYWORDS: tuple[tuple[IntentCategory, tuple[str, ...]], ...] = (
    (IntentCategory.NAMING, ("name", "naming", "branding", "slogan", "tagline",
                             "call it", "title for", "logo")),
    (IntentCategory.MEMORY, ("remember", "recall", "what did i", "do you remember",
                             "forget", "memorize")),
    (IntentCategory.ARCHITECTURE, ("architecture", "design a", "design an", "system design",
                                   "topology", "mesh", "infrastructure", "schematic",
                                   "pinout", "rf ", "embedded system", "microservice")),
    (IntentCategory.CODING, ("code", "implement", "write a function", "bug", "refactor",
                             "script", "compile", "api endpoint", "unit test", "debug")),
    (IntentCategory.RESEARCH, ("research", "feasibility", "will this work", "prove",
                               "derive", "hypothesis", "physics", "equation",
                               "first principles", "analyze")),
    (IntentCategory.TEACHING, ("explain", "teach", "what is", "how does", "learn",
                               "tutorial", "understand", "walk me through")),
)

# Security-sensitive cues force Security to activate regardless of intent.
_SECURITY_SENSITIVE = (
    "auth", "login", "password", "credential", "token", "network", "deploy",
    "file", "delete", "payment", "exec", "shell", "privilege", "encryption",
    "firewall", "secret", "permission",
)


def _normalise(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt.lower()).strip()


def classify_intent(prompt: str) -> IntentCategory:
    text = _normalise(prompt)
    if not text:
        return IntentCategory.GENERAL
    for category, keywords in _INTENT_KEYWORDS:
        if any(kw in text for kw in keywords):
            return category
    return IntentCategory.GENERAL


def is_security_sensitive(prompt: str) -> bool:
    text = _normalise(prompt)
    return any(re.search(rf"\b{re.escape(kw)}", text) for kw in _SECURITY_SENSITIVE)


# ---------------------------------------------------------------------------
# Routing decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RoutingDecision:
    prompt: str
    intent: IntentCategory
    mode: RouterMode
    agents: tuple[str, ...]            # priority-ordered, clamped to the mode cap
    dropped_agents: tuple[str, ...]    # requested but cut by the budget cap
    security_mandatory: bool
    estimated_cost: ActivationCost
    budget: BudgetAllocation
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "intent": self.intent.value,
            "mode": self.mode.value,
            "agents": list(self.agents),
            "dropped_agents": list(self.dropped_agents),
            "security_mandatory": self.security_mandatory,
            "estimated_cost": self.estimated_cost.value,
            "budget": self.budget.to_dict(),
            "reasons": list(self.reasons),
        }


_COST_RANK = {ActivationCost.LOW: 0, ActivationCost.MEDIUM: 1, ActivationCost.HIGH: 2}
_RANK_COST = {v: k for k, v in _COST_RANK.items()}


class AgentRouter:
    """Deterministic prompt -> agent activation router."""

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self._registry = registry or DEFAULT_REGISTRY

    def route(self, prompt: str, mode: RouterMode | str = RouterMode.BALANCED) -> RoutingDecision:
        mode = RouterMode.coerce(mode)
        reasons: list[str] = []

        intent = classify_intent(prompt)
        reasons.append(f"intent classified as {intent.value}")

        requested = list(ACTIVATION_MATRIX[intent])

        security_sensitive = is_security_sensitive(prompt)
        if security_sensitive and "Security" not in requested:
            requested.append("Security")
            reasons.append("security-sensitive prompt: Security activated")

        # Resolve to registered agents; silently skip anything unknown.
        resolved = [a for name in requested if (a := self._registry.get(name)) is not None]
        # Order by orchestration priority (higher first) so clamping keeps the
        # most authoritative agents — and Security (100) is never dropped.
        resolved.sort(key=lambda a: (-a.priority, a.name))

        cap = mode.max_agents
        kept = resolved[:cap]
        dropped = resolved[cap:]
        if dropped:
            reasons.append(
                f"{mode.value} cap={cap}: kept {[a.name for a in kept]}, "
                f"dropped {[a.name for a in dropped]}"
            )

        budget = BudgetManager.allocate(mode, len(kept))
        cost = self._estimate_cost(kept)

        return RoutingDecision(
            prompt=prompt,
            intent=intent,
            mode=mode,
            agents=tuple(a.name for a in kept),
            dropped_agents=tuple(a.name for a in dropped),
            security_mandatory=security_sensitive,
            estimated_cost=cost,
            budget=budget,
            reasons=tuple(reasons),
        )

    @staticmethod
    def _estimate_cost(agents: list) -> ActivationCost:
        if not agents:
            return ActivationCost.LOW
        peak = max(_COST_RANK[a.activation_cost] for a in agents)
        # Many agents raise the effective cost even if each is individually cheap.
        if len(agents) >= 4:
            peak = max(peak, _COST_RANK[ActivationCost.HIGH])
        elif len(agents) >= 2:
            peak = max(peak, _COST_RANK[ActivationCost.MEDIUM])
        return _RANK_COST[peak]


# Module-level shared router over the default registry.
DEFAULT_ROUTER = AgentRouter()
