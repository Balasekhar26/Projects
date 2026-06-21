"""Constraint/Veto Consensus Engine (Layer 9C -> Core).

Converts several specialist opinions into ONE safe decision without majority-vote
hallucination. The engine is deterministic and never blends fragments: it
*selects* a coherent recommendation and enumerates the tradeoffs, or it refuses.

It distinguishes three kinds of signal:

* **Veto**        - a validator's PASS/FAIL verdict. A FAIL (e.g. Security fails,
                    or the Scientist proves the physics is impossible) rejects
                    the proposal outright. Vetoes are not opinions to weigh.
* **Constraint**  - HARD constraints must all be jointly satisfiable; if two
                    HARD constraints require incompatible things, there is no
                    feasible solution. SOFT constraints are tradeoffs only.
* **Recommendation** - a weighable preference, ranked by ``weight x confidence``.

Decision rules (from the architecture spec):

    Rule 1  Any HARD conflict        -> NO_FEASIBLE_SOLUTION (+ alternatives)
    Rule 2  SOFT conflicts           -> weighted ranking
    Rule 3  Security veto FAIL       -> REJECTED
    Rule 4  Physics veto FAIL        -> REJECTED  (physics is not negotiable)

The engine has no model call, no I/O, and no randomness: identical inputs yield
identical decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------

class ConstraintType(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"

    @classmethod
    def coerce(cls, value: "ConstraintType | str") -> "ConstraintType":
        if isinstance(value, ConstraintType):
            return value
        return cls(str(value).strip().upper())


class ConsensusStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"                         # a veto fired
    NO_FEASIBLE_SOLUTION = "no_feasible_solution"  # HARD constraints conflict


@dataclass(frozen=True)
class Constraint:
    source: str
    type: ConstraintType
    message: str
    key: str = ""                # the dimension; HARD constraints on the same key may conflict
    required_value: Any = True   # what this constraint requires on ``key``
    satisfiable: bool = True     # the emitting agent's own feasibility verdict

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Constraint":
        return cls(
            source=str(data.get("source", "")),
            type=ConstraintType.coerce(data.get("type", "SOFT")),
            message=str(data.get("message", "")),
            key=str(data.get("key", "")),
            required_value=data.get("required_value", True),
            satisfiable=bool(data.get("satisfiable", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "type": self.type.value,
            "message": self.message,
            "key": self.key,
            "required_value": self.required_value,
            "satisfiable": self.satisfiable,
        }


@dataclass(frozen=True)
class Recommendation:
    source: str
    message: str
    weight: float = 0.5

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Recommendation":
        return cls(
            source=str(data.get("source", "")),
            message=str(data.get("message", "")),
            weight=float(data.get("weight", 0.5)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "message": self.message, "weight": self.weight}


@dataclass(frozen=True)
class Veto:
    source: str
    passed: bool
    reason: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Veto":
        return cls(
            source=str(data.get("source", "")),
            passed=bool(data.get("passed", True)),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "passed": self.passed, "reason": self.reason}


@dataclass(frozen=True)
class AgentOutput:
    agent: str
    confidence: float = 0.5
    constraints: tuple[Constraint, ...] = ()
    recommendations: tuple[Recommendation, ...] = ()
    veto: Veto | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentOutput":
        veto = data.get("veto")
        return cls(
            agent=str(data.get("agent", "")),
            confidence=float(data.get("confidence", 0.5)),
            constraints=tuple(Constraint.from_dict(c) for c in data.get("constraints", [])),
            recommendations=tuple(
                Recommendation.from_dict(r) for r in data.get("recommendations", [])
            ),
            veto=Veto.from_dict(veto) if isinstance(veto, dict) else None,
        )


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RankedRecommendation:
    recommendation: Recommendation
    score: float

    def to_dict(self) -> dict[str, Any]:
        data = self.recommendation.to_dict()
        data["score"] = round(self.score, 4)
        return data


@dataclass(frozen=True)
class ConsensusDecision:
    status: ConsensusStatus
    selected: Recommendation | None
    ranked_recommendations: list[RankedRecommendation] = field(default_factory=list)
    hard_constraints: list[Constraint] = field(default_factory=list)
    soft_constraints: list[Constraint] = field(default_factory=list)
    conflicts: list[tuple[Constraint, Constraint]] = field(default_factory=list)
    vetoes: list[Veto] = field(default_factory=list)
    rejected_by: str | None = None
    alternatives: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def is_actionable(self) -> bool:
        return self.status is ConsensusStatus.APPROVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "selected": self.selected.to_dict() if self.selected else None,
            "ranked_recommendations": [r.to_dict() for r in self.ranked_recommendations],
            "hard_constraints": [c.to_dict() for c in self.hard_constraints],
            "soft_constraints": [c.to_dict() for c in self.soft_constraints],
            "conflicts": [[a.to_dict(), b.to_dict()] for a, b in self.conflicts],
            "vetoes": [v.to_dict() for v in self.vetoes],
            "rejected_by": self.rejected_by,
            "alternatives": list(self.alternatives),
            "reasons": list(self.reasons),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ConsensusEngine:
    """Selects one coherent decision from specialist outputs. Never blends."""

    @classmethod
    def decide(cls, outputs: list[AgentOutput]) -> ConsensusDecision:
        reasons: list[str] = []
        vetoes = [o.veto for o in outputs if o.veto is not None]
        hard = [c for o in outputs for c in o.constraints if c.type is ConstraintType.HARD]
        soft = [c for o in outputs for c in o.constraints if c.type is ConstraintType.SOFT]

        # Rule 3 & 4: any failing veto (Security, Physics, ...) rejects outright.
        failed = [v for v in vetoes if not v.passed]
        if failed:
            # Deterministic: first failing veto by source name.
            failed.sort(key=lambda v: v.source)
            blocker = failed[0]
            reasons.append(f"veto FAIL from {blocker.source}: {blocker.reason}")
            return ConsensusDecision(
                status=ConsensusStatus.REJECTED,
                selected=None,
                hard_constraints=hard,
                soft_constraints=soft,
                vetoes=vetoes,
                rejected_by=blocker.source,
                alternatives=cls._alternatives(outputs),
                reasons=reasons,
            )

        # Rule 1: HARD constraints must be jointly satisfiable.
        conflicts = cls._hard_conflicts(hard)
        unsat = [c for c in hard if not c.satisfiable]
        if conflicts or unsat:
            for c in unsat:
                reasons.append(f"HARD constraint from {c.source} declared unsatisfiable: {c.message}")
            for a, b in conflicts:
                reasons.append(
                    f"HARD conflict on '{a.key}': {a.source} requires {a.required_value!r}, "
                    f"{b.source} requires {b.required_value!r}"
                )
            return ConsensusDecision(
                status=ConsensusStatus.NO_FEASIBLE_SOLUTION,
                selected=None,
                hard_constraints=hard,
                soft_constraints=soft,
                conflicts=conflicts,
                vetoes=vetoes,
                alternatives=cls._alternatives(outputs),
                reasons=reasons,
            )

        # Rule 2: feasible -> rank SOFT recommendations by weight x source confidence.
        confidence_by_agent = {o.agent: o.confidence for o in outputs}
        ranked = cls._rank(outputs, confidence_by_agent)
        selected = ranked[0].recommendation if ranked else None
        if selected is not None:
            reasons.append(
                f"selected '{selected.message}' from {selected.source} (highest weighted score)"
            )
        else:
            reasons.append("no recommendations to rank; constraints satisfied")

        return ConsensusDecision(
            status=ConsensusStatus.APPROVED,
            selected=selected,
            ranked_recommendations=ranked,
            hard_constraints=hard,
            soft_constraints=soft,
            vetoes=vetoes,
            reasons=reasons,
        )

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _hard_conflicts(hard: list[Constraint]) -> list[tuple[Constraint, Constraint]]:
        """Two HARD constraints sharing a non-empty key but requiring different values."""
        conflicts: list[tuple[Constraint, Constraint]] = []
        keyed: dict[str, list[Constraint]] = {}
        for c in hard:
            if c.key:
                keyed.setdefault(c.key, []).append(c)
        for key, group in keyed.items():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if group[i].required_value != group[j].required_value:
                        conflicts.append((group[i], group[j]))
        return conflicts

    @staticmethod
    def _rank(
        outputs: list[AgentOutput], confidence_by_agent: dict[str, float]
    ) -> list[RankedRecommendation]:
        ranked: list[RankedRecommendation] = []
        for o in outputs:
            for rec in o.recommendations:
                conf = confidence_by_agent.get(rec.source, o.confidence)
                ranked.append(RankedRecommendation(rec, rec.weight * conf))
        # Highest score first; deterministic tie-break by source then message.
        ranked.sort(key=lambda r: (-r.score, r.recommendation.source, r.recommendation.message))
        return ranked

    @staticmethod
    def _alternatives(outputs: list[AgentOutput]) -> list[str]:
        """Surface soft tradeoffs and recommendations as alternative directions."""
        alts: list[str] = []
        for o in outputs:
            for c in o.constraints:
                if c.type is ConstraintType.SOFT and c.message:
                    alts.append(f"{c.source}: {c.message}")
            for r in o.recommendations:
                if r.message:
                    alts.append(f"{r.source}: {r.message}")
        return alts


def decide_from_dicts(raw_outputs: list[dict[str, Any]]) -> ConsensusDecision:
    """Parse raw dict outputs (e.g. from the API) and run consensus."""
    return ConsensusEngine.decide([AgentOutput.from_dict(d) for d in raw_outputs])
