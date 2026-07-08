"""Wisdom Engine — Phase K9.

Takes a classified decision context and returns ranked, applicable Gita
principles along with their concrete guidance.  Never invoked for technical
or scientific questions — the DecisionClassifier enforces this.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.wisdom.gita_principles import (
    PRINCIPLES,
    GitaPrinciple,
    get_principles_for_domain,
    is_excluded_domain,
)
from backend.core.logger import log_event


@dataclass
class WisdomAdvice:
    principles: list[GitaPrinciple]
    summary: str          # one-paragraph synthesis for planner/executive
    governing_domain: str
    confidence: float


class WisdomEngine:
    """Queries Gita principles and synthesizes actionable ethical guidance."""

    @classmethod
    def advise(
        cls,
        question: str,
        domains: list[str],
        context: dict[str, Any] | None = None,
    ) -> WisdomAdvice:
        """Return ranked applicable principles for the given domains.

        Parameters
        ----------
        question:  the original user question or decision context
        domains:   domain tags from DecisionClassifier (e.g. ["ethics", "conflict"])
        context:   optional state dict for additional filtering
        """
        # Safety: never advise on excluded technical domains
        for d in domains:
            if is_excluded_domain(d):
                log_event(
                    "wisdom_engine_exclusion",
                    f"Domain {d!r} is excluded from Wisdom Engine — routing blocked.",
                )
                return WisdomAdvice(
                    principles=[],
                    summary=(
                        "This question is in a technical domain. "
                        "The Wisdom Engine does not advise on technical questions. "
                        "Route to the engineering/science path."
                    ),
                    governing_domain=d,
                    confidence=0.0,
                )

        matched: dict[str, GitaPrinciple] = {}
        domain_hit_counts: dict[str, int] = {}

        for domain in domains:
            hits = get_principles_for_domain(domain)
            domain_hit_counts[domain] = len(hits)
            for p in hits:
                if p.id not in matched:
                    matched[p.id] = p

        # Sort by: most relevant domain first, then chapter order
        ranked = sorted(matched.values(), key=lambda p: (
            -max(domain_hit_counts.get(d, 0) for d in p.application_domains if d in domains),
            p.chapter,
        ))

        top = ranked[:4]   # cap at 4 principles per response

        governing_domain = domains[0] if domains else "ethics"
        summary = cls._synthesize(question, top, governing_domain)
        confidence = min(1.0, len(top) / 4.0) if top else 0.0

        log_event(
            "wisdom_engine_advise",
            f"Wisdom Engine: {len(top)} principles for domains={domains}",
        )
        return WisdomAdvice(
            principles=top,
            summary=summary,
            governing_domain=governing_domain,
            confidence=confidence,
        )

    @staticmethod
    def _synthesize(question: str, principles: list[GitaPrinciple], domain: str) -> str:
        if not principles:
            return "No applicable Gita principles found for this domain."

        lines = [
            f"Wisdom guidance for domain '{domain}':",
            "",
        ]
        for p in principles:
            lines.append(f"• [{p.id}] {p.principle}")
            lines.append(f"  → {p.guidance}")
            lines.append("")

        lines.append(
            "Apply these principles to: clarify priorities, resolve ethical tensions, "
            "and align the plan with long-term purpose — not immediate outcomes."
        )
        return "\n".join(lines)
