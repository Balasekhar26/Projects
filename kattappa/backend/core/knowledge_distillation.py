"""Knowledge Distillation Engine (Tier 2).

Converts many observations/reflections into a few patterns, and patterns into
reusable principles:

    100 reflections -> 10 patterns -> 1 principle

Deterministic, token-similarity clustering (no LLM). It distills experience into
wisdom; it never mutates memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "the a an and or but if then is are was were be to of in on at for with from by as it "
    "this that these those i you we they them my our your".split()
)


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(text.lower()) if len(t) > 2 and t not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class Pattern:
    representative: str
    count: int
    members: list[str]
    common_terms: list[str]
    principle: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "representative": self.representative,
            "count": self.count,
            "members": list(self.members),
            "common_terms": list(self.common_terms),
            "principle": self.principle,
        }


@dataclass(frozen=True)
class DistillationReport:
    observations: int
    patterns: list[Pattern] = field(default_factory=list)

    @property
    def principles(self) -> list[str]:
        return [p.principle for p in self.patterns]

    def to_dict(self) -> dict[str, Any]:
        return {
            "observations": self.observations,
            "pattern_count": len(self.patterns),
            "patterns": [p.to_dict() for p in self.patterns],
            "principles": self.principles,
        }


class KnowledgeDistiller:
    SIMILARITY = 0.34
    MIN_CLUSTER = 3

    @classmethod
    def distill(
        cls,
        observations: list[str],
        *,
        min_cluster: int | None = None,
        similarity: float | None = None,
        principle_hints: dict[str, str] | None = None,
    ) -> DistillationReport:
        min_cluster = cls.MIN_CLUSTER if min_cluster is None else min_cluster
        similarity = cls.SIMILARITY if similarity is None else similarity
        hints = {k.lower(): v for k, v in (principle_hints or {}).items()}

        clusters: list[dict[str, Any]] = []
        for obs in observations:
            obs = obs.strip()
            if not obs:
                continue
            toks = _tokens(obs)
            placed = False
            for c in clusters:
                if _jaccard(toks, c["centroid"]) >= similarity:
                    c["members"].append(obs)
                    c["token_lists"].append(toks)
                    # centroid = tokens common to >= half the members
                    counts: dict[str, int] = {}
                    for tl in c["token_lists"]:
                        for t in tl:
                            counts[t] = counts.get(t, 0) + 1
                    half = len(c["token_lists"]) / 2
                    c["centroid"] = {t for t, n in counts.items() if n >= half} or toks
                    placed = True
                    break
            if not placed:
                clusters.append({"members": [obs], "token_lists": [toks], "centroid": set(toks)})

        patterns: list[Pattern] = []
        for c in clusters:
            if len(c["members"]) < min_cluster:
                continue
            counts: dict[str, int] = {}
            for tl in c["token_lists"]:
                for t in tl:
                    counts[t] = counts.get(t, 0) + 1
            common = [t for t, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))][:5]
            representative = max(c["members"], key=len)
            principle = cls._principle(common, len(c["members"]), hints)
            patterns.append(Pattern(representative, len(c["members"]), list(c["members"]),
                                    common, principle))

        patterns.sort(key=lambda p: p.count, reverse=True)
        return DistillationReport(observations=len([o for o in observations if o.strip()]),
                                  patterns=patterns)

    @staticmethod
    def _principle(common_terms: list[str], count: int, hints: dict[str, str]) -> str:
        for term in common_terms:
            if term in hints:
                return hints[term]
        terms = ", ".join(common_terms[:4]) if common_terms else "this theme"
        return (f"Recurring pattern observed {count} times around [{terms}]; "
                f"establish a standing rule to handle it proactively.")
