"""IntentRouter — Phase K8 upgrade.

Determines which memory tiers to query based on intent semantics alone.
The caller never specifies memory types; they specify intent and the
router selects the optimal tier combination.

Intent taxonomy
───────────────
  RECALL_EVENT      "What happened yesterday?" → episodic
  LOOKUP_CONCEPT    "What is radar?"           → semantic, knowledge_graph
  LOOKUP_PROCEDURE  "How do I calibrate X?"    → procedural
  DIAGNOSE_FAILURE  "Why did X fail?"          → episodic, semantic, world_model, KG
  PLAN_TASK         "Help me plan..."          → working, semantic, goal_manager
  LEARN_CONCEPT     "Teach me about..."        → semantic, knowledge_graph
  REFLECT           "What have I learned?"     → episodic, semantic
  RETRIEVE_CONTEXT  "What were we discussing?" → working, episodic
  GENERAL           fallback                   → working, episodic, semantic
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import auto, Enum


class MemoryIntent(str, Enum):
    RECALL_EVENT     = "RECALL_EVENT"
    LOOKUP_CONCEPT   = "LOOKUP_CONCEPT"
    LOOKUP_PROCEDURE = "LOOKUP_PROCEDURE"
    DIAGNOSE_FAILURE = "DIAGNOSE_FAILURE"
    PLAN_TASK        = "PLAN_TASK"
    LEARN_CONCEPT    = "LEARN_CONCEPT"
    REFLECT          = "REFLECT"
    RETRIEVE_CONTEXT = "RETRIEVE_CONTEXT"
    GENERAL          = "GENERAL"


@dataclass
class RoutingDecision:
    intent: MemoryIntent
    memory_types: list[str]
    reasoning: str


# ── Signal patterns per intent ─────────────────────────────────────────────────

_RECALL_SIGNALS = (
    r"\b(yesterday|last week|earlier|before|what happened|recall|remember|when did)\b",
)
_PROCEDURE_SIGNALS = (
    r"\bhow (do|can|should) (i|we|you)\b",
    r"\bsteps (to|for)\b",
    r"\bprocedure\b",
    r"\bcalibrat\b",
    r"\binstall\b",
    r"\bset up\b",
    r"\bconfigure\b",
)
_FAILURE_SIGNALS = (
    r"\bwhy (did|does|is)\b.*\bfail\b",
    r"\bfailed\b",
    r"\bnot working\b",
    r"\berror\b",
    r"\bdiagnos\b",
    r"\broot cause\b",
    r"\bbroken\b",
)
_PLAN_SIGNALS = (
    r"\bplan\b",
    r"\bstrategy\b",
    r"\bmilestone\b",
    r"\bnext step\b",
    r"\broadmap\b",
    r"\bgoal\b",
)
_CONCEPT_SIGNALS = (
    r"\bwhat is\b",
    r"\bwhat are\b",
    r"\bdefin\b",
    r"\bexplain\b",
    r"\bdescrib\b",
    r"\bmeaning of\b",
)
_LEARN_SIGNALS = (
    r"\bteach me\b",
    r"\blearn\b",
    r"\bstudy\b",
    r"\bunderstand\b",
    r"\btutorial\b",
)
_REFLECT_SIGNALS = (
    r"\bwhat (have|did) (i|we) learn\b",
    r"\breflect\b",
    r"\binsight\b",
    r"\bpattern\b",
    r"\blessons?\b",
)
_CONTEXT_SIGNALS = (
    r"\bwere (we|you|i) (discussing|talking|working)\b",
    r"\bour (last|previous|earlier) (conversation|discussion|session)\b",
    r"\bcontext\b",
)

_INTENT_MEMORY_MAP: dict[MemoryIntent, list[str]] = {
    MemoryIntent.RECALL_EVENT:     ["episodic"],
    MemoryIntent.LOOKUP_CONCEPT:   ["semantic", "knowledge_graph"],
    MemoryIntent.LOOKUP_PROCEDURE: ["procedural"],
    MemoryIntent.DIAGNOSE_FAILURE: ["episodic", "semantic", "knowledge_graph"],
    MemoryIntent.PLAN_TASK:        ["working", "semantic"],
    MemoryIntent.LEARN_CONCEPT:    ["semantic", "knowledge_graph"],
    MemoryIntent.REFLECT:          ["episodic", "semantic"],
    MemoryIntent.RETRIEVE_CONTEXT: ["working", "episodic"],
    MemoryIntent.GENERAL:          ["working", "episodic", "semantic"],
}


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(re.search(p, lower) for p in patterns)


class IntentRouter:
    """Routes a natural language query to the correct memory tier(s) by intent."""

    @classmethod
    def route(cls, query: str) -> RoutingDecision:
        """Classify the query intent and return the optimal memory tier list.

        Parameters
        ----------
        query : str
            The natural language query or question.

        Returns
        -------
        RoutingDecision
            Contains the classified intent and the list of memory tiers to search.
        """
        if _matches_any(query, _FAILURE_SIGNALS):
            return RoutingDecision(
                intent=MemoryIntent.DIAGNOSE_FAILURE,
                memory_types=_INTENT_MEMORY_MAP[MemoryIntent.DIAGNOSE_FAILURE],
                reasoning="Failure/error signals detected → episodic + semantic + KG for causal diagnosis",
            )
        if _matches_any(query, _PROCEDURE_SIGNALS):
            return RoutingDecision(
                intent=MemoryIntent.LOOKUP_PROCEDURE,
                memory_types=_INTENT_MEMORY_MAP[MemoryIntent.LOOKUP_PROCEDURE],
                reasoning="Procedural 'how to' intent → procedural memory",
            )
        if _matches_any(query, _RECALL_SIGNALS):
            return RoutingDecision(
                intent=MemoryIntent.RECALL_EVENT,
                memory_types=_INTENT_MEMORY_MAP[MemoryIntent.RECALL_EVENT],
                reasoning="Temporal/event recall signals → episodic only",
            )
        if _matches_any(query, _REFLECT_SIGNALS):
            return RoutingDecision(
                intent=MemoryIntent.REFLECT,
                memory_types=_INTENT_MEMORY_MAP[MemoryIntent.REFLECT],
                reasoning="Reflection/learning intent → episodic + semantic",
            )
        if _matches_any(query, _CONTEXT_SIGNALS):
            return RoutingDecision(
                intent=MemoryIntent.RETRIEVE_CONTEXT,
                memory_types=_INTENT_MEMORY_MAP[MemoryIntent.RETRIEVE_CONTEXT],
                reasoning="Context retrieval signals → working + episodic",
            )
        if _matches_any(query, _PLAN_SIGNALS):
            return RoutingDecision(
                intent=MemoryIntent.PLAN_TASK,
                memory_types=_INTENT_MEMORY_MAP[MemoryIntent.PLAN_TASK],
                reasoning="Planning intent → working memory + semantic knowledge",
            )
        if _matches_any(query, _LEARN_SIGNALS):
            return RoutingDecision(
                intent=MemoryIntent.LEARN_CONCEPT,
                memory_types=_INTENT_MEMORY_MAP[MemoryIntent.LEARN_CONCEPT],
                reasoning="Learning intent → semantic + KG for deep concept search",
            )
        if _matches_any(query, _CONCEPT_SIGNALS):
            return RoutingDecision(
                intent=MemoryIntent.LOOKUP_CONCEPT,
                memory_types=_INTENT_MEMORY_MAP[MemoryIntent.LOOKUP_CONCEPT],
                reasoning="Concept lookup intent → semantic + KG",
            )
        return RoutingDecision(
            intent=MemoryIntent.GENERAL,
            memory_types=_INTENT_MEMORY_MAP[MemoryIntent.GENERAL],
            reasoning="No specific intent detected → general fan-out across working, episodic, semantic",
        )
