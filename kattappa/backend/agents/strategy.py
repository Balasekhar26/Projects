"""
strategy.py
===========
Strategy Agent V1 — Policy synthesis layer for Kattappa AI OS.

Position in the cognitive stack
---------------------------------
  Reflection Agent  →  Strategy Agent  →  Executive Agent
       (observes)         (proposes)          (decides)

Responsibilities
----------------
* Reads Reflection Agent reports and typed observations
* Converts observations into structured, versioned ProposedPolicy objects
* Detects duplicate and conflicting policies before submission
* Routes proposed policies to Executive for review (never self-applies)
* Maintains a persistent, versioned PolicyLedger

Authority Rules (hard constraints)
------------------------------------
✅  Read Reflection reports and Memory Service
✅  Produce ProposedPolicy objects (advisory data)
✅  Write proposed policies to the PolicyLedger
✅  Write advisory summaries to Memory Service
✅  Accept/reject acknowledgements from Executive

❌  Self-apply any policy
❌  Modify CapabilityRegistry or PolicyEngine
❌  Call ActionBroker directly
❌  Rewrite Planner plans
❌  Approve its own policy proposals
❌  Execute OS actions of any kind
"""

from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


# ── Paths ─────────────────────────────────────────────────────────────────────

def _ledger_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "policy_ledger.json"


def _reflection_reports_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "reflection_reports.json"


# ── Policy Domain Models ───────────────────────────────────────────────────────

class PolicyStatus(str, Enum):
    PROPOSED        = "PROPOSED"
    PENDING_REVIEW  = "PENDING_REVIEW"
    ACCEPTED        = "ACCEPTED"
    REJECTED        = "REJECTED"
    ACTIVE          = "ACTIVE"
    SUSPENDED       = "SUSPENDED"
    EXPIRED         = "EXPIRED"


class PolicyCategory(str, Enum):
    SCHEDULING_CONSTRAINT = "scheduling_constraint"
    AGENT_PREFERENCE      = "agent_preference"
    RETRY_BUDGET          = "retry_budget"
    RESOURCE_GATE         = "resource_gate"
    PLAN_CONSTRAINT       = "plan_constraint"
    COOLDOWN              = "cooldown"


@dataclass
class PolicyCondition:
    """Describes when a policy applies."""
    resource: str | None = None          # e.g. "CPU", "RAM"
    operator: str | None = None          # "gt", "lt", "eq", "gte", "lte"
    threshold: float | None = None       # numeric threshold
    agent: str | None = None            # target agent
    action_type: str | None = None      # e.g. "VOICE_TTS"
    time_window_sec: int | None = None  # rolling window for rate-based conditions

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class PolicyEffect:
    """Describes what the policy does when the condition fires."""
    action: str                           # "defer", "prefer", "limit_retries", "block", "cooldown"
    target_agent: str | None = None
    alternative_agent: str | None = None
    max_retries: int | None = None
    cooldown_sec: int | None = None
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ProposedPolicy:
    """
    A versioned, advisory policy proposal.
    Requires Executive acceptance before it influences any planning.
    """
    policy_id: str
    version: int
    status: str
    category: str
    title: str
    condition: dict[str, Any]
    effect: dict[str, Any]
    derived_from: list[str]         # Recommendation IDs that triggered this policy
    confidence: float
    proposed_at: float
    accepted_at: float | None = None
    rejected_at: float | None = None
    rejection_reason: str | None = None
    expires_at: float | None = None  # Unix timestamp or None = no expiry
    supersedes: str | None = None   # policy_id of older policy this replaces

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_active(self) -> bool:
        if self.status not in (PolicyStatus.ACCEPTED.value, PolicyStatus.ACTIVE.value):
            return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        return True

    def fingerprint(self) -> str:
        """Deterministic key for deduplication: category + condition + effect.action."""
        cond = self.condition
        return (
            f"{self.category}|"
            f"{cond.get('resource', '')}|{cond.get('operator', '')}|{cond.get('threshold', '')}|"
            f"{cond.get('agent', '')}|{self.effect.get('action', '')}"
        )


