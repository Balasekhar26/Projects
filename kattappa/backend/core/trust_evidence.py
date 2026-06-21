"""Trust & Evidence System (Tier 1).

Every conclusion earns an evidence score, a confidence tier, and a provenance
trail. Higher-quality evidence always dominates: a real-world measurement
outweighs validators, which outweigh tests, history, reasoning, and bare
opinion. Refuting evidence at a higher level than the support flags a conflict.

Pure, deterministic; no persistence, no side effects. Complements the Consensus
v2 evidence multiplier with explicit levels and provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvidenceLevel(int, Enum):
    OPINION = 0
    LLM_REASONING = 1
    HISTORICAL = 2
    TEST_RESULT = 3
    VALIDATOR = 4
    REAL_WORLD = 5

    @property
    def normalized(self) -> float:
        return self.value / 5.0

    @classmethod
    def coerce(cls, value: "EvidenceLevel | int | str") -> "EvidenceLevel":
        if isinstance(value, EvidenceLevel):
            return value
        if isinstance(value, int):
            return cls(value)
        key = str(value).strip().upper().replace(" ", "_")
        aliases = {
            "OPINION": cls.OPINION, "REASONING": cls.LLM_REASONING,
            "LLM": cls.LLM_REASONING, "LLM_REASONING": cls.LLM_REASONING,
            "HISTORY": cls.HISTORICAL, "HISTORICAL": cls.HISTORICAL,
            "MEMORY": cls.HISTORICAL, "TEST": cls.TEST_RESULT,
            "TEST_RESULT": cls.TEST_RESULT, "VALIDATOR": cls.VALIDATOR,
            "TOOL": cls.VALIDATOR, "REAL_WORLD": cls.REAL_WORLD,
            "MEASUREMENT": cls.REAL_WORLD,
        }
        if key in aliases:
            return aliases[key]
        return cls(int(key))


class ConfidenceTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @classmethod
    def classify(cls, score: float) -> "ConfidenceTier":
        if score >= 0.80:
            return cls.HIGH
        if score >= 0.50:
            return cls.MEDIUM
        return cls.LOW


@dataclass(frozen=True)
class EvidenceItem:
    source: str
    level: EvidenceLevel
    supports: bool = True
    detail: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceItem":
        return cls(
            source=str(data.get("source", "")),
            level=EvidenceLevel.coerce(data.get("level", 0)),
            supports=bool(data.get("supports", True)),
            detail=str(data.get("detail", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source, "level": self.level.name.lower(),
            "level_value": self.level.value, "supports": self.supports, "detail": self.detail,
        }


@dataclass(frozen=True)
class TrustReport:
    statement: str
    evidence_score: float
    confidence: ConfidenceTier
    top_level: str
    conflict: bool
    provenance: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "evidence_score": round(self.evidence_score, 4),
            "confidence": self.confidence.value,
            "top_level": self.top_level,
            "conflict": self.conflict,
            "provenance": list(self.provenance),
            "reasons": list(self.reasons),
        }


class TrustEngine:
    @classmethod
    def assess(cls, statement: str, evidence: list[EvidenceItem]) -> TrustReport:
        supporting = [e for e in evidence if e.supports]
        refuting = [e for e in evidence if not e.supports]
        reasons: list[str] = []

        provenance = sorted(
            (e.to_dict() for e in evidence),
            key=lambda d: d["level_value"], reverse=True,
        )

        if not supporting:
            reasons.append("no supporting evidence")
            return TrustReport(statement, 0.0, ConfidenceTier.LOW, "none", False, provenance, reasons)

        best_support = max(e.level for e in supporting)
        best_refute = max((e.level for e in refuting), default=None)

        conflict = best_refute is not None and best_refute.value >= best_support.value
        if conflict:
            score = max(0.0, best_support.normalized - best_refute.normalized)
            reasons.append(
                f"refuted by stronger/equal evidence ({best_refute.name.lower()} >= "
                f"{best_support.name.lower()})"
            )
        else:
            base = best_support.normalized
            # Corroboration: extra independent sources at the top level lift trust.
            top_count = sum(1 for e in supporting if e.level is best_support)
            boost = min(0.15, 0.05 * (top_count - 1))
            score = min(1.0, base + boost)
            reasons.append(f"top supporting evidence: {best_support.name.lower()}")
            if top_count > 1:
                reasons.append(f"{top_count} corroborating sources at top level")

        return TrustReport(
            statement=statement,
            evidence_score=score,
            confidence=ConfidenceTier.classify(score),
            top_level=best_support.name.lower(),
            conflict=conflict,
            provenance=provenance,
            reasons=reasons,
        )


def assess_from_dicts(statement: str, raw_evidence: list[dict[str, Any]]) -> TrustReport:
    return TrustEngine.assess(statement, [EvidenceItem.from_dict(d) for d in raw_evidence])
