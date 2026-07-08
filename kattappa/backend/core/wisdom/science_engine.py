"""Science Engine — Phase K9.

Handles SCIENTIFIC and TECHNICAL question types that must not be
routed through the Wisdom Engine.  Provides structured prompts
and context assembly for the agent_router to dispatch to the
correct specialist agent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ScienceAdvice:
    recommended_agent: str    # e.g. "researcher", "coder", "engineer"
    context_summary: str
    confidence: float


class ScienceEngine:
    """Routes scientific/technical questions to the correct specialist agent."""

    _TECHNICAL_AGENT_MAP: dict[str, str] = {
        "code":       "coder",
        "debug":      "coder",
        "algorithm":  "coder",
        "circuit":    "engineer",
        "electronics":"engineer",
        "radar":      "researcher",
        "rf":         "researcher",
        "research":   "researcher",
        "paper":      "researcher",
        "evidence":   "researcher",
        "explain":    "researcher",
        "math":       "coder",
        "database":   "coder",
        "api":        "coder",
    }

    @classmethod
    def advise(
        cls,
        question: str,
        context: dict[str, Any] | None = None,
    ) -> ScienceAdvice:
        lower = question.lower()
        agent = "researcher"   # default
        for keyword, a in cls._TECHNICAL_AGENT_MAP.items():
            if keyword in lower:
                agent = a
                break

        return ScienceAdvice(
            recommended_agent=agent,
            context_summary=(
                f"Technical/scientific question detected. "
                f"Routing to '{agent}' specialist. "
                f"No Wisdom Engine guidance applies to this domain."
            ),
            confidence=0.8,
        )