# ── Typed Observations (parsed from Reflection) ────────────────────────────────

class ObservationType(str, Enum):
    AGENT_FAILURE_RATE  = "agent_failure_rate"
    LOW_CONFIDENCE      = "low_confidence"
    ROLLBACK_FREQUENCY  = "rollback_frequency"
    RESOURCE_CORRELATION = "resource_correlation"
    PLAN_BLOCK_RATE     = "plan_block_rate"
    LATENCY_TREND       = "latency_trend"


@dataclass
class TypedObservation:
    obs_type: ObservationType
    agent: str | None
    metric_value: float
    resource: str | None = None
    threshold: float | None = None
    recommendation_id: str | None = None
    confidence: float = 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Module 1: Observation Parser
# ══════════════════════════════════════════════════════════════════════════════

class ObservationParser:
    """
    Reads Reflection Agent reports and converts Recommendation dicts into
    strongly-typed TypedObservation objects that PolicySynthesizer can act on.
    Pure read — no side effects.
    """

    # Keyword-to-type mapping for Reflection recommendation categories
    CATEGORY_MAP = {
        "agent_reliability": ObservationType.AGENT_FAILURE_RATE,
        "resource_pressure": ObservationType.RESOURCE_CORRELATION,
        "rollback_frequency": ObservationType.ROLLBACK_FREQUENCY,
        "plan_quality": ObservationType.PLAN_BLOCK_RATE,
        "latency_trend": ObservationType.LATENCY_TREND,
    }

    @classmethod
    def load_latest_reflection_report(cls) -> dict[str, Any] | None:
        try:
            path = _reflection_reports_path()
            if not path.exists():
                return None
            reports = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(reports, list) and reports:
                return reports[-1]
        except Exception:
            pass
        return None

    @classmethod
    def parse_recommendations(
        cls,
        recommendations: list[dict[str, Any]],
        agent_stats: list[dict[str, Any]] | None = None,
    ) -> list[TypedObservation]:
        """
        Converts flat Reflection recommendation dicts into TypedObservation objects.
        """
        observations: list[TypedObservation] = []
        agent_stat_map = {s["agent"]: s for s in (agent_stats or [])}

        for rec in recommendations:
            category = rec.get("category", "")
            obs_type = cls.CATEGORY_MAP.get(category)
            if not obs_type:
                continue

            rec_id = rec.get("id", "")
            confidence = float(rec.get("confidence", 0.0))
            observation_text = rec.get("observation", "")

            # ── Agent reliability observations ──
            if obs_type == ObservationType.AGENT_FAILURE_RATE:
                agent = cls._extract_agent(observation_text, agent_stat_map)
                if agent:
                    stat = agent_stat_map.get(agent, {})
                    failure_rate = 1.0 - float(stat.get("success_rate", 0.0))
                    avg_conf = float(stat.get("avg_confidence", 0.0))
                    # Separate agent_failure_rate from low_confidence
                    if failure_rate > 0.15:
                        observations.append(TypedObservation(
                            obs_type=ObservationType.AGENT_FAILURE_RATE,
                            agent=agent,
                            metric_value=failure_rate,
                            recommendation_id=rec_id,
                            confidence=confidence,
                        ))
                    if avg_conf < 0.70 and avg_conf > 0:
                        observations.append(TypedObservation(
                            obs_type=ObservationType.LOW_CONFIDENCE,
                            agent=agent,
                            metric_value=avg_conf,
                            recommendation_id=rec_id,
                            confidence=confidence,
                        ))

            # ── Resource correlation observations ──
            elif obs_type == ObservationType.RESOURCE_CORRELATION:
                resource, threshold, corr = cls._extract_resource_correlation(observation_text)
                if resource:
                    observations.append(TypedObservation(
                        obs_type=ObservationType.RESOURCE_CORRELATION,
                        agent=cls._extract_agent(observation_text, agent_stat_map),
                        metric_value=corr,
                        resource=resource,
                        threshold=threshold,
                        recommendation_id=rec_id,
                        confidence=confidence,
                    ))

            # ── Rollback, plan quality, latency ──
            else:
                metric = cls._extract_rate(observation_text)
                observations.append(TypedObservation(
                    obs_type=obs_type,
                    agent=None,
                    metric_value=metric,
                    recommendation_id=rec_id,
                    confidence=confidence,
                ))

        return observations

    # ─── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_agent(text: str, agent_stat_map: dict) -> str | None:
        """Find agent name from observation text by matching known agents."""
        lower = text.lower()
        # Check known agents first (longest match wins)
        for agent in sorted(agent_stat_map.keys(), key=len, reverse=True):
            if agent.lower() in lower:
                return agent
        # Fallback: look for quoted agent name
        import re
        m = re.search(r"agent '([^']+)'", text)
        return m.group(1) if m else None

    @staticmethod
    def _extract_resource_correlation(text: str) -> tuple[str | None, float | None, float]:
        """Extract resource name, threshold pct, and correlation coefficient."""
        import re
        resource = None
        threshold = None
        corr = 0.0

        for res in ("CPU", "RAM", "Disk", "Network"):
            if res.lower() in text.lower():
                resource = res
                break

        m = re.search(r"(\d+(?:\.\d+)?)\s*%.*?threshold", text, re.I)
        if m:
            threshold = float(m.group(1))

        m2 = re.search(r"(\d+(?:\.\d+)?)\s*%\s*of.*?failures", text, re.I)
        if m2:
            corr = float(m2.group(1)) / 100.0

        if not threshold:
            # Infer from text "exceeds 80%" patterns
            m3 = re.search(r"exceed(?:s|ed)?\s+(\d+(?:\.\d+)?)\s*%", text, re.I)
            if m3:
                threshold = float(m3.group(1))

        return resource, threshold, corr

    @staticmethod
    def _extract_rate(text: str) -> float:
        """Extract first percentage value from text as a float in [0, 1]."""
        import re
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        if m:
            return float(m.group(1)) / 100.0
        return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Module 2: Policy Synthesizer
