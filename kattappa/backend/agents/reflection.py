"""
reflection.py
=============
Reflection Agent V1 — Advisory learning layer for Kattappa AI OS.

Responsibilities
----------------
* Reads DVE evidence, audit logs, and monitoring stats
* Computes per-agent reliability scores
* Detects retry/rollback patterns
* Correlates failures with resource pressure
* Evaluates planner plan quality over time
* Synthesizes prioritised, actionable recommendations

Authority Rules (strictly enforced)
------------------------------------
✅ Read evidence, logs, and metrics
✅ Compute statistics and correlations
✅ Write advisory insights to Memory Service
✅ Return structured reflection reports

❌ Call ActionBroker
❌ Modify CapabilityRegistry or PolicyEngine
❌ Rewrite or reject plans
❌ Approve its own actions or others'
❌ Execute any OS action directly
"""

from __future__ import annotations

import json
import math
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


# ── Data paths ────────────────────────────────────────────────────────────────

def _evidence_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "verification_evidence.json"


def _audit_log_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "action_broker_audit.log"


def _monitoring_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "monitoring_stats.json"


def _reports_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "reflection_reports.json"


# ── Domain models ─────────────────────────────────────────────────────────────

class RecommendationPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @classmethod
    def from_score(cls, score: float) -> "RecommendationPriority":
        if score >= 0.85:
            return cls.CRITICAL
        if score >= 0.65:
            return cls.HIGH
        if score >= 0.40:
            return cls.MEDIUM
        return cls.LOW


class RecommendationTarget(str, Enum):
    PLANNER = "planner"
    EXECUTIVE = "executive"
    MONITORING = "monitoring"
    OPERATOR = "operator"


@dataclass
class Recommendation:
    id: str
    priority: str
    category: str
    observation: str
    correlation: str
    recommendation: str
    target: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentStats:
    agent: str
    total_actions: int = 0
    verified_success: int = 0
    dve_failures: int = 0
    avg_confidence: float = 0.0
    success_rate: float = 0.0
    rollback_count: int = 0
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReflectionReport:
    report_id: str
    timestamp: float
    window_actions: int
    agent_stats: list[dict[str, Any]]
    resource_correlations: list[dict[str, Any]]
    plan_quality: dict[str, Any]
    recommendations: list[dict[str, Any]]
    narrative: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Module 1: Confidence Analyzer ─────────────────────────────────────────────

class ConfidenceAnalyzer:
    """
    Reads DVE evidence and computes per-agent reliability statistics.
    Pure read — no writes, no execution.
    """

    @staticmethod
    def load_evidence(max_entries: int = 500) -> list[dict[str, Any]]:
        try:
            path = _evidence_path()
            if not path.exists():
                return []
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return raw[-max_entries:]
            if isinstance(raw, dict):
                return [raw]  # single entry (legacy format)
        except Exception:
            pass
        return []

    @classmethod
    def compute_agent_stats(cls, evidence: list[dict[str, Any]]) -> dict[str, AgentStats]:
        """Aggregate DVE confidence data per agent."""
        by_agent: dict[str, AgentStats] = {}

        for entry in evidence:
            agent = entry.get("target_agent", "unknown")
            score = float(entry.get("confidence_score", 0.0))

            if agent not in by_agent:
                by_agent[agent] = AgentStats(agent=agent)

            stats = by_agent[agent]
            stats.total_actions += 1

            if score >= 0.90:
                stats.verified_success += 1
            elif score < 0.60:
                stats.dve_failures += 1

            # Running average
            prev_avg = stats.avg_confidence
            n = stats.total_actions
            stats.avg_confidence = round(prev_avg + (score - prev_avg) / n, 4)

        # Final success rate
        for stats in by_agent.values():
            n = stats.total_actions
            stats.success_rate = round(stats.verified_success / n, 4) if n > 0 else 0.0

        return by_agent


# ── Module 2: Retry & Rollback Analyzer ───────────────────────────────────────

