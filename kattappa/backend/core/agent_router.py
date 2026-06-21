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
        # BEAST caps at 5: Scientist, Engineer, Critic, Planner, Security cover the
        # heaviest design tasks; beyond that, opinions start to duplicate.
        return {RouterMode.ECO: 1, RouterMode.BALANCED: 3, RouterMode.BEAST: 5}[self]

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
    DEBUGGING = "debugging"
    DOCUMENTATION = "documentation"
    PRESENTATION = "presentation"
    ANALYSIS = "analysis"
    TEACHING = "teaching"
    NAMING = "naming"
    MEMORY = "memory"
    GENERAL = "general"


# Intent -> ordered agent activation set.
ACTIVATION_MATRIX: dict[IntentCategory, tuple[str, ...]] = {
    IntentCategory.RESEARCH: ("Scientist", "Critic"),
    IntentCategory.ARCHITECTURE: ("Scientist", "Engineer", "Critic", "Planner", "Security"),
    IntentCategory.CODING: ("Engineer", "Builder", "Security"),
    IntentCategory.DEBUGGING: ("Engineer", "Builder", "Critic"),
    IntentCategory.DOCUMENTATION: ("Teacher",),
    IntentCategory.PRESENTATION: ("Poet",),
    IntentCategory.ANALYSIS: ("Scientist", "Critic"),
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
    (IntentCategory.PRESENTATION, ("presentation", "slides", "slide deck", "pitch deck",
                                   "keynote")),
    (IntentCategory.DOCUMENTATION, ("documentation", "readme", "docstring", "write docs",
                                    "api docs", "document the")),
    (IntentCategory.ARCHITECTURE, ("architecture", "design a", "design an", "system design",
                                   "topology", "mesh", "infrastructure", "schematic",
                                   "pinout", "rf ", "embedded system", "microservice")),
    (IntentCategory.DEBUGGING, ("debug", "stack trace", "traceback", "not working",
                                "why is this failing", "exception", "fix the bug")),
    (IntentCategory.CODING, ("code", "implement", "write a function", "refactor",
                             "script", "compile", "api endpoint", "unit test")),
    (IntentCategory.ANALYSIS, ("analysis", "analyze", "compare", "evaluate", "trade-off",
                               "tradeoff", "assessment")),
    (IntentCategory.RESEARCH, ("research", "feasibility", "will this work", "prove",
                               "derive", "hypothesis", "physics", "equation",
                               "first principles")),
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
# Confidence scoring (Router v2)
#
# CRITICAL: routing confidence is NOT correctness confidence. A score of 0.92
# means "the Router is 0.92 confident this is the right specialist", never "the
# answer is 92% correct". The two must never be conflated.
# ---------------------------------------------------------------------------

_MATCH_WEIGHT = 0.15  # deterministic score per keyword match


class ConfidenceTier(str, Enum):
    HIGH = "high"      # >= 0.80 : route directly to the primary agent
    MEDIUM = "medium"  # 0.50-0.79 : route primary, keep a secondary candidate
    LOW = "low"        # < 0.50 : ambiguous -> escalate to multi-agent (top 2)

    @classmethod
    def classify(cls, score: float) -> "ConfidenceTier":
        if score >= 0.80:
            return cls.HIGH
        if score >= 0.50:
            return cls.MEDIUM
        return cls.LOW


# Per-agent capability schemas used for confidence scoring.
AGENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Scientist": ("physics", "quantum", "energy", "voltage", "current", "rf",
                  "frequency", "propagation", "wave", "feasibility", "equation",
                  "theorem", "probability", "signal", "simulation"),
    "Engineer": ("architecture", "design", "system", "topology", "firmware",
                 "hardware", "circuit", "embedded", "schematic", "pinout",
                 "interface", "infrastructure", "pcb", "sensor", "mesh",
                 "network", "build", "microcontroller"),
    "Builder": ("code", "implement", "function", "script", "compile", "generate",
                "refactor", "class", "module", "test suite"),
    "Teacher": ("explain", "teach", "learn", "tutorial", "understand", "concept",
                "basics", "documentation", "readme", "docstring"),
    "Poet": ("name", "naming", "brand", "branding", "slogan", "tagline", "story",
             "copy", "presentation", "slides", "pitch", "creative", "theme"),
    "Planner": ("plan", "roadmap", "milestone", "schedule", "priority",
                "dependency", "timeline", "backlog", "sprint", "sequence"),
    "Critic": ("review", "critique", "flaw", "edge case", "risk", "weakness",
               "assumption", "failure", "analyze", "analysis", "evaluate"),
    "Security": ("login", "auth", "authentication", "password", "credential",
                 "security", "encryption", "vulnerability", "firewall", "token",
                 "privilege", "threat"),
    "Memory Keeper": ("remember", "recall", "memory", "forget", "history", "remind"),
}