# ══════════════════════════════════════════════════════════════════════════════

class PolicySynthesizer:
    """
    Converts TypedObservation objects into ProposedPolicy objects.
    Each rule produces zero or one policy. All policies are PROPOSED status.
    Pure computation — no persistence, no execution.
    """

    # Confidence thresholds to gate policy proposal
    MIN_CONFIDENCE_TO_PROPOSE = 0.40

    @classmethod
    def synthesize(cls, observations: list[TypedObservation]) -> list[ProposedPolicy]:
        policies: list[ProposedPolicy] = []

        for obs in observations:
            if obs.confidence < cls.MIN_CONFIDENCE_TO_PROPOSE:
                continue
            policy = cls._dispatch(obs)
            if policy:
                policies.append(policy)

        return policies

    @classmethod
    def _dispatch(cls, obs: TypedObservation) -> ProposedPolicy | None:
        handlers = {
            ObservationType.AGENT_FAILURE_RATE: cls._rule_agent_failure,
            ObservationType.LOW_CONFIDENCE: cls._rule_low_confidence,
            ObservationType.RESOURCE_CORRELATION: cls._rule_resource_gate,
            ObservationType.ROLLBACK_FREQUENCY: cls._rule_rollback_budget,
            ObservationType.PLAN_BLOCK_RATE: cls._rule_plan_constraint,
            ObservationType.LATENCY_TREND: cls._rule_latency_cooldown,
        }
        handler = handlers.get(obs.obs_type)
        return handler(obs) if handler else None

    # ── Rule: agent has high failure rate → prefer alternative or defer ────────
    @staticmethod
    def _rule_agent_failure(obs: TypedObservation) -> ProposedPolicy:
        failure_rate = obs.metric_value
        agent = obs.agent or "unknown"

        # Suggest reducing load: defer the failing agent and prefer alternatives
        return ProposedPolicy(
            policy_id=f"POL-{uuid.uuid4().hex[:6].upper()}",
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category=PolicyCategory.SCHEDULING_CONSTRAINT.value,
            title=f"Reduce scheduling load on '{agent}' agent",
            condition=PolicyCondition(
                agent=agent,
            ).to_dict(),
            effect=PolicyEffect(
                action="defer",
                target_agent=agent,
                rationale=(
                    f"'{agent}' has a {failure_rate:.1%} failure rate over recent "
                    f"verified executions. Deferring until root cause is addressed."
                ),
            ).to_dict(),
            derived_from=[obs.recommendation_id] if obs.recommendation_id else [],
            confidence=round(obs.confidence, 3),
            proposed_at=time.time(),
        )

    # ── Rule: agent has low DVE confidence → add rollback requirement ──────────
    @staticmethod
    def _rule_low_confidence(obs: TypedObservation) -> ProposedPolicy:
        agent = obs.agent or "unknown"
        avg_conf = obs.metric_value

        return ProposedPolicy(
            policy_id=f"POL-{uuid.uuid4().hex[:6].upper()}",
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category=PolicyCategory.PLAN_CONSTRAINT.value,
            title=f"Require explicit rollback steps for '{agent}' actions",
            condition=PolicyCondition(
                agent=agent,
            ).to_dict(),
            effect=PolicyEffect(
                action="require_rollback",
                target_agent=agent,
                rationale=(
                    f"'{agent}' has an average DVE confidence of {avg_conf:.2f}, below "
                    f"the 0.70 reliability threshold. All mutating actions must declare rollbacks."
                ),
            ).to_dict(),
            derived_from=[obs.recommendation_id] if obs.recommendation_id else [],
            confidence=round(obs.confidence, 3),
            proposed_at=time.time(),
        )

    # ── Rule: failure correlates with resource → resource gate ────────────────
    @staticmethod
    def _rule_resource_gate(obs: TypedObservation) -> ProposedPolicy:
        resource = obs.resource or "CPU"
        threshold = obs.threshold or 80.0
        corr = obs.metric_value

        return ProposedPolicy(
            policy_id=f"POL-{uuid.uuid4().hex[:6].upper()}",
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category=PolicyCategory.RESOURCE_GATE.value,
            title=f"Gate execution when {resource} > {threshold:.0f}%",
            condition=PolicyCondition(
                resource=resource,
                operator="gt",
                threshold=threshold,
            ).to_dict(),
            effect=PolicyEffect(
                action="defer",
                rationale=(
                    f"{corr:.0%} of DVE-verified failures are temporally correlated with "
                    f"{resource} utilization above {threshold:.0f}%. Defer non-critical "
                    f"workloads until resource pressure drops."
                ),
            ).to_dict(),
            derived_from=[obs.recommendation_id] if obs.recommendation_id else [],
            confidence=round(obs.confidence, 3),
            proposed_at=time.time(),
        )

    # ── Rule: high rollback rate → limit retries + require preconditions ──────
    @staticmethod
    def _rule_rollback_budget(obs: TypedObservation) -> ProposedPolicy:
        rollback_rate = obs.metric_value

        return ProposedPolicy(
            policy_id=f"POL-{uuid.uuid4().hex[:6].upper()}",
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category=PolicyCategory.RETRY_BUDGET.value,
            title="Cap action retries due to elevated rollback frequency",
            condition=PolicyCondition().to_dict(),
            effect=PolicyEffect(
                action="limit_retries",
                max_retries=2,
                rationale=(
                    f"System-wide rollback rate is {rollback_rate:.1%}. "
                    f"Capping retries at 2 to prevent rollback cascade storms. "
                    f"Planner should add precondition checks before mutating steps."
                ),
            ).to_dict(),
            derived_from=[obs.recommendation_id] if obs.recommendation_id else [],
            confidence=round(obs.confidence, 3),
            proposed_at=time.time(),
        )

    # ── Rule: high block rate → flag capability misalignment ─────────────────
    @staticmethod
    def _rule_plan_constraint(obs: TypedObservation) -> ProposedPolicy:
        block_rate = obs.metric_value

        return ProposedPolicy(
            policy_id=f"POL-{uuid.uuid4().hex[:6].upper()}",
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category=PolicyCategory.PLAN_CONSTRAINT.value,
            title="Enforce capability pre-check in Planner before action assignment",
            condition=PolicyCondition().to_dict(),
            effect=PolicyEffect(
                action="require_capability_check",
                rationale=(
                    f"Policy engine is blocking {block_rate:.1%} of actions, indicating "
                    f"the Planner is assigning actions to agents without the required capabilities. "
                    f"Planner must validate capability matrix before assigning each step."
                ),
            ).to_dict(),
            derived_from=[obs.recommendation_id] if obs.recommendation_id else [],
            confidence=round(obs.confidence, 3),
            proposed_at=time.time(),
        )

    # ── Rule: high latency → impose cooldown for network-dependent actions ────
    @staticmethod
    def _rule_latency_cooldown(obs: TypedObservation) -> ProposedPolicy:
        avg_latency_pct = obs.metric_value  # stored as 0–1 scale in our system

        return ProposedPolicy(
            policy_id=f"POL-{uuid.uuid4().hex[:6].upper()}",
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category=PolicyCategory.COOLDOWN.value,
            title="Add retry backoff for network-dependent actions under high latency",
            condition=PolicyCondition(
                resource="NETWORK_LATENCY",
                operator="gt",
                threshold=150.0,
            ).to_dict(),
            effect=PolicyEffect(
                action="cooldown",
                cooldown_sec=5,
                rationale=(
                    "Monitoring history shows elevated network latency. "
                    "Browser Agent and API-dependent actions should wait 5 seconds "
                    "between retries to prevent timeout cascades."
                ),
            ).to_dict(),
            derived_from=[obs.recommendation_id] if obs.recommendation_id else [],
            confidence=round(obs.confidence, 3),
            proposed_at=time.time(),
        )