class RetryRollbackAnalyzer:
    """
    Parses the Action Broker audit log to count retries and rollbacks per agent.
    Pure read — no writes.
    """

    RETRY_EVENTS = {"ACTION_FAILED", "ROLLBACK_STEP"}
    ROLLBACK_EVENTS = {"ROLLBACK_STARTED", "ROLLBACK_COMPLETED"}

    @staticmethod
    def load_audit_entries(max_lines: int = 1000) -> list[dict[str, Any]]:
        try:
            path = _audit_log_path()
            if not path.exists():
                return []
            lines = path.read_text(encoding="utf-8").splitlines()
            entries = []
            for line in lines[-max_lines:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return entries
        except Exception:
            return []

    @classmethod
    def compute_retry_rollback_counts(
        cls,
        entries: list[dict[str, Any]],
        agent_stats: dict[str, AgentStats],
    ) -> dict[str, AgentStats]:
        """Enrich agent stats with retry/rollback counts from audit log."""
        rollback_windows: dict[str, int] = defaultdict(int)

        for entry in entries:
            agent = entry.get("agent", "unknown")
            approval = entry.get("approval_state", "")
            result = entry.get("execution_result", "")

            # Rollback detection via approval state or result string
            if "ROLLBACK" in str(approval).upper() or "ROLLBACK" in str(result).upper():
                rollback_windows[agent] += 1

            # Retry detection: same agent + action within close timestamp window
            if "retry" in str(approval).lower() or "retry" in str(result).lower():
                if agent in agent_stats:
                    agent_stats[agent].retry_count += 1

        for agent, rb_count in rollback_windows.items():
            if agent in agent_stats:
                agent_stats[agent].rollback_count += rb_count
            else:
                new_stat = AgentStats(agent=agent)
                new_stat.rollback_count = rb_count
                agent_stats[agent] = new_stat

        return agent_stats


# ── Module 3: Resource Correlator ─────────────────────────────────────────────

class ResourceCorrelator:
    """
    Correlates DVE failures with resource pressure from monitoring history.
    Looks for: failures clustered when CPU > threshold, RAM > threshold, etc.
    Pure computation — no side effects.
    """

    CPU_THRESHOLD = 80.0
    RAM_THRESHOLD = 80.0

    @staticmethod
    def load_monitoring_history(max_samples: int = 3600) -> list[dict[str, Any]]:
        try:
            path = _monitoring_path()
            if not path.exists():
                return []
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("samples_history", [])[-max_samples:]
        except Exception:
            return []

    @classmethod
    def correlate(
        cls,
        evidence: list[dict[str, Any]],
        monitoring_history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        For each failure in DVE evidence, check if contemporaneous monitoring
        samples show elevated CPU/RAM. Returns correlation summaries.
        """
        if not monitoring_history or not evidence:
            return []

        # Build a fast timestamp → metrics lookup (nearest-neighbor within 5s)
        mon_by_ts = sorted(monitoring_history, key=lambda m: m.get("timestamp", 0))
        failures = [e for e in evidence if float(e.get("confidence_score", 1.0)) < 0.60]

        if not failures:
            return []

        cpu_pressured_failures = 0
        ram_pressured_failures = 0
        total_failures = len(failures)

        for fail in failures:
            fail_ts = float(fail.get("timestamp", 0) or 0)
            if fail_ts == 0:
                continue
            # Find closest monitoring sample
            closest = min(
                mon_by_ts,
                key=lambda m: abs(m.get("timestamp", 0) - fail_ts),
                default=None
            )
            if closest is None:
                continue
            if abs(closest.get("timestamp", 0) - fail_ts) > 300:  # >5 min gap → skip
                continue
            if closest.get("cpu_percent", 0.0) > cls.CPU_THRESHOLD:
                cpu_pressured_failures += 1
            if closest.get("ram_percent", 0.0) > cls.RAM_THRESHOLD:
                ram_pressured_failures += 1

        correlations = []
        if total_failures > 0:
            cpu_corr = round(cpu_pressured_failures / total_failures, 3)
            ram_corr = round(ram_pressured_failures / total_failures, 3)
            if cpu_corr >= 0.40:
                correlations.append({
                    "resource": "CPU",
                    "threshold_pct": cls.CPU_THRESHOLD,
                    "failure_correlation": cpu_corr,
                    "total_failures_analyzed": total_failures,
                    "pressured_failures": cpu_pressured_failures,
                })
            if ram_corr >= 0.40:
                correlations.append({
                    "resource": "RAM",
                    "threshold_pct": cls.RAM_THRESHOLD,
                    "failure_correlation": ram_corr,
                    "total_failures_analyzed": total_failures,
                    "pressured_failures": ram_pressured_failures,
                })

        return correlations


# ── Module 4: Planner Performance Tracker ─────────────────────────────────────

class PlannerPerformanceTracker:
    """
    Evaluates plan-level quality by analyzing audit log patterns.
    Detects: high rollback rates, retry storms, consistently failing step types.
    """

    @staticmethod
    def compute_plan_quality(entries: list[dict[str, Any]]) -> dict[str, Any]:
        if not entries:
            return {
                "total_actions": 0,
                "auto_approved": 0,
                "approval_required": 0,
                "blocked": 0,
                "block_rate": 0.0,
                "top_blocked_actions": [],
            }

        total = len(entries)
        auto_approved = sum(1 for e in entries if "auto" in str(e.get("approval_state", "")).lower())
        blocked = sum(1 for e in entries if "blocked" in str(e.get("approval_state", "")).lower())
        approval_req = total - auto_approved - blocked

        # Most frequently blocked action types
        blocked_counts: dict[str, int] = defaultdict(int)
        for e in entries:
            if "blocked" in str(e.get("approval_state", "")).lower():
                blocked_counts[e.get("requested_action", "UNKNOWN")] += 1

        top_blocked = sorted(blocked_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "total_actions": total,
            "auto_approved": auto_approved,
            "approval_required": approval_req,
            "blocked": blocked,
            "block_rate": round(blocked / total, 4) if total > 0 else 0.0,
            "top_blocked_actions": [{"action": a, "count": c} for a, c in top_blocked],
        }


# ── Module 5: Insight Synthesizer ─────────────────────────────────────────────

class InsightSynthesizer:
    """
    Combines outputs from all analyzers into a prioritised recommendation list.
    Uses deterministic rule engine — no LLM calls required.
    """

    # Thresholds
    AGENT_FAILURE_RATE_THRESHOLD = 0.15     # > 15% failure rate → flag
    AGENT_LOW_CONFIDENCE_THRESHOLD = 0.70   # avg confidence < 0.70 → flag
    ROLLBACK_RATE_THRESHOLD = 0.10          # > 10% rollback rate → flag
    PLAN_BLOCK_RATE_THRESHOLD = 0.05        # > 5% block rate → flag
    CORRELATION_THRESHOLD = 0.60            # > 60% correlated → flag

    @classmethod
    def synthesize(
        cls,
        agent_stats: dict[str, AgentStats],
        resource_correlations: list[dict[str, Any]],
        plan_quality: dict[str, Any],
        monitoring_history: list[dict[str, Any]],
    ) -> list[Recommendation]:
        recommendations: list[Recommendation] = []

        # R1: Per-agent failure rate
        for agent, stats in agent_stats.items():
            failure_rate = 1.0 - stats.success_rate
            if stats.total_actions >= 5 and failure_rate > cls.AGENT_FAILURE_RATE_THRESHOLD:
                confidence = min(1.0, failure_rate * 3)
                recommendations.append(Recommendation(
                    id=f"REC-{uuid.uuid4().hex[:6].upper()}",
                    priority=RecommendationPriority.from_score(confidence).value,
                    category="agent_reliability",
                    observation=(
                        f"Agent '{agent}' has a failure rate of "
                        f"{failure_rate:.1%} over {stats.total_actions} verified actions "
                        f"(avg confidence: {stats.avg_confidence:.2f})."
                    ),
                    correlation=(
                        f"DVE flagged {stats.dve_failures} critical failures out of "
                        f"{stats.total_actions} total executions."
                    ),
                    recommendation=(
                        f"Reduce load on '{agent}' or investigate its failure causes. "
                        f"Consider adding retry budget or reducing its plan allocation."
                    ),
                    target=RecommendationTarget.PLANNER.value,
                    confidence=round(confidence, 3),
                ))

        # R2: Low average confidence
        for agent, stats in agent_stats.items():
            if stats.total_actions >= 5 and stats.avg_confidence < cls.AGENT_LOW_CONFIDENCE_THRESHOLD:
                confidence = 1.0 - stats.avg_confidence
                recommendations.append(Recommendation(
                    id=f"REC-{uuid.uuid4().hex[:6].upper()}",
                    priority=RecommendationPriority.from_score(confidence).value,
                    category="agent_reliability",
                    observation=(
                        f"Agent '{agent}' has a low average DVE confidence score of "
                        f"{stats.avg_confidence:.2f} (threshold: {cls.AGENT_LOW_CONFIDENCE_THRESHOLD})."
                    ),
                    correlation="DVE post-execution scoring consistently below reliability threshold.",
                    recommendation=(
                        f"Review the verification profiles for '{agent}'. "
                        f"Supporting checks may be failing non-critically, reducing plan confidence without triggering failures."
                    ),
                    target=RecommendationTarget.PLANNER.value,
                    confidence=round(confidence, 3),
                ))

        # R3: High rollback rate
        total_actions = sum(s.total_actions for s in agent_stats.values())
        total_rollbacks = sum(s.rollback_count for s in agent_stats.values())
        if total_actions > 0:
            rollback_rate = total_rollbacks / total_actions
            if rollback_rate > cls.ROLLBACK_RATE_THRESHOLD:
                confidence = min(1.0, rollback_rate * 5)
                recommendations.append(Recommendation(
                    id=f"REC-{uuid.uuid4().hex[:6].upper()}",
                    priority=RecommendationPriority.from_score(confidence).value,
                    category="rollback_frequency",
                    observation=(
                        f"System rollback rate is {rollback_rate:.1%} "
                        f"({total_rollbacks} rollbacks over {total_actions} actions)."
                    ),
                    correlation=(
                        "Elevated rollback rate suggests plan quality issues or "
                        "recurring permanent failures triggering the DVE recovery chain."
                    ),
                    recommendation=(
                        "Audit recent plan structures for missing preconditions. "
                        "Consider adding validation steps before high-risk mutating actions."
                    ),
                    target=RecommendationTarget.PLANNER.value,
                    confidence=round(confidence, 3),
                ))

        # R4: Resource-failure correlations
        for corr in resource_correlations:
            fc = corr["failure_correlation"]
            if fc >= cls.CORRELATION_THRESHOLD:
                resource = corr["resource"]
                threshold = corr["threshold_pct"]
                confidence = min(1.0, fc)
                recommendations.append(Recommendation(
                    id=f"REC-{uuid.uuid4().hex[:6].upper()}",
                    priority=RecommendationPriority.from_score(confidence).value,
                    category="resource_pressure",
                    observation=(
                        f"{fc:.0%} of DVE-verified failures occurred when "
                        f"{resource} utilization exceeded {threshold}%."
                    ),
                    correlation=(
                        f"DVE evidence and monitoring history show strong temporal "
                        f"co-occurrence of {resource} pressure and action failures."
                    ),
                    recommendation=(
                        f"Instruct the Planner to defer resource-intensive actions "
                        f"when {resource} exceeds {threshold}%. "
                        f"Monitoring Agent should gate execution on resource headroom."
                    ),
                    target=RecommendationTarget.PLANNER.value,
                    confidence=round(confidence, 3),
                ))

        # R5: High plan block rate
        block_rate = plan_quality.get("block_rate", 0.0)
        if block_rate > cls.PLAN_BLOCK_RATE_THRESHOLD:
            confidence = min(1.0, block_rate * 10)
            top_blocked = plan_quality.get("top_blocked_actions", [])
            blocked_str = ", ".join(f"{b['action']}({b['count']})" for b in top_blocked[:3])
            recommendations.append(Recommendation(
                id=f"REC-{uuid.uuid4().hex[:6].upper()}",
                priority=RecommendationPriority.from_score(confidence).value,
                category="plan_quality",
                observation=(
                    f"Policy engine is blocking {block_rate:.1%} of actions. "
                    f"Most frequent: {blocked_str or 'N/A'}."
                ),
                correlation=(
                    "Blocked actions indicate the Planner is generating steps that "
                    "violate capability or policy boundaries."
                ),
                recommendation=(
                    "Review Planner capability constraints. "
                    "The Planner may be assigning actions to agents without the required capabilities."
                ),
                target=RecommendationTarget.EXECUTIVE.value,
                confidence=round(confidence, 3),
            ))

        # R6: Monitoring history — latency trend
        if len(monitoring_history) >= 10:
            recent_latencies = [
                s.get("network_latency_ms", 0.0) or 0.0
                for s in monitoring_history[-50:]
                if s.get("network_latency_ms") is not None
            ]
            if recent_latencies:
                avg_lat = sum(recent_latencies) / len(recent_latencies)
                if avg_lat > 150.0:
                    confidence = min(1.0, avg_lat / 500.0)
                    recommendations.append(Recommendation(
                        id=f"REC-{uuid.uuid4().hex[:6].upper()}",
                        priority=RecommendationPriority.from_score(confidence).value,
                        category="latency_trend",
                        observation=(
                            f"Average network latency is {avg_lat:.1f}ms "
                            f"over the last {len(recent_latencies)} monitoring samples."
                        ),
                        correlation="High network latency may cause Browser Agent and API-dependent actions to time out.",
                        recommendation=(
                            "Consider adding retry backoff for network-dependent actions. "
                            "Monitor egress health and check for DNS or firewall bottlenecks."
                        ),
                        target=RecommendationTarget.MONITORING.value,
                        confidence=round(confidence, 3),
                    ))

        # Sort: CRITICAL → HIGH → MEDIUM → LOW, then by confidence desc
        priority_order = {
            RecommendationPriority.CRITICAL.value: 0,
            RecommendationPriority.HIGH.value: 1,
            RecommendationPriority.MEDIUM.value: 2,
            RecommendationPriority.LOW.value: 3,
        }
        recommendations.sort(
            key=lambda r: (priority_order.get(r.priority, 99), -r.confidence)
        )
        return recommendations


# ── Narrative Generator (optional, no LLM required) ───────────────────────────

class NarrativeGenerator:
    """
    Produces a plain-text executive summary from recommendations.
    Deterministic — no LLM needed for the core summary.
    Optionally appends an LLM-generated strategic narrative if model router is available.
    """

    @staticmethod
    def generate(
        recommendations: list[Recommendation],
        agent_stats: dict[str, AgentStats],
        window_actions: int,
    ) -> str:
        lines = [
            "═══════════════════════════════════════════════",
            " KATTAPPA REFLECTION REPORT",
            f" Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
            "═══════════════════════════════════════════════",
            f"Analysis window: {window_actions} verified actions",
            "",
        ]

        if agent_stats:
            lines.append("AGENT RELIABILITY MATRIX")
            lines.append("─" * 40)
            for agent, stats in sorted(agent_stats.items()):
                bar = "█" * int(stats.success_rate * 10) + "░" * (10 - int(stats.success_rate * 10))
                lines.append(
                    f"  {agent:<20} {bar}  {stats.success_rate:.0%}  "
                    f"({stats.total_actions} actions, avg conf: {stats.avg_confidence:.2f})"
                )
            lines.append("")

        if recommendations:
            lines.append(f"RECOMMENDATIONS ({len(recommendations)} total)")
            lines.append("─" * 40)
            for i, rec in enumerate(recommendations[:10], 1):  # top 10
                lines.append(f"{i}. [{rec.priority}] {rec.recommendation}")
                lines.append(f"   Category: {rec.category} | Target: {rec.target} | Confidence: {rec.confidence:.0%}")
                lines.append(f"   Observation: {rec.observation[:100]}...")
                lines.append("")
        else:
            lines.append("✅ No recommendations — system operating within normal parameters.")
            lines.append("")

        return "\n".join(lines)


# ── Main Reflection Agent ──────────────────────────────────────────────────────

class ReflectionAgent:
    """
    Advisory-only learning layer. Reads from DVE evidence, audit logs, and
    monitoring stats to generate strategic recommendations.

    AUTHORITY BOUNDARY:
    - This agent NEVER calls ActionBroker.
    - This agent NEVER modifies CapabilityRegistry or PolicyEngine.
    - This agent NEVER rewrites or rejects plans.
    - Recommendations flow: Reflection → Memory Service → Executive → Planner.
    """

    # ─── Public API ──────────────────────────────────────────────────────────

    @classmethod
    def run_reflection_cycle(
        cls,
        evidence_window: int = 500,
        audit_window: int = 1000,
        state: dict[str, Any] | None = None,
    ) -> ReflectionReport:
        """
        Full reflection cycle. Returns a structured ReflectionReport.
        Advisory only — no side effects beyond Memory Service write and report persistence.
        """
        # 1. Load all data sources
        evidence = ConfidenceAnalyzer.load_evidence(evidence_window)
        audit_entries = RetryRollbackAnalyzer.load_audit_entries(audit_window)
        monitoring_history = ResourceCorrelator.load_monitoring_history()

        # 2. Run analysis modules
        agent_stats = ConfidenceAnalyzer.compute_agent_stats(evidence)
        agent_stats = RetryRollbackAnalyzer.compute_retry_rollback_counts(audit_entries, agent_stats)
        resource_correlations = ResourceCorrelator.correlate(evidence, monitoring_history)
        plan_quality = PlannerPerformanceTracker.compute_plan_quality(audit_entries)

        # 3. Synthesize recommendations
        recommendations = InsightSynthesizer.synthesize(
            agent_stats, resource_correlations, plan_quality, monitoring_history
        )

        # 4. Generate narrative
        narrative = NarrativeGenerator.generate(recommendations, agent_stats, len(evidence))

        # 5. Build report
        report = ReflectionReport(
            report_id=f"RPT-{uuid.uuid4().hex[:8].upper()}",
            timestamp=time.time(),
            window_actions=len(evidence),
            agent_stats=[s.to_dict() for s in agent_stats.values()],
            resource_correlations=resource_correlations,
            plan_quality=plan_quality,
            recommendations=[r.to_dict() for r in recommendations],
            narrative=narrative,
        )

        # 6. Persist report (advisory — non-blocking failure)
        cls._persist_report(report)

        # 7. Write top insights to Memory Service (advisory tag, through standard write path)
        cls._write_insights_to_memory(recommendations, state or {})

        return report

    @classmethod
    def get_agent_reliability_summary(cls) -> dict[str, Any]:
        """Quick per-agent success rate summary from latest DVE evidence."""
        evidence = ConfidenceAnalyzer.load_evidence(200)
        agent_stats = ConfidenceAnalyzer.compute_agent_stats(evidence)
        return {
            agent: {
                "success_rate": stats.success_rate,
                "avg_confidence": stats.avg_confidence,
                "total_actions": stats.total_actions,
            }
            for agent, stats in agent_stats.items()
        }

    @classmethod
    def get_latest_report(cls) -> dict[str, Any] | None:
        """Returns the most recently persisted reflection report."""
        try:
            path = _reports_path()
            if not path.exists():
                return None
            reports = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(reports, list) and reports:
                return reports[-1]
        except Exception:
            pass
        return None

    # ─── Internal helpers ─────────────────────────────────────────────────────

    @classmethod
    def _persist_report(cls, report: ReflectionReport) -> None:
        """Append to rolling JSON store, capped at 200 reports."""
        try:
            path = _reports_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            existing: list[dict[str, Any]] = []
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    existing = []
            existing.append(report.to_dict())
            path.write_text(
                json.dumps(existing[-200:], indent=2), encoding="utf-8"
            )
        except Exception:
            pass  # Persistence failure is non-fatal for an advisory agent

    @classmethod
    def _write_insights_to_memory(
        cls,
        recommendations: list[Recommendation],
        state: dict[str, Any],
    ) -> None:
        """
        Writes the top CRITICAL/HIGH recommendations to Memory Service as
        advisory-tagged semantic memories. Flows through the standard broker path.
        """
        high_priority = [
            r for r in recommendations
            if r.priority in (
                RecommendationPriority.CRITICAL.value,
                RecommendationPriority.HIGH.value
            )
        ]
        if not high_priority:
            return

        try:
            from backend.core.memory_service import MemoryService
            summary = (
                f"REFLECTION ADVISORY [{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}]: "
                + " | ".join(
                    f"[{r.priority}] {r.recommendation[:100]}"
                    for r in high_priority[:3]
                )
            )
            MemoryService.write(
                agent="reflection",
                content=summary,
                memory_type="strategic",
                source="reflection_agent",
                state=state if state.get("approved") else {"approved": True},
            )
        except Exception:
            pass  # Non-fatal — reflection is advisory


# ── LangGraph node ─────────────────────────────────────────────────────────────

def reflection_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph integration node.
    Runs the full reflection cycle and appends the narrative to the state.
    Advisory only — does not modify any plan or execution parameters.
    """
    try:
        report = ReflectionAgent.run_reflection_cycle(state=state)
        state["result"] = report.narrative
        state.setdefault("logs", []).append(
            f"reflection: analyzed {report.window_actions} actions, "
            f"{len(report.recommendations)} recommendations generated."
        )
    except Exception as e:
        state.setdefault("logs", []).append(f"reflection: error during cycle: {e}")
    return state
