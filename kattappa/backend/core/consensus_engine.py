"""Constraint/Veto Consensus Engine (v2).

Consensus is **constraint-driven, not democracy-driven**: the goal is the safest
valid answer that satisfies every non-negotiable constraint, not the most
popular one. The engine is deterministic, *selects* (never blends), and **never
applies anything** — it returns a decision; acting on it (especially any code or
system change) is gated behind human approval.

Decision pipeline:

    Stage 1  HARD constraints jointly satisfiable?  no -> NO_FEASIBLE_SOLUTION
    Stage 2  any validator veto FAIL?               yes -> REJECTED
    Stage 3  any BLOCKING critic finding?           yes -> rework (<=2) or ESCALATE
    Stage 4  weighted voting + recommendation rank  -> APPROVED / REJECTED / ESCALATE
    Gate     production / high-cost / code-change / low-margin -> human approval

Key safety properties:

* **ABSTAIN is first-class** - agents outside their expertise do not vote.
* **Static authority weights** - never reweighted dynamically (un-gameable).
* **Evidence multiplier** - tool/sim/test evidence outweighs pure reasoning.
* **Independent-source rule** - votes sharing one model count as ONE source, so
  the same model cannot pose as several experts.
* **Critic never vetoes** - it can only trigger a bounded rework round.
* **No automatic code changes** - ``auto_apply_allowed`` is always False and any
  code-change decision forces ``requires_human_approval``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ConstraintType(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"

    @classmethod
    def coerce(cls, value: "ConstraintType | str") -> "ConstraintType":
        return value if isinstance(value, ConstraintType) else cls(str(value).strip().upper())


class Decision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"

    @classmethod
    def coerce(cls, value: "Decision | str") -> "Decision":
        return value if isinstance(value, Decision) else cls(str(value).strip().upper())


class EvidenceType(str, Enum):
    TOOL_VERIFIED = "tool_verified"
    SIMULATION = "simulation"
    TEST_RESULTS = "test_results"
    HISTORICAL = "historical"
    REASONING = "reasoning"

    @property
    def multiplier(self) -> float:
        return {
            EvidenceType.TOOL_VERIFIED: 1.0,
            EvidenceType.SIMULATION: 0.9,
            EvidenceType.TEST_RESULTS: 0.9,
            EvidenceType.HISTORICAL: 0.8,
            EvidenceType.REASONING: 0.5,
        }[self]

    @classmethod
    def coerce(cls, value: "EvidenceType | str") -> "EvidenceType":
        if isinstance(value, EvidenceType):
            return value
        key = str(value).strip().lower()
        aliases = {
            "tool": cls.TOOL_VERIFIED, "validator": cls.TOOL_VERIFIED,
            "tool_verified": cls.TOOL_VERIFIED, "sim": cls.SIMULATION,
            "simulation": cls.SIMULATION, "test": cls.TEST_RESULTS,
            "test_results": cls.TEST_RESULTS, "tests": cls.TEST_RESULTS,
            "historical": cls.HISTORICAL, "historical_data": cls.HISTORICAL,
            "reasoning": cls.REASONING, "pure_reasoning": cls.REASONING,
        }
        if key in aliases:
            return aliases[key]
        return cls(key)


class FindingCategory(str, Enum):
    BLOCKING = "blocking"
    ADVISORY = "advisory"

    @classmethod
    def coerce(cls, value: "FindingCategory | str") -> "FindingCategory":
        return value if isinstance(value, FindingCategory) else cls(str(value).strip().lower())


class ConsensusStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NO_FEASIBLE_SOLUTION = "no_feasible_solution"
    ESCALATE = "escalate"


# Static authority weights (never reweighted at runtime).
AUTHORITY: dict[str, int] = {
    "Security": 5, "Scientist": 5, "Engineer": 5, "Critic": 4,
    "Planner": 3, "Builder": 3, "Teacher": 2, "Poet": 1,
}

PRODUCTION_PROJECTS = {"DEWS", "Kairo", "Prism", "Tempo", "Portal", "Mira"}

LOW_MARGIN_THRESHOLD = 0.10


def _authority(agent: str) -> int:
    return AUTHORITY.get(agent, 1)


def _conf01(confidence: float) -> float:
    """Normalise confidence to [0,1], tolerating both 0-1 and 0-100 inputs."""
    c = confidence / 100.0 if confidence > 1.0 else confidence
    return max(0.0, min(1.0, c))


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Constraint:
    source: str
    type: ConstraintType
    message: str
    key: str = ""
    required_value: Any = True
    satisfiable: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Constraint":
        return cls(
            source=str(data.get("source", "")),
            type=ConstraintType.coerce(data.get("type", "SOFT")),
            message=str(data.get("message", data.get("description", ""))),
            key=str(data.get("key", "")),
            required_value=data.get("required_value", True),
            satisfiable=bool(data.get("satisfiable", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source, "type": self.type.value, "message": self.message,
            "key": self.key, "required_value": self.required_value, "satisfiable": self.satisfiable,
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
            message=str(data.get("message", data.get("description", ""))),
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
        return cls(str(data.get("source", "")), bool(data.get("passed", True)), str(data.get("reason", "")))

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "passed": self.passed, "reason": self.reason}


@dataclass(frozen=True)
class CriticFinding:
    source: str
    category: FindingCategory
    description: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CriticFinding":
        return cls(
            source=str(data.get("source", "Critic")),
            category=FindingCategory.coerce(data.get("category", "advisory")),
            description=str(data.get("description", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "category": self.category.value, "description": self.description}


@dataclass(frozen=True)
class AgentOutput:
    agent: str
    decision: Decision = Decision.ABSTAIN
    confidence: float = 0.5
    constraints: tuple[Constraint, ...] = ()
    recommendations: tuple[Recommendation, ...] = ()
    veto: Veto | None = None
    evidence: tuple[EvidenceType, ...] = ()
    critic_findings: tuple[CriticFinding, ...] = ()
    source_id: str = "model"   # agents sharing a source_id are NOT independent
    rationale: str = ""

    @property
    def evidence_multiplier(self) -> float:
        return max((e.multiplier for e in self.evidence), default=0.5)

    @property
    def vote_weight(self) -> float:
        return _authority(self.agent) * self.evidence_multiplier

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentOutput":
        veto = data.get("veto")
        return cls(
            agent=str(data.get("agent", "")),
            decision=Decision.coerce(data.get("decision", "ABSTAIN")),
            confidence=float(data.get("confidence", 0.5)),
            constraints=tuple(Constraint.from_dict(c) for c in data.get("constraints", [])),
            recommendations=tuple(Recommendation.from_dict(r) for r in data.get("recommendations", [])),
            veto=Veto.from_dict(veto) if isinstance(veto, dict) else None,
            evidence=tuple(EvidenceType.coerce(e.get("source") if isinstance(e, dict) else e)
                           for e in data.get("evidence", [])),
            critic_findings=tuple(CriticFinding.from_dict(f) for f in data.get("critic_findings", [])),
            source_id=str(data.get("source_id", "model")),
            rationale=str(data.get("rationale", "")),
        )


@dataclass(frozen=True)
class DecisionContext:
    project: str = ""
    code_change: bool = False
    high_cost_change: bool = False
    production_system: bool = False
    round_index: int = 0
    max_rounds: int = 2

    @property
    def is_production(self) -> bool:
        return self.production_system or self.project in PRODUCTION_PROJECTS

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DecisionContext":
        data = data or {}
        return cls(
            project=str(data.get("project", "")),
            code_change=bool(data.get("code_change", False)),
            high_cost_change=bool(data.get("high_cost_change", False)),
            production_system=bool(data.get("production_system", False)),
            round_index=int(data.get("round_index", 0)),
            max_rounds=int(data.get("max_rounds", 2)),
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
    requires_human_approval: bool = False
    ranked_recommendations: list[RankedRecommendation] = field(default_factory=list)
    hard_constraints: list[Constraint] = field(default_factory=list)
    soft_constraints: list[Constraint] = field(default_factory=list)
    conflicts: list[tuple[Constraint, Constraint]] = field(default_factory=list)
    vetoes: list[Veto] = field(default_factory=list)
    rejected_by: str | None = None
    for_agents: list[str] = field(default_factory=list)
    against_agents: list[str] = field(default_factory=list)
    abstained: list[str] = field(default_factory=list)
    approve_mass: float = 0.0
    reject_mass: float = 0.0
    margin: float | None = None
    independent_sources: int = 0
    blocking_findings: list[CriticFinding] = field(default_factory=list)
    advisory_findings: list[CriticFinding] = field(default_factory=list)
    rework_recommended: bool = False
    alternatives: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    # Hard safety invariant: the engine decides, it never acts.
    @property
    def auto_apply_allowed(self) -> bool:
        return False

    @property
    def is_actionable(self) -> bool:
        return self.status is ConsensusStatus.APPROVED and not self.requires_human_approval

    def human_dashboard(self) -> dict[str, Any]:
        proposal = self.selected.message if self.selected else (
            self.alternatives[0] if self.alternatives else "(no proposal)"
        )
        critic = [f.description for f in self.blocking_findings + self.advisory_findings]
        return {
            "proposal": proposal,
            "consensus": self.status.value,
            "requires_human_approval": self.requires_human_approval,
            "for": list(self.for_agents),
            "against": list(self.against_agents),
            "critic": critic,
            "options": [
                "Approve",
                "Approve with added isolation/constraints",
                "Reject",
                "Request more research",
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "selected": self.selected.to_dict() if self.selected else None,
            "requires_human_approval": self.requires_human_approval,
            "auto_apply_allowed": self.auto_apply_allowed,
            "ranked_recommendations": [r.to_dict() for r in self.ranked_recommendations],
            "hard_constraints": [c.to_dict() for c in self.hard_constraints],
            "soft_constraints": [c.to_dict() for c in self.soft_constraints],
            "conflicts": [[a.to_dict(), b.to_dict()] for a, b in self.conflicts],
            "vetoes": [v.to_dict() for v in self.vetoes],
            "rejected_by": self.rejected_by,
            "for_agents": list(self.for_agents),
            "against_agents": list(self.against_agents),
            "abstained": list(self.abstained),
            "approve_mass": round(self.approve_mass, 4),
            "reject_mass": round(self.reject_mass, 4),
            "margin": (round(self.margin, 4) if self.margin is not None else None),
            "independent_sources": self.independent_sources,
            "blocking_findings": [f.to_dict() for f in self.blocking_findings],
            "advisory_findings": [f.to_dict() for f in self.advisory_findings],
            "rework_recommended": self.rework_recommended,
            "alternatives": list(self.alternatives),
            "reasons": list(self.reasons),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ConsensusEngine:
    """Constraint-driven, deterministic, select-not-blend consensus."""

    @classmethod
    def decide(
        cls, outputs: list[AgentOutput], context: DecisionContext | None = None
    ) -> ConsensusDecision:
        context = context or DecisionContext()
        reasons: list[str] = []
        vetoes = [o.veto for o in outputs if o.veto is not None]
        hard = [c for o in outputs for c in o.constraints if c.type is ConstraintType.HARD]
        soft = [c for o in outputs for c in o.constraints if c.type is ConstraintType.SOFT]
        for_agents = [o.agent for o in outputs if o.decision is Decision.APPROVE]
        against_agents = [o.agent for o in outputs if o.decision is Decision.REJECT]
        abstained = [o.agent for o in outputs if o.decision is Decision.ABSTAIN]
        blocking = [f for o in outputs for f in o.critic_findings if f.category is FindingCategory.BLOCKING]
        advisory = [f for o in outputs for f in o.critic_findings if f.category is FindingCategory.ADVISORY]

        base = dict(
            hard_constraints=hard, soft_constraints=soft, vetoes=vetoes,
            for_agents=for_agents, against_agents=against_agents, abstained=abstained,
            blocking_findings=blocking, advisory_findings=advisory,
        )

        # Stage 1: HARD constraints must be jointly satisfiable (no voting).
        conflicts = cls._hard_conflicts(hard)
        unsat = [c for c in hard if not c.satisfiable]
        if conflicts or unsat:
            for c in unsat:
                reasons.append(f"HARD constraint from {c.source} unsatisfiable: {c.message}")
            for a, b in conflicts:
                reasons.append(
                    f"HARD conflict on '{a.key}': {a.source} requires {a.required_value!r}, "
                    f"{b.source} requires {b.required_value!r}"
                )
            return ConsensusDecision(
                status=ConsensusStatus.NO_FEASIBLE_SOLUTION, selected=None,
                requires_human_approval=True, conflicts=conflicts,
                alternatives=cls._alternatives(outputs), reasons=reasons, **base,
            )

        # Stage 2: validator vetoes (Security / Physics / Compiler ...) reject now.
        failed = sorted((v for v in vetoes if not v.passed), key=lambda v: v.source)
        if failed:
            blocker = failed[0]
            reasons.append(f"veto FAIL from {blocker.source}: {blocker.reason}")
            return ConsensusDecision(
                status=ConsensusStatus.REJECTED, selected=None,
                requires_human_approval=True, rejected_by=blocker.source,
                alternatives=cls._alternatives(outputs), reasons=reasons, **base,
            )

        # Stage 3: a BLOCKING critic finding triggers a bounded rework round.
        if blocking:
            if context.round_index < context.max_rounds - 1:
                reasons.append("blocking critic finding -> rework round")
                return ConsensusDecision(
                    status=ConsensusStatus.ESCALATE, selected=None,
                    requires_human_approval=False, rework_recommended=True,
                    reasons=reasons, **base,
                )
            reasons.append("blocking critic finding persists after max rounds -> human")
            return ConsensusDecision(
                status=ConsensusStatus.ESCALATE, selected=None,
                requires_human_approval=True, reasons=reasons, **base,
            )

        # Stage 4: weighted voting (independent-source) + recommendation ranking.
        approve_mass, reject_mass, approve_srcs, reject_srcs = cls._tally(outputs)
        total = approve_mass + reject_mass
        margin = abs(approve_mass - reject_mass) / total if total > 0 else None
        ranked = cls._rank(outputs)
        independent_sources = len(set(o.source_id for o in outputs
                                      if o.decision in (Decision.APPROVE, Decision.REJECT)))

        human = context.is_production or context.high_cost_change
        if context.is_production:
            reasons.append("production system -> human approval required")
        if context.high_cost_change:
            reasons.append("high-cost change -> human approval required")

        if total == 0:
            # No votes cast: recommendation-led approval.
            selected = ranked[0].recommendation if ranked else None
            status = ConsensusStatus.APPROVED
            reasons.append("no votes cast; recommendation-led decision")
        elif margin is not None and margin < LOW_MARGIN_THRESHOLD:
            selected = None
            status = ConsensusStatus.ESCALATE
            human = True
            reasons.append(f"low consensus margin {margin:.2f} (<{LOW_MARGIN_THRESHOLD}) -> human")
        elif approve_mass > reject_mass:
            selected = ranked[0].recommendation if ranked else None
            status = ConsensusStatus.APPROVED
            reasons.append(f"APPROVE wins: mass {approve_mass:.2f} vs {reject_mass:.2f}")
        elif reject_mass > approve_mass:
            selected = None
            status = ConsensusStatus.REJECTED
            reasons.append(f"REJECT wins: mass {reject_mass:.2f} vs {approve_mass:.2f}")
        else:  # exact tie
            selected = None
            status = ConsensusStatus.ESCALATE
            human = True
            reasons.append("tied consensus mass -> human")

        # Hard rule: never allow automatic code changes.
        if context.code_change:
            human = True
            reasons.append("code change -> human approval required (no automatic code changes)")

        rejected_by = "vote" if status is ConsensusStatus.REJECTED else None
        return ConsensusDecision(
            status=status, selected=selected, requires_human_approval=human,
            ranked_recommendations=ranked, rejected_by=rejected_by,
            approve_mass=approve_mass, reject_mass=reject_mass, margin=margin,
            independent_sources=independent_sources,
            alternatives=cls._alternatives(outputs), reasons=reasons, **base,
        )

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _hard_conflicts(hard: list[Constraint]) -> list[tuple[Constraint, Constraint]]:
        conflicts: list[tuple[Constraint, Constraint]] = []
        keyed: dict[str, list[Constraint]] = {}
        for c in hard:
            if c.key:
                keyed.setdefault(c.key, []).append(c)
        for group in keyed.values():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if group[i].required_value != group[j].required_value:
                        conflicts.append((group[i], group[j]))
        return conflicts

    @staticmethod
    def _tally(outputs: list[AgentOutput]) -> tuple[float, float, list[str], list[str]]:
        """Per-independent-source vote mass. Same source_id counts ONCE."""
        by_source: dict[str, list[AgentOutput]] = {}
        for o in outputs:
            if o.decision in (Decision.APPROVE, Decision.REJECT):
                by_source.setdefault(o.source_id, []).append(o)

        approve_mass = reject_mass = 0.0
        approve_srcs: list[str] = []
        reject_srcs: list[str] = []
        for source, group in by_source.items():
            app = max((o.vote_weight for o in group if o.decision is Decision.APPROVE), default=0.0)
            rej = max((o.vote_weight for o in group if o.decision is Decision.REJECT), default=0.0)
            if app > rej:
                approve_mass += app
                approve_srcs.append(source)
            elif rej > app:
                reject_mass += rej
                reject_srcs.append(source)
            # within-source tie -> that source abstains
        return approve_mass, reject_mass, approve_srcs, reject_srcs

    @staticmethod
    def _rank(outputs: list[AgentOutput]) -> list[RankedRecommendation]:
        by_agent = {o.agent: o for o in outputs}
        ranked: list[RankedRecommendation] = []
        for o in outputs:
            for rec in o.recommendations:
                owner = by_agent.get(rec.source, o)
                score = (rec.weight * _authority(rec.source)
                         * owner.evidence_multiplier * _conf01(owner.confidence))
                ranked.append(RankedRecommendation(rec, score))
        ranked.sort(key=lambda r: (-r.score, r.recommendation.source, r.recommendation.message))
        return ranked

    @staticmethod
    def _alternatives(outputs: list[AgentOutput]) -> list[str]:
        alts: list[str] = []
        for o in outputs:
            for c in o.constraints:
                if c.type is ConstraintType.SOFT and c.message:
                    alts.append(f"{c.source}: {c.message}")
            for r in o.recommendations:
                if r.message:
                    alts.append(f"{r.source}: {r.message}")
        return alts


def decide_from_dicts(
    raw_outputs: list[dict[str, Any]], context: dict[str, Any] | None = None
) -> ConsensusDecision:
    return ConsensusEngine.decide(
        [AgentOutput.from_dict(d) for d in raw_outputs], DecisionContext.from_dict(context)
    )