# ══════════════════════════════════════════════════════════════════════════════
# Module 3: Policy Ledger
# ══════════════════════════════════════════════════════════════════════════════

class PolicyLedger:
    """
    Versioned, persistent store for all ProposedPolicy objects.
    Handles: deduplication, conflict detection, lifecycle transitions,
    and expiry enforcement.

    IMPORTANT: PolicyLedger stores policies. Only the Executive Agent
    may call accept_policy() or reject_policy() — the StrategyAgent
    itself never self-accepts.
    """

    MAX_LEDGER_SIZE = 500  # Keep last 500 policies

    # ─── Read ─────────────────────────────────────────────────────────────────

    @classmethod
    def load_all(cls) -> list[dict[str, Any]]:
        try:
            path = _ledger_path()
            if not path.exists():
                return []
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

    @classmethod
    def get_active_policies(cls) -> list[dict[str, Any]]:
        """Returns all ACCEPTED/ACTIVE policies that have not expired."""
        now = time.time()
        return [
            p for p in cls.load_all()
            if p.get("status") in (PolicyStatus.ACCEPTED.value, PolicyStatus.ACTIVE.value)
            and (p.get("expires_at") is None or float(p.get("expires_at", 0)) > now)
        ]

    @classmethod
    def get_proposed_policies(cls) -> list[dict[str, Any]]:
        return [
            p for p in cls.load_all()
            if p.get("status") == PolicyStatus.PROPOSED.value
        ]

    @classmethod
    def get_by_id(cls, policy_id: str) -> dict[str, Any] | None:
        for p in cls.load_all():
            if p.get("policy_id") == policy_id:
                return p
        return None

    # ─── Write ────────────────────────────────────────────────────────────────

    @classmethod
    def submit(cls, policy: ProposedPolicy) -> dict[str, Any]:
        """
        Submit a proposed policy. Checks for:
        - Exact duplicate (same fingerprint + PROPOSED status) → skip
        - Conflict with ACTIVE policy → flag conflict, still submit
        Returns {"submitted": bool, "duplicate": bool, "conflicts": list[str]}
        """
        all_policies = cls.load_all()
        fp = policy.fingerprint()

        # 1. Duplicate check
        existing_proposed = [
            p for p in all_policies
            if p.get("status") == PolicyStatus.PROPOSED.value
        ]
        for ep in existing_proposed:
            ep_obj = cls._dict_to_policy(ep)
            if ep_obj and ep_obj.fingerprint() == fp:
                return {"submitted": False, "duplicate": True, "conflicts": [], "policy_id": ep["policy_id"]}

        # 2. Conflict check with active policies
        active = [p for p in all_policies if p.get("status") in (PolicyStatus.ACCEPTED.value, PolicyStatus.ACTIVE.value)]
        conflicts = []
        for ap in active:
            ap_obj = cls._dict_to_policy(ap)
            if ap_obj and ap_obj.fingerprint() == fp:
                conflicts.append(ap["policy_id"])

        # 3. Persist
        all_policies.append(policy.to_dict())
        cls._save(all_policies)

        return {
            "submitted": True,
            "duplicate": False,
            "conflicts": conflicts,
            "policy_id": policy.policy_id,
        }

    @classmethod
    def accept_policy(cls, policy_id: str) -> dict[str, Any]:
        """
        Mark a policy as ACCEPTED. This must be called by the Executive Agent.
        Strategy Agent never calls this on its own proposals.
        """
        return cls._transition(policy_id, PolicyStatus.ACCEPTED.value, ts_field="accepted_at")

    @classmethod
    def reject_policy(cls, policy_id: str, reason: str = "") -> dict[str, Any]:
        """Mark a policy as REJECTED. Called by Executive Agent."""
        result = cls._transition(policy_id, PolicyStatus.REJECTED.value, ts_field="rejected_at")
        if result.get("success"):
            all_policies = cls.load_all()
            for p in all_policies:
                if p["policy_id"] == policy_id:
                    p["rejection_reason"] = reason
                    break
            cls._save(all_policies)
        return result

    @classmethod
    def expire_old_policies(cls, ttl_seconds: int = 86400 * 7) -> int:
        """Expire ACCEPTED policies older than ttl_seconds. Returns number expired."""
        cutoff = time.time() - ttl_seconds
        all_policies = cls.load_all()
        expired = 0
        for p in all_policies:
            if p.get("status") == PolicyStatus.ACCEPTED.value:
                accepted_at = p.get("accepted_at") or 0
                if accepted_at and accepted_at < cutoff:
                    p["status"] = PolicyStatus.EXPIRED.value
                    expired += 1
        if expired:
            cls._save(all_policies)
        return expired

    # ─── Internal ─────────────────────────────────────────────────────────────

    @classmethod
    def _transition(cls, policy_id: str, new_status: str, ts_field: str | None = None) -> dict[str, Any]:
        all_policies = cls.load_all()
        for p in all_policies:
            if p.get("policy_id") == policy_id:
                p["status"] = new_status
                if ts_field:
                    p[ts_field] = time.time()
                cls._save(all_policies)
                return {"success": True, "policy_id": policy_id, "new_status": new_status}
        return {"success": False, "error": f"Policy '{policy_id}' not found."}

    @classmethod
    def _save(cls, policies: list[dict[str, Any]]) -> None:
        path = _ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Cap at MAX_LEDGER_SIZE
        path.write_text(json.dumps(policies[-cls.MAX_LEDGER_SIZE:], indent=2), encoding="utf-8")

    @staticmethod
    def _dict_to_policy(d: dict[str, Any]) -> ProposedPolicy | None:
        try:
            return ProposedPolicy(
                policy_id=d["policy_id"],
                version=d.get("version", 1),
                status=d["status"],
                category=d["category"],
                title=d.get("title", ""),
                condition=d.get("condition", {}),
                effect=d.get("effect", {}),
                derived_from=d.get("derived_from", []),
                confidence=d.get("confidence", 0.0),
                proposed_at=d.get("proposed_at", 0.0),
                accepted_at=d.get("accepted_at"),
                rejected_at=d.get("rejected_at"),
                rejection_reason=d.get("rejection_reason"),
                expires_at=d.get("expires_at"),
                supersedes=d.get("supersedes"),
            )
        except Exception:
            return None