@dataclass(frozen=True)
class AgentScore:
    agent: str
    score: float
    matches: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"agent": self.agent, "score": round(self.score, 4), "matches": list(self.matches)}


def _routing_confidence(ranked_scores: list[float]) -> float:
    """Routing certainty from the ranked raw agent scores.

    A clear winner (large margin / uncontested) yields high confidence; a
    contested field yields low confidence and triggers multi-agent escalation.
    """
    if not ranked_scores or ranked_scores[0] <= 0.0:
        return 0.0
    top = ranked_scores[0]
    second = ranked_scores[1] if len(ranked_scores) > 1 else 0.0
    margin = top - second
    uncontested_bonus = 0.4 if second == 0.0 else 0.0
    return round(min(1.0, top + margin + uncontested_bonus), 4)


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
    # Router v2 confidence scoring (advisory routing metadata).
    selected_agent: str | None = None
    routing_confidence: float = 0.0
    confidence_tier: ConfidenceTier = ConfidenceTier.LOW
    agent_scores: tuple[AgentScore, ...] = ()
    routing_mode: str = "single"        # "single" | "multi_agent"
    escalated: bool = False
    secondary_agent: str | None = None

    @property
    def top_agents(self) -> tuple[str, ...]:
        """The agents to actually engage given the confidence tier."""
        if self.escalated:
            return tuple(s.agent for s in self.agent_scores[:2])
        if self.selected_agent is None:
            return ()
        return (self.selected_agent,)

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
            "selected_agent": self.selected_agent,
            # NOTE: routing confidence != correctness confidence.
            "routing_confidence": self.routing_confidence,
            "confidence_tier": self.confidence_tier.value,
            "agent_scores": [s.to_dict() for s in self.agent_scores],
            "routing_mode": self.routing_mode,
            "escalated": self.escalated,
            "secondary_agent": self.secondary_agent,
            "top_agents": list(self.top_agents),
        }


_COST_RANK = {ActivationCost.LOW: 0, ActivationCost.MEDIUM: 1, ActivationCost.HIGH: 2}
_RANK_COST = {v: k for k, v in _COST_RANK.items()}


class AgentRouter:
    """Deterministic prompt -> agent activation router."""

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self._registry = registry or DEFAULT_REGISTRY

    def score_agents(self, prompt: str) -> list[AgentScore]:
        """Deterministically score each specialist against the prompt.

        Ranked highest-first; ties broken by registry priority then name.
        """
        text = _normalise(prompt)
        scores: list[AgentScore] = []
        for agent, keywords in AGENT_KEYWORDS.items():
            matches = tuple(kw for kw in keywords if re.search(rf"\b{re.escape(kw)}", text))
            if matches:
                scores.append(AgentScore(agent, min(1.0, _MATCH_WEIGHT * len(matches)), matches))

        def priority(name: str) -> int:
            agent = self._registry.get(name)
            return agent.priority if agent else 0

        scores.sort(key=lambda s: (-s.score, -priority(s.agent), s.agent))
        return scores

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

        # Router v2 confidence scoring.
        scores = self.score_agents(prompt)
        routing_confidence = _routing_confidence([s.score for s in scores])
        tier = ConfidenceTier.classify(routing_confidence)
        selected_agent = scores[0].agent if scores else None
        # Ambiguous (low confidence) with a real contender -> escalate to top 2.
        escalated = tier is ConfidenceTier.LOW and len(scores) >= 2
        routing_mode = "multi_agent" if escalated else "single"
        secondary_agent = (
            scores[1].agent if tier is ConfidenceTier.MEDIUM and len(scores) > 1 else None
        )
        reasons.append(
            f"routing confidence {routing_confidence:.2f} ({tier.value}); "
            f"selected={selected_agent}, mode={routing_mode}"
        )

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
            selected_agent=selected_agent,
            routing_confidence=routing_confidence,
            confidence_tier=tier,
            agent_scores=tuple(scores),
            routing_mode=routing_mode,
            escalated=escalated,
            secondary_agent=secondary_agent,
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