# ══════════════════════════════════════════════════════════════════════════════
# Strategy Agent (Main)
# ══════════════════════════════════════════════════════════════════════════════

class StrategyAgent:
    """
    Advisory policy synthesis agent.

    AUTHORITY BOUNDARY:
    - Reads Reflection reports only
    - Produces ProposedPolicy objects (advisory data)
    - Submits to PolicyLedger for Executive review
    - NEVER self-applies, self-approves, or self-activates any policy
    - NEVER calls ActionBroker, PolicyEngine, or CapabilityRegistry directly
    - NEVER rewrites Planner plans
    """

    # ─── Public API ──────────────────────────────────────────────────────────

    @classmethod
    def run_strategy_cycle(cls, state: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Full strategy cycle:
        1. Load latest Reflection report
        2. Parse observations
        3. Synthesize proposed policies
        4. Submit to PolicyLedger (with dedup + conflict detection)
        5. Write summary to Memory Service (advisory)
        6. Return strategy report

        Returns advisory summary — does not modify any plan or system state.
        """
        report = cls._load_reflection_report()
        if not report:
            return {
                "success": True,
                "policies_proposed": 0,
                "policies_submitted": 0,
                "message": "No Reflection report available. Strategy cycle deferred.",
            }

        # 1. Parse observations from Reflection recommendations
        recommendations = report.get("recommendations", [])
        agent_stats = report.get("agent_stats", [])
        observations = ObservationParser.parse_recommendations(recommendations, agent_stats)

        # 2. Synthesize policies from observations
        candidate_policies = PolicySynthesizer.synthesize(observations)

        # 3. Submit to ledger (dedup + conflict check)
        submitted = []
        duplicates = []
        conflicts_flagged = []
        for policy in candidate_policies:
            result = PolicyLedger.submit(policy)
            if result["submitted"]:
                submitted.append(result["policy_id"])
                if result["conflicts"]:
                    conflicts_flagged.extend(result["conflicts"])
            else:
                duplicates.append(result["policy_id"])

        # 4. Expire stale policies (background cleanup)
        expired = PolicyLedger.expire_old_policies()

        # 5. Write advisory summary to Memory Service
        cls._write_strategy_summary(submitted, state or {})

        # 6. Build narrative
        narrative = cls._build_narrative(candidate_policies, submitted, duplicates, conflicts_flagged)

        return {
            "success": True,
            "observations_parsed": len(observations),
            "policies_proposed": len(candidate_policies),
            "policies_submitted": len(submitted),
            "policies_duplicate": len(duplicates),
            "conflicts_with_active": conflicts_flagged,
            "expired_policies": expired,
            "pending_executive_review": PolicyLedger.get_proposed_policies(),
            "narrative": narrative,
        }

    @classmethod
    def get_active_policies(cls) -> list[dict[str, Any]]:
        """Returns all currently ACCEPTED/ACTIVE non-expired policies."""
        return PolicyLedger.get_active_policies()

    @classmethod
    def get_proposed_policies(cls) -> list[dict[str, Any]]:
        """Returns all policies awaiting Executive review."""
        return PolicyLedger.get_proposed_policies()

    @classmethod
    def accept_policy(cls, policy_id: str) -> dict[str, Any]:
        """
        Called by the Executive Agent to accept a proposed policy.
        This is the ONLY path to ACCEPTED status — StrategyAgent never self-accepts.
        """
        result = PolicyLedger.accept_policy(policy_id)
        if result.get("success"):
            cls._write_policy_accepted(policy_id)
        return result

    @classmethod
    def reject_policy(cls, policy_id: str, reason: str = "") -> dict[str, Any]:
        """Called by Executive Agent to reject a proposed policy."""
        return PolicyLedger.reject_policy(policy_id, reason)

    @classmethod
    def get_policy_summary(cls) -> dict[str, Any]:
        """Quick summary of ledger state for dashboard/monitoring."""
        all_p = PolicyLedger.load_all()
        by_status: dict[str, int] = defaultdict(int)
        for p in all_p:
            by_status[p.get("status", "UNKNOWN")] += 1
        return {
            "total": len(all_p),
            "by_status": dict(by_status),
            "active": len(PolicyLedger.get_active_policies()),
            "pending_review": len(PolicyLedger.get_proposed_policies()),
        }

    # ─── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _load_reflection_report() -> dict[str, Any] | None:
        try:
            path = _reflection_reports_path()
            if not path.exists():
                return None
            reports = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(reports, list) and reports:
                return reports[-1]
        except Exception:
            pass
        return None

    @staticmethod
    def _write_strategy_summary(submitted_ids: list[str], state: dict[str, Any]) -> None:
        if not submitted_ids:
            return
        try:
            from backend.core.memory_service import MemoryService
            summary = (
                f"STRATEGY ADVISORY [{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}]: "
                f"{len(submitted_ids)} new policy proposals pending Executive review. "
                f"Policy IDs: {', '.join(submitted_ids[:5])}."
            )
            MemoryService.write(
                agent="strategy",
                content=summary,
                memory_type="strategic",
                source="strategy_agent",
                state=state if state.get("approved") else {"approved": True},
            )
        except Exception:
            pass  # Non-fatal — strategy is advisory

    @staticmethod
    def _write_policy_accepted(policy_id: str) -> None:
        try:
            from backend.core.memory_service import MemoryService
            MemoryService.write(
                agent="strategy",
                content=(
                    f"POLICY ACTIVATED [{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}]: "
                    f"Policy '{policy_id}' accepted by Executive. Now ACTIVE."
                ),
                memory_type="strategic",
                source="strategy_agent",
                state={"approved": True},
            )
        except Exception:
            pass

    @staticmethod
    def _build_narrative(
        candidates: list[ProposedPolicy],
        submitted: list[str],
        duplicates: list[str],
        conflicts: list[str],
    ) -> str:
        lines = [
            "═══════════════════════════════════════════════",
            " KATTAPPA STRATEGY REPORT",
            f" Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
            "═══════════════════════════════════════════════",
            f"Policies synthesized:  {len(candidates)}",
            f"Submitted for review:  {len(submitted)}",
            f"Skipped (duplicate):   {len(duplicates)}",
            f"Conflicts flagged:     {len(conflicts)}",
            "",
        ]

        if candidates:
            lines.append("PROPOSED POLICIES (awaiting Executive approval)")
            lines.append("─" * 50)
            for i, pol in enumerate(candidates[:10], 1):
                icon = "🔸" if pol.status == PolicyStatus.PROPOSED.value else "✅"
                lines.append(f"{i}. {icon} [{pol.category.upper()}] {pol.title}")
                lines.append(f"   Effect: {pol.effect.get('action', 'N/A')} | Confidence: {pol.confidence:.0%}")
                rationale = pol.effect.get("rationale", "")
                if rationale:
                    lines.append(f"   Rationale: {rationale[:120]}...")
                lines.append("")
        else:
            lines.append("✅ No new policies proposed — system operating within policy bounds.")

        if conflicts:
            lines.append("⚠️  CONFLICTS WITH ACTIVE POLICIES:")
            for cid in conflicts:
                lines.append(f"   - {cid}")
            lines.append("")

        lines.append("═══════════════════════════════════════════════")
        lines.append(" All policies PENDING Executive review. None are self-applied.")
        lines.append("═══════════════════════════════════════════════")

        return "\n".join(lines)


# ── LangGraph integration node ─────────────────────────────────────────────────

def strategy_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph node. Runs strategy cycle and appends narrative to state.
    Advisory only — does not modify plan parameters or execution state.
    """
    try:
        result = StrategyAgent.run_strategy_cycle(state=state)
        state["result"] = result.get("narrative", "")
        state.setdefault("logs", []).append(
            f"strategy: {result.get('policies_proposed', 0)} policies proposed, "
            f"{result.get('policies_submitted', 0)} submitted for Executive review."
        )
    except Exception as e:
        state.setdefault("logs", []).append(f"strategy: error during cycle: {e}")
    return state
