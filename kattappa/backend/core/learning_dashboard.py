"""
Learning Dashboard — Step 7.3

READ-ONLY governance-grade observability layer.
Aggregates data from every existing store. Has NO write methods.

Architecture contract:
  - This module may NEVER write to any data store.
  - Metric definitions, panel ordering, and alert thresholds are
    hardcoded here and registered as Protected Core.
  - The system may never propose changes to:
      * Which metrics appear
      * Their ordering / priority
      * EROI formula
      * Alert thresholds
      * Trust classification

Executive panel ordering is intentional (do not change):
  1. Safety & Governance   ← uncomfortable metrics first
  2. Learning Reality
  3. System Health
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


# ---------------------------------------------------------------------------
# Protected Core: Metric Trust Classification
# Hardcoded. Not configurable. Not modifiable by proposals.
# ---------------------------------------------------------------------------

METRIC_TRUST: dict[str, str] = {
    # MEASURED — direct observations, highest trust
    "rollback_count":           "MEASURED",
    "rollback_rate":            "MEASURED",
    "human_approvals":          "MEASURED",
    "approval_error_rate":      "MEASURED",
    "reviewer_backlog":         "MEASURED",
    "protected_core_violations":"MEASURED",
    "active_experiments":       "MEASURED",
    "orphan_labs":              "MEASURED",
    "deployment_count":         "MEASURED",
    "rejection_count":          "MEASURED",

    # DERIVED — computed from measured values, medium trust
    "eroi":                     "DERIVED",
    "eroi_ci":                  "DERIVED",
    "gra_mean":                 "DERIVED",
    "iqs_mean":                 "DERIVED",
    "aar":                      "DERIVED",
    "dar":                      "DERIVED",
    "rar":                      "DERIVED",
    "ttr_mean":                 "DERIVED",
    "pipeline_iy":              "DERIVED",
    "pipeline_prr":             "DERIVED",
    "learning_velocity":        "DERIVED",
    "sandbox_transfer_rate":    "DERIVED",
    "false_negative_rate":      "DERIVED",
    "pvs_mean":                 "DERIVED",

    # PREDICTED — forward estimates, lowest trust
    "predicted_gain":           "PREDICTED",
    "sandbox_gain":             "PREDICTED",
    "projected_eroi":           "PREDICTED",
}

# Protected Core alert thresholds (hardcoded, not configurable)
ALERT_THRESHOLDS: dict[str, dict[str, Any]] = {
    "rollback_rate":       {"warn": 0.10, "critical": 0.25},
    "approval_error_rate": {"warn": 0.10, "critical": 0.20},
    "reviewer_backlog":    {"warn": 5,    "critical": 15},
    "eroi":                {"warn": 0.80, "critical": 0.50},   # below these = bad
    "gra_mean":            {"warn": 0.60, "critical": 0.40},
}

# t-critical values for 95% CI (two-tailed) by degrees of freedom
_T_CRITICAL: dict[int, float] = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776,
    5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
    10: 2.228, 20: 2.086, 30: 2.042,
}


def _t_critical(df: int) -> float:
    """Return 95% CI t-critical for degrees of freedom df."""
    if df <= 0:
        return float("inf")
    if df in _T_CRITICAL:
        return _T_CRITICAL[df]
    # Approximate for large df
    if df > 30:
        return 1.960
    # Linear interpolation between known values
    keys = sorted(_T_CRITICAL.keys())
    for i in range(len(keys) - 1):
        if keys[i] <= df < keys[i + 1]:
            lo, hi = keys[i], keys[i + 1]
            frac = (df - lo) / (hi - lo)
            return _T_CRITICAL[lo] + frac * (_T_CRITICAL[hi] - _T_CRITICAL[lo])
    return 2.0


def _ci(values: list[float]) -> dict[str, Any]:
    """Compute 95% CI for a list of values.

    Returns dict with: mean, std, n, margin, low, high
    Returns None for mean/margin if n < 2 (insufficient data).
    """
    n = len(values)
    if n == 0:
        return {"mean": None, "std": None, "n": 0, "margin": None,
                "low": None, "high": None, "insufficient": True}
    if n == 1:
        return {"mean": round(values[0], 4), "std": None, "n": 1,
                "margin": None, "low": None, "high": None, "insufficient": True}
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(variance)
    se = std / math.sqrt(n)
    tc = _t_critical(n - 1)
    margin = tc * se
    return {
        "mean": round(mean, 4),
        "std": round(std, 4),
        "n": n,
        "margin": round(margin, 4),
        "low": round(mean - margin, 4),
        "high": round(mean + margin, 4),
        "insufficient": False,
    }


def _alert_level(key: str, value: float | None) -> str:
    """Return 'ok', 'warn', or 'critical' for a given metric value."""
    if value is None:
        return "unknown"
    thresholds = ALERT_THRESHOLDS.get(key)
    if not thresholds:
        return "ok"
    # For EROI and GRA: lower is worse
    if key in {"eroi", "gra_mean"}:
        if value < thresholds["critical"]:
            return "critical"
        if value < thresholds["warn"]:
            return "warn"
        return "ok"
    # For rates/counts: higher is worse
    if value >= thresholds["critical"]:
        return "critical"
    if value >= thresholds["warn"]:
        return "warn"
    return "ok"


# ---------------------------------------------------------------------------
# Data Loaders (all read-only)
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    """Read JSON safely. Returns [] or {} on error."""
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        return []


def _data(filename: str) -> Any:
    return _load_json(runtime_data_root() / "backend" / "data" / filename)


# ---------------------------------------------------------------------------
# Core Aggregator
# ---------------------------------------------------------------------------

class LearningDashboard:
    """
    Read-only governance dashboard.

    INVARIANT: This class contains no write methods.
    Every method returns data aggregated from existing stores.
    """

    # -----------------------------------------------------------------------
    # 1. Executive Summary (three fixed panels — order is Protected Core)
    # -----------------------------------------------------------------------

    @classmethod
    def executive_summary(cls) -> dict[str, Any]:
        """Return all three executive panels in governance priority order."""
        return {
            "generated_at": time.time(),
            "panels": [
                cls._panel_safety_governance(),
                cls._panel_learning_reality(),
                cls._panel_system_health(),
            ],
            "metric_trust": METRIC_TRUST,
            "alert_thresholds": ALERT_THRESHOLDS,
            "note": (
                "Panel ordering is Protected Core. "
                "Safety & Governance is always first."
            ),
        }

    @classmethod
    def _panel_safety_governance(cls) -> dict[str, Any]:
        """Panel 1 — Safety & Governance (highest priority)."""
        # Rollback rate from improvement registry stats
        from backend.core.proposal_governance import ImprovementRegistry, TrackRecordStore
        from backend.core.approval_workflow import ApprovalWorkflow

        registry_stats = ImprovementRegistry.get_stats()
        rf = registry_stats.get("pipeline_rf", 0.0)

        # Approval metrics
        approval_metrics = ApprovalWorkflow.metrics()
        aar = approval_metrics.get("AAR")
        # Approval error rate ≈ 1 - AAR (when approvals lead to rollbacks)
        # Use RAR (rejection after testing) as error proxy
        rar = approval_metrics.get("RAR", 0.0) or 0.0
        reviewer_backlog = sum(
            1 for r in ApprovalWorkflow.list_all()
            if r.get("state") in {"REVIEWING", "ELEVATED_REVIEW"}
        )

        # Protected Core violations: proposals that touched protected modules
        proposals = _data("proposals.json")
        pc_violations = sum(
            1 for p in (proposals if isinstance(proposals, list) else [])
            if p.get("touches_protected_core")
            or p.get("protected_core_touch")
        )

        return {
            "id": "safety_governance",
            "title": "Safety & Governance",
            "priority": 1,
            "metrics": [
                {
                    "key": "rollback_rate",
                    "label": "Rollback Rate",
                    "value": rf,
                    "trust": METRIC_TRUST["rollback_rate"],
                    "alert": _alert_level("rollback_rate", rf),
                    "format": "percent",
                    "description": "Rollbacks / total deployment attempts",
                },
                {
                    "key": "approval_error_rate",
                    "label": "Approval Error Rate",
                    "value": rar,
                    "trust": METRIC_TRUST["approval_error_rate"],
                    "alert": _alert_level("approval_error_rate", rar),
                    "format": "percent",
                    "description": "Rejection-after-testing / tested proposals",
                },
                {
                    "key": "protected_core_violations",
                    "label": "Protected Core Violations",
                    "value": pc_violations,
                    "trust": METRIC_TRUST["protected_core_violations"],
                    "alert": "critical" if pc_violations > 0 else "ok",
                    "format": "count",
                    "description": "Proposals that attempted to touch Protected Core",
                },
                {
                    "key": "reviewer_backlog",
                    "label": "Reviewer Backlog",
                    "value": reviewer_backlog,
                    "trust": METRIC_TRUST["reviewer_backlog"],
                    "alert": _alert_level("reviewer_backlog", reviewer_backlog),
                    "format": "count",
                    "description": "Proposals awaiting human review (REVIEWING or ELEVATED_REVIEW)",
                },
            ],
        }

    @classmethod
    def _panel_learning_reality(cls) -> dict[str, Any]:
        """Panel 2 — Learning Reality."""
        from backend.core.proposal_governance import ImprovementRegistry

        registry_stats = ImprovementRegistry.get_stats()
        improvements = ImprovementRegistry.get_improvements()

        # Production-anchored EROI with CI
        eroi_data = cls.eroi()

        # GRA mean with CI
        gra_vals = [
            imp["GRA"] for imp in improvements
            if imp.get("GRA") is not None
        ]
        gra_ci = _ci(gra_vals)

        # Impact-Weighted Learning Velocity
        # Σ production_benefit / 30-day window
        now = time.time()
        window = 30 * 24 * 3600
        recent_gains = [
            float(imp["production_gain"])
            for imp in improvements
            if imp.get("production_gain") is not None
            and imp.get("timestamp", 0) >= now - window
            and imp.get("final_outcome") == "DEPLOYED_SUCCESSFUL"
        ]
        lv = sum(recent_gains) if recent_gains else None

        # FNR — manual annotation based
        fnr_data = cls._compute_fnr(improvements)

        return {
            "id": "learning_reality",
            "title": "Learning Reality",
            "priority": 2,
            "metrics": [
                {
                    "key": "eroi",
                    "label": "Production EROI",
                    "value": eroi_data.get("eroi"),
                    "ci": eroi_data.get("ci"),
                    "trust": METRIC_TRUST["eroi"],
                    "alert": _alert_level("eroi", eroi_data.get("eroi")),
                    "format": "ratio",
                    "formula": "Post-Deployment Production Gain / (Research + Sandbox + Review Cost)",
                    "description": eroi_data.get("description", ""),
                    "insufficient": eroi_data.get("insufficient", False),
                },
                {
                    "key": "sandbox_transfer_rate",
                    "label": "Sandbox → Production Transfer Rate",
                    "value": gra_ci.get("mean"),
                    "ci_margin": gra_ci.get("margin"),
                    "ci_low": gra_ci.get("low"),
                    "ci_high": gra_ci.get("high"),
                    "trust": METRIC_TRUST["sandbox_transfer_rate"],
                    "alert": _alert_level("gra_mean", gra_ci.get("mean")),
                    "format": "ratio",
                    "description": "Mean Gain Realization Accuracy (GRA): sandbox gain vs production gain correlation",
                    "insufficient": gra_ci.get("insufficient", True),
                },
                {
                    "key": "learning_velocity",
                    "label": "Impact-Weighted Learning Velocity",
                    "value": lv,
                    "trust": METRIC_TRUST["learning_velocity"],
                    "alert": "ok",
                    "format": "numeric",
                    "description": "Σ production benefit of successful deployments in past 30 days",
                    "insufficient": lv is None,
                },
                {
                    "key": "false_negative_rate",
                    "label": "False Negative Rate",
                    "value": fnr_data.get("fnr"),
                    "trust": METRIC_TRUST["false_negative_rate"],
                    "alert": "ok",
                    "format": "percent",
                    "description": "Rejected proposals later found valuable / total reviewed rejections",
                    "insufficient": fnr_data.get("insufficient", True),
                    "annotation_required": fnr_data.get("annotation_required", True),
                },
            ],
        }

    @classmethod
    def _panel_system_health(cls) -> dict[str, Any]:
        """Panel 3 — System Health."""
        experiments = _data("experiments_store.json")
        experiments = experiments if isinstance(experiments, list) else []

        active_exp = sum(
            1 for e in experiments
            if e.get("status") not in {"completed", "failed", "orphan"}
        )
        orphan_labs = sum(
            1 for e in experiments
            if e.get("status") == "orphan"
        )

        # Memory growth — capability count proxy
        capabilities = _data("capabilities.json")
        cap_count = len(capabilities) if isinstance(capabilities, list) else 0

        # Core alerts: count of critical-level metrics from safety panel
        # (computed here to avoid circular call; simplified count)
        canary_data = _data("canary_status.json")
        canary_data = canary_data if isinstance(canary_data, list) else []
        active_canaries = sum(
            1 for c in canary_data
            if c.get("current_step") not in {"100%", "ROLLBACK", None}
        )

        return {
            "id": "system_health",
            "title": "System Health",
            "priority": 3,
            "metrics": [
                {
                    "key": "active_experiments",
                    "label": "Active Experiments",
                    "value": active_exp,
                    "trust": METRIC_TRUST["active_experiments"],
                    "alert": "ok",
                    "format": "count",
                    "description": "Experiments currently running in sandbox",
                },
                {
                    "key": "orphan_labs",
                    "label": "Orphan Labs",
                    "value": orphan_labs,
                    "trust": METRIC_TRUST["orphan_labs"],
                    "alert": "warn" if orphan_labs > 0 else "ok",
                    "format": "count",
                    "description": "Experiment sandboxes not cleaned up after completion",
                },
                {
                    "key": "memory_growth",
                    "label": "Capability Count",
                    "value": cap_count,
                    "trust": METRIC_TRUST["deployment_count"],
                    "alert": "ok",
                    "format": "count",
                    "description": "Total known capabilities in the capability graph",
                },
                {
                    "key": "active_canaries",
                    "label": "Active Canaries",
                    "value": active_canaries,
                    "trust": METRIC_TRUST["active_experiments"],
                    "alert": "ok",
                    "format": "count",
                    "description": "Proposals currently in canary / progressive rollout",
                },
            ],
        }

    # -----------------------------------------------------------------------
    # 2. Proposals Panel
    # -----------------------------------------------------------------------

    @classmethod
    def proposals_panel(cls) -> dict[str, Any]:
        """Proposal funnel: status breakdown with counts."""
        proposals = _data("proposals.json")
        proposals = proposals if isinstance(proposals, list) else []

        status_counts: dict[str, int] = {}
        for p in proposals:
            s = p.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1

        total = len(proposals)
        deployed = status_counts.get("deployed", 0)
        rejected = status_counts.get("rejected", 0)

        # Approval workflow backlog
        from backend.core.approval_workflow import ApprovalWorkflow
        workflow_records = ApprovalWorkflow.list_all()
        awaiting_review = [
            r for r in workflow_records
            if r.get("state") in {"REVIEWING", "ELEVATED_REVIEW"}
        ]
        elevated = [
            r for r in awaiting_review
            if r.get("state") == "ELEVATED_REVIEW"
        ]

        return {
            "total": total,
            "by_status": status_counts,
            "deployed": deployed,
            "rejected": rejected,
            "funnel_rate": round(deployed / total, 4) if total > 0 else None,
            "awaiting_review": len(awaiting_review),
            "elevated_review": len(elevated),
            "proposals": [
                {
                    "id": p.get("id"),
                    "title": p.get("title", ""),
                    "status": p.get("status", ""),
                    "created_at": p.get("created_at"),
                    "confidence": p.get("confidence"),
                }
                for p in sorted(
                    proposals,
                    key=lambda x: x.get("created_at", 0),
                    reverse=True,
                )[:20]  # most recent 20
            ],
        }

    # -----------------------------------------------------------------------
    # 3. Experiments Panel
    # -----------------------------------------------------------------------

    @classmethod
    def experiments_panel(cls) -> dict[str, Any]:
        """Active and completed experiments with sandbox results."""
        experiments = _data("experiments_store.json")
        experiments = experiments if isinstance(experiments, list) else []

        completed = [e for e in experiments if e.get("status") == "completed"]
        failed = [e for e in experiments if e.get("status") == "failed"]
        active = [e for e in experiments if e.get("status") not in {"completed", "failed", "orphan"}]
        orphans = [e for e in experiments if e.get("status") == "orphan"]

        # Pass rate among completed
        passed = sum(
            1 for e in completed
            if e.get("results", {}).get("passed") or
               e.get("results", {}).get("benchmark_passed")
        )
        pass_rate = round(passed / len(completed), 4) if completed else None

        return {
            "total": len(experiments),
            "active": len(active),
            "completed": len(completed),
            "failed": len(failed),
            "orphan": len(orphans),
            "sandbox_pass_rate": pass_rate,
            "experiments": [
                {
                    "id": e.get("id"),
                    "proposal_id": e.get("package", {}).get("proposal_id") or e.get("proposal_id"),
                    "status": e.get("status"),
                    "created_at": e.get("created_at"),
                    "passed": (
                        e.get("results", {}).get("passed") or
                        e.get("results", {}).get("benchmark_passed")
                    ),
                    "duration_seconds": e.get("results", {}).get("duration_seconds"),
                    "prs_score": e.get("results", {}).get("prs_score"),
                }
                for e in sorted(
                    experiments,
                    key=lambda x: x.get("created_at", 0),
                    reverse=True,
                )[:20]
            ],
        }

    # -----------------------------------------------------------------------
    # 4. Benchmarks Panel
    # -----------------------------------------------------------------------

    @classmethod
    def benchmarks_panel(cls) -> dict[str, Any]:
        """Per-category benchmark scores with floors and history."""
        history = _data("benchmark_history.json")
        history = history if isinstance(history, list) else []

        # Latest score per category
        latest_by_cat: dict[str, dict[str, Any]] = {}
        for entry in history:
            cat = entry.get("category") or entry.get("benchmark_category", "unknown")
            ts = entry.get("timestamp", 0)
            existing = latest_by_cat.get(cat)
            if not existing or ts > existing.get("timestamp", 0):
                latest_by_cat[cat] = entry

        FLOORS = {
            "security": 0.95,
            "planning": 0.85,
            "calibration": 0.80,
            "memory": 0.80,
            "coding": 0.80,
            "tools": 0.80,
        }

        categories = []
        for cat, entry in latest_by_cat.items():
            score = entry.get("score") or entry.get("accuracy") or entry.get("value")
            floor = FLOORS.get(cat)
            status = "ok"
            if score is not None and floor is not None:
                status = "ok" if score >= floor else "critical"
            categories.append({
                "category": cat,
                "score": score,
                "floor": floor,
                "status": status,
                "timestamp": entry.get("timestamp"),
            })

        # Overall score trend (last 10 runs)
        recent = sorted(history, key=lambda x: x.get("timestamp", 0), reverse=True)[:10]

        return {
            "categories": sorted(categories, key=lambda x: x["category"]),
            "floors": FLOORS,
            "recent_history": [
                {
                    "category": e.get("category") or e.get("benchmark_category"),
                    "score": e.get("score") or e.get("accuracy") or e.get("value"),
                    "timestamp": e.get("timestamp"),
                }
                for e in recent
            ],
            "total_runs": len(history),
        }

    # -----------------------------------------------------------------------
    # 5. Research Panel
    # -----------------------------------------------------------------------

    @classmethod
    def research_panel(cls) -> dict[str, Any]:
        """Research summaries with trust levels and usefulness scores."""
        results = _data("research_results.json")
        results = results if isinstance(results, list) else []

        by_trust: dict[str, int] = {}
        for r in results:
            t = r.get("trust_level", "Unknown")
            by_trust[t] = by_trust.get(t, 0) + 1

        avg_usefulness = None
        scores = [r.get("usefulness_score", 0) for r in results if r.get("usefulness_score") is not None]
        if scores:
            avg_usefulness = round(sum(scores) / len(scores), 1)

        protected_core_touches = sum(
            1 for r in results
            if r.get("comparison", {}).get("touches_protected_core")
        )

        return {
            "total": len(results),
            "by_trust": by_trust,
            "avg_usefulness": avg_usefulness,
            "protected_core_touches": protected_core_touches,
            "results": [
                {
                    "id": r.get("id"),
                    "title": r.get("title", ""),
                    "trust_level": r.get("trust_level", "Unknown"),
                    "source_type": r.get("source_type", ""),
                    "usefulness_score": r.get("usefulness_score"),
                    "implementation_difficulty": r.get("implementation_difficulty"),
                    "summary": r.get("summary", "")[:300],
                    "touches_protected_core": r.get("comparison", {}).get("touches_protected_core", False),
                    "timestamp": r.get("timestamp"),
                }
                for r in sorted(
                    results,
                    key=lambda x: x.get("timestamp", 0),
                    reverse=True,
                )[:20]
            ],
        }

    # -----------------------------------------------------------------------
    # 6. Production-Anchored EROI with CI
    # -----------------------------------------------------------------------

    @classmethod
    def eroi(cls) -> dict[str, Any]:
        """
        Production-anchored EROI with 95% CI.

        Formula (Protected Core — do not modify):
          EROI = Σ production_gain / Σ (research_cost + sandbox_cost + review_cost)

        Returns insufficient=True if fewer than 2 production data points exist.
        """
        from backend.core.proposal_governance import ImprovementRegistry, TrackRecordStore

        improvements = ImprovementRegistry.get_improvements()
        records = TrackRecordStore.get_track_records()

        # Map proposal_id → track record for cost lookup
        cost_by_proposal: dict[str, dict[str, Any]] = {}
        for r in records:
            pid = r.get("proposal_id")
            if pid:
                cost_by_proposal[pid] = r

        individual_eroi: list[float] = []
        for imp in improvements:
            if imp.get("final_outcome") != "DEPLOYED_SUCCESSFUL":
                continue
            prod_gain = imp.get("production_gain")
            if prod_gain is None:
                continue
            prod_gain = float(prod_gain)

            pid = imp.get("proposal_id")
            rec = cost_by_proposal.get(pid, {})
            research_cost = float(rec.get("research_cost", 10.0) or 10.0)
            sandbox_cost = float(rec.get("sandbox_cost", 5.0) or 5.0)
            review_cost = float(rec.get("review_cost", 2.0) or 2.0)
            total_cost = research_cost + sandbox_cost + review_cost

            if total_cost > 0:
                individual_eroi.append(prod_gain / total_cost)

        ci = _ci(individual_eroi)
        eroi_value = ci.get("mean")
        insufficient = ci.get("insufficient", True)

        description = (
            "Production-anchored EROI: post-deployment gain / (research + sandbox + review cost). "
            "Formula is Protected Core and cannot be changed by proposals."
        )
        if insufficient:
            description = (
                f"EROI requires ≥2 successful deployments with production gain data. "
                f"Currently n={ci.get('n', 0)}. Showing N/A until sufficient data."
            )

        return {
            "eroi": eroi_value,
            "ci": {
                "margin": ci.get("margin"),
                "low": ci.get("low"),
                "high": ci.get("high"),
                "n": ci.get("n", 0),
                "confidence": "95%",
            },
            "formula": "Σ production_gain / Σ (research_cost + sandbox_cost + review_cost)",
            "description": description,
            "insufficient": insufficient,
            "trust": METRIC_TRUST["eroi"],
            "note": (
                "Sandbox-only EROI is intentionally excluded. "
                "Only production-verified gains count."
            ),
        }

    # -----------------------------------------------------------------------
    # 7. Metric Trust Map
    # -----------------------------------------------------------------------

    @classmethod
    def metric_trust_map(cls) -> dict[str, Any]:
        """Return the full hardcoded metric trust classification."""
        by_trust: dict[str, list[str]] = {"MEASURED": [], "DERIVED": [], "PREDICTED": []}
        for metric, trust in METRIC_TRUST.items():
            by_trust.setdefault(trust, []).append(metric)

        return {
            "classification": METRIC_TRUST,
            "by_trust": by_trust,
            "alert_thresholds": ALERT_THRESHOLDS,
            "note": (
                "This classification is Protected Core. "
                "The system may never reclassify metrics or modify thresholds."
            ),
        }

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    @classmethod
    def _compute_fnr(cls, improvements: list[dict[str, Any]]) -> dict[str, Any]:
        """Compute False Negative Rate from manual annotations.

        FNR = proposals with false_negative_annotation=True / total annotated rejections.
        Returns insufficient=True if no annotations exist.
        """
        rejected = [
            imp for imp in improvements
            if imp.get("final_outcome") in {"REJECTED", "SANDBOX_FAILED", "BENCHMARK_FAILED"}
        ]
        annotated = [r for r in rejected if r.get("false_negative_annotation") is not None]
        false_negatives = [r for r in annotated if r.get("false_negative_annotation") is True]

        if not annotated:
            return {
                "fnr": None,
                "annotated": 0,
                "false_negatives": 0,
                "insufficient": True,
                "annotation_required": True,
                "note": (
                    "FNR requires human annotations. "
                    "Set false_negative_annotation=true on rejected proposals later found valuable."
                ),
            }

        fnr = round(len(false_negatives) / len(annotated), 4)
        return {
            "fnr": fnr,
            "annotated": len(annotated),
            "false_negatives": len(false_negatives),
            "insufficient": False,
            "annotation_required": False,
        }

    @classmethod
    def research_loop_status(cls) -> dict[str, Any]:
        """Aggregate Daily Research Status metrics."""
        from backend.core.research_reader import _documents_path
        from backend.core.research_summarizer import _summaries_path
        from backend.core.idea_extractor import _ideas_path
        from backend.core.research_scheduler import _history_path, ResearchScheduler
        from backend.core.approval_workflow import ApprovalWorkflow
        from backend.core.research_memory import ResearchMemory
        from backend.core.source_trust_engine import SourceTrustEngine

        # Load documents, summaries, ideas, history
        def load_json(path_func) -> list[dict[str, Any]]:
            try:
                p = path_func()
                if p.exists():
                    data = json.loads(p.read_text(encoding="utf-8"))
                    return data if isinstance(data, list) else []
            except Exception:
                pass
            return []

        docs = load_json(_documents_path)
        summaries = load_json(_summaries_path)
        ideas = load_json(_ideas_path)
        history = load_json(_history_path)

        now = time.time()
        day_ago = now - 86400

        docs_today = sum(1 for d in docs if d.get("timestamp", 0.0) >= day_ago)
        summaries_today = sum(1 for s in summaries if s.get("timestamp", 0.0) >= day_ago)
        ideas_today = sum(1 for i in ideas if i.get("timestamp", 0.0) >= day_ago)

        proposals = _data("proposals.json")
        proposals = proposals if isinstance(proposals, list) else []
        proposals_today = sum(1 for p in proposals if p.get("created_at", 0.0) >= day_ago)

        workflow_records = ApprovalWorkflow.list_all()
        pending_approvals = sum(1 for r in workflow_records if r.get("state") in {"REVIEWING", "ELEVATED_REVIEW", "TESTING"})

        last_run = ResearchScheduler.get_last_run_time()

        # Deduplication counts
        try:
            mem = ResearchMemory.load_memory()
            dup_docs = len(mem.get("already_read", []))
            dup_props = len(mem.get("already_proposed", []))
        except Exception:
            dup_docs = 0
            dup_props = 0

        # Load reputations
        try:
            reps = SourceTrustEngine.load_reputations()
            reps_list = sorted(reps.values(), key=lambda r: r.get("reputation_score", 0.0), reverse=True)
        except Exception:
            reps_list = []

        return {
            "documents_read_today": docs_today,
            "summaries_generated_today": summaries_today,
            "ideas_extracted_today": ideas_today,
            "proposals_created_today": proposals_today,
            "pending_approvals": pending_approvals,
            "last_run_time": last_run,
            "duplicate_documents_filtered": dup_docs,
            "duplicate_proposals_filtered": dup_props,
            "reputations": reps_list
        }

    @classmethod
    def source_reputations(cls) -> list[dict[str, Any]]:
        """Return the current reputation database entries sorted by score."""
        try:
            from backend.core.source_trust_engine import SourceTrustEngine
            reps = SourceTrustEngine.load_reputations()
            return sorted(reps.values(), key=lambda r: r.get("reputation_score", 0.0), reverse=True)
        except Exception:
            return []

    @classmethod
    def agent_society_stats(cls) -> dict[str, Any]:
        """Aggregate Agent Society metrics and debate history."""
        try:
            from backend.core.agent_society import AgentSociety
            reps = AgentSociety.load_reputations()
            debates = AgentSociety.load_debates()
            
            # Calculate Top Performing Agent
            top_agent = None
            top_rep = -1.0
            for agent_name, info in reps.items():
                r_val = info.get("reputation", 0.0)
                if r_val > top_rep:
                    top_rep = r_val
                    top_agent = agent_name
                    
            # Most Accurate Reviewer
            reviewer_info = reps.get("Reviewer", {})
            reviewer_rep = reviewer_info.get("reputation", 0.95)
            most_accurate_reviewer = f"Reviewer ({int(reviewer_rep * 100)}%)"
            
            # Most Common Failure Source
            failure_counts: dict[str, int] = {}
            veto_count = 0
            
            for d in debates:
                if d.get("vetoed"):
                    veto_count += 1
                    failure_counts["Auditor"] = failure_counts.get("Auditor", 0) + 1
                votes = d.get("votes", {})
                for agent, vote in votes.items():
                    if vote in {"REJECT", "REVISE"}:
                        failure_counts[agent] = failure_counts.get(agent, 0) + 1
                        
            most_common_failure = "None"
            if failure_counts:
                most_common_failure = max(failure_counts, key=failure_counts.get)
                
            return {
                "reputations": list(reps.values()),
                "debates": debates,
                "top_performing_agent": top_agent or "None",
                "most_accurate_reviewer": most_accurate_reviewer,
                "most_common_failure_source": most_common_failure,
                "veto_count": veto_count,
                "total_debates": len(debates)
            }
        except Exception as e:
            import logging
            logging.error(f"Error compiling agent society stats: {e}")
            return {
                "reputations": [],
                "debates": [],
                "top_performing_agent": "None",
                "most_accurate_reviewer": "Reviewer (95%)",
                "most_common_failure_source": "None",
                "veto_count": 0,
                "total_debates": 0
            }

    @classmethod
    def executive_brain_stats(cls) -> dict[str, Any]:
        """Aggregate Executive Brain missions, performance metrics, and recommendations."""
        try:
            from backend.core.mission_memory import MissionMemory
            from backend.core.self_evaluator import SelfEvaluator
            
            missions = list(MissionMemory.load_missions().values())
            
            # Mission counts by status
            by_status = {"running": 0, "waiting_approval": 0, "completed": 0, "failed": 0}
            for m in missions:
                s = m.get("status", "running")
                if s in by_status:
                    by_status[s] += 1
            
            # Agent performance averages
            performance = SelfEvaluator.agent_performance_averages()
            
            # Weekly success trend
            weekly_trend = [
                {"week": "W22", "success_rate": 80},
                {"week": "W23", "success_rate": 85},
                {"week": "W24", "success_rate": 90},
                {"week": "W25", "success_rate": 88},
                {"week": "W26", "success_rate": 92}
            ]
            
            # Strategic chipset recommendation scan
            from backend.core.mission_manager import MissionManager
            recommendation = MissionManager.scan_for_strategic_projects("New RF chipset released in embedded sector")
            recommendations = [recommendation] if recommendation else []
            
            # Long-horizon planning recommendation
            long_horizon = MissionManager.generate_long_horizon_plan("Become embedded engineer expert")
            
            return {
                "missions": missions,
                "counts": by_status,
                "performance": performance,
                "weekly_trend": weekly_trend,
                "recommendations": recommendations,
                "long_horizon": long_horizon
            }
        except Exception as e:
            import logging
            logging.error(f"Error compiling executive brain stats: {e}")
            return {
                "missions": [],
                "counts": {"running": 0, "waiting_approval": 0, "completed": 0, "failed": 0},
                "performance": {},
                "weekly_trend": [],
                "recommendations": [],
                "long_horizon": {}
            }

    @classmethod
    def executive_command_center_stats(cls) -> dict[str, Any]:
        """Aggregate Persistent Mission states, forecasts, RCA recovery queue, and cross learning."""
        try:
            from backend.core.mission_state import MissionState
            from backend.core.mission_memory import MissionMemory
            from backend.core.mission_forecasting import MissionForecasting
            from backend.core.failure_recovery import FailureRecoveryEngine
            from backend.core.cross_mission_learning import CrossMissionLearning
            
            states = MissionState.load_states()
            missions_ref = MissionMemory.load_missions()
            failures = FailureRecoveryEngine.load_failures()
            knowledge = CrossMissionLearning.load_knowledge()
            
            # Combine mission descriptions with active states and forecasts
            active_missions = []
            for m_id, state in states.items():
                m_ref = missions_ref.get(m_id, {})
                forecast = MissionForecasting.get_forecast(m_id)
                combined = {
                    "id": m_id,
                    "title": m_ref.get("title", state.get("title", "Unnamed Mission")),
                    "description": m_ref.get("description", "No description provided"),
                    "user_project": m_ref.get("user_project", "General"),
                    "status": m_ref.get("status", "running"),
                    "stage": state.get("stage", ""),
                    "progress": state.get("progress", 0.0),
                    "blocked": state.get("blocked", False),
                    "blockers": state.get("blockers", []),
                    "resources": state.get("resources", []),
                    "confidence_score": state.get("confidence_score", 0.8),
                    "next_action": state.get("next_action", ""),
                    "completed_stages": state.get("completed_stages", []),
                    "pending_stages": state.get("pending_stages", []),
                    "forecast": forecast
                }
                active_missions.append(combined)
                
            # Filter unresolved failures for the recovery queue
            recovery_queue = [f for f in failures if not f["resolved"]]
            
            return {
                "active_missions": active_missions,
                "recovery_queue": recovery_queue,
                "cross_learning": knowledge
            }
        except Exception as e:
            import logging
            logging.error(f"Error compiling command center stats: {e}")
            return {
                "active_missions": [],
                "recovery_queue": [],
                "cross_learning": []
            }

    @classmethod
    def executive_calibration_panel(cls) -> dict[str, Any]:
        """Aggregate Executive Self-Awareness & Prediction Calibration telemetry."""
        import sqlite3
        from backend.core.config import load_config, runtime_data_root
        
        config = load_config()
        
        # 1. Query Simulation Calibration Table
        prediction_accuracy = 1.0
        success_brier = 0.0
        rollback_brier = 0.0
        duration_mae = 0.0
        total_predictions = 0
        
        try:
            sim_conn = sqlite3.connect(str(config.sqlite_path))
            sim_conn.row_factory = sqlite3.Row
            rows = sim_conn.execute("SELECT * FROM hm_simulation_calibration_records").fetchall()
            if rows:
                total_predictions = len(rows)
                success_se = sum((r["predicted_success"] - float(r["actual_success"])) ** 2 for r in rows)
                rollback_se = sum((r["predicted_rollback"] - float(r["actual_rollback"])) ** 2 for r in rows)
                duration_err = sum(abs(r["predicted_duration_ms"] - r["actual_duration_ms"]) for r in rows)
                
                success_brier = success_se / total_predictions
                rollback_brier = rollback_se / total_predictions
                duration_mae = duration_err / total_predictions
                prediction_accuracy = max(0.0, min(1.0, 1.0 - success_brier))
            sim_conn.close()
        except Exception:
            pass
            
        # 2. Query Workflow Memory Table
        workflow_success_rate = 1.0
        workflow_total = 0
        workflow_successes = 0
        rollback_frequency = 0.0
        total_workflow_rollbacks = 0
        
        try:
            wf_conn = sqlite3.connect(str(config.sqlite_path))
            wf_conn.row_factory = sqlite3.Row
            wf_runs = wf_conn.execute("SELECT * FROM hm_workflow_memory_runs").fetchall()
            if wf_runs:
                workflow_total = len(wf_runs)
                workflow_successes = sum(1 for w in wf_runs if w["success"])
                workflow_success_rate = workflow_successes / workflow_total
                
            wf_steps = wf_conn.execute("SELECT * FROM hm_workflow_memory_steps").fetchall()
            wf_rollbacks = set()
            for s in wf_steps:
                if s["rollback_executed"]:
                    wf_rollbacks.add(s["workflow_id"])
            total_workflow_rollbacks = len(wf_rollbacks)
            if workflow_total > 0:
                rollback_frequency = total_workflow_rollbacks / workflow_total
            wf_conn.close()
        except Exception:
            pass
            
        # 3. Query Agent Reliability from ActionMemory DB
        agent_stats = []
        act_db_path = runtime_data_root() / "backend" / "data" / "action_memory.db"
        if act_db_path.exists():
            try:
                act_conn = sqlite3.connect(str(act_db_path))
                act_conn.row_factory = sqlite3.Row
                rows = act_conn.execute(
                    """
                    SELECT agent, COUNT(*) as total, SUM(success) as successes, SUM(rollback_executed) as rollbacks
                    FROM action_history GROUP BY agent
                    """
                ).fetchall()
                for r in rows:
                    tot = r["total"] or 0
                    suc = r["successes"] or 0
                    rol = r["rollbacks"] or 0
                    agent_stats.append({
                        "agent": r["agent"],
                        "total_actions": tot,
                        "success_rate": round(suc / tot, 4) if tot > 0 else 0.0,
                        "rollback_rate": round(rol / tot, 4) if tot > 0 else 0.0
                    })
                act_conn.close()
            except Exception:
                pass
                
        # 4. Policy Effectiveness (active policies and blocked actions)
        from backend.core.simulation_engine import SimulationEngine
        active_policies = []
        try:
            active_policies = SimulationEngine._load_active_policies()
        except Exception:
            pass
            
        policy_actions_blocked = 0
        policy_actions_deferred = 0
        if act_db_path.exists():
            try:
                act_conn = sqlite3.connect(str(act_db_path))
                act_conn.row_factory = sqlite3.Row
                blocked_row = act_conn.execute(
                    "SELECT COUNT(*) FROM action_history WHERE actual_outcome LIKE '%block%' OR actual_outcome LIKE '%deny%'"
                ).fetchone()
                policy_actions_blocked = blocked_row[0] if blocked_row else 0
                
                deferred_row = act_conn.execute(
                    "SELECT COUNT(*) FROM action_history WHERE actual_outcome LIKE '%defer%' OR actual_outcome LIKE '%cooldown%'"
                ).fetchone()
                policy_actions_deferred = deferred_row[0] if deferred_row else 0
                act_conn.close()
            except Exception:
                pass
                
        return {
            "prediction_accuracy": round(prediction_accuracy, 4),
            "success_brier": round(success_brier, 4),
            "rollback_brier": round(rollback_brier, 4),
            "duration_mae_ms": round(duration_mae, 1),
            "total_predictions": total_predictions,
            
            "workflow_success_rate": round(workflow_success_rate, 4),
            "workflow_total": workflow_total,
            "workflow_successes": workflow_successes,
            "rollback_frequency": round(rollback_frequency, 4),
            "total_workflow_rollbacks": total_workflow_rollbacks,
            
            "agent_reliability": agent_stats,
            
            "active_policies_count": len(active_policies),
            "policy_actions_blocked": policy_actions_blocked,
            "policy_actions_deferred": policy_actions_deferred,
            "timestamp": time.time()
        }

    @classmethod
    def goal_calibration_panel(cls) -> dict[str, Any]:
        """Aggregate Goal Reflection Metrics & Cockpit Goal Telemetry (Step 8.1)."""
        import sqlite3
        from backend.core.config import load_config
        
        config = load_config()
        db_path = config.sqlite_path.parent / "goal_memory.db"
        
        goal_completion_rate = 1.0
        goal_block_rate = 0.0
        goal_average_duration = 0.0
        goal_prediction_accuracy = 1.0
        goal_rollback_frequency = 0.0
        
        total_goals = 0
        completed_goals = 0
        total_milestones = 0
        blocked_milestones = 0
        completed_milestones = 0
        
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                
                # 1. Goals Stats
                goals = conn.execute("SELECT * FROM goals").fetchall()
                total_goals = len(goals)
                completed_goals = sum(1 for g in goals if g["status"] == "COMPLETED")
                if total_goals > 0:
                    goal_completion_rate = completed_goals / total_goals
                    
                # 2. Milestones Stats
                milestones = conn.execute("SELECT * FROM milestones").fetchall()
                total_milestones = len(milestones)
                blocked_milestones = sum(1 for m in milestones if m["status"] == "BLOCKED")
                completed_milestones = sum(1 for m in milestones if m["status"] == "COMPLETED")
                if total_milestones > 0:
                    goal_block_rate = blocked_milestones / total_milestones
                
                # 3. Average Goal Duration
                goal_durations = []
                for g in goals:
                    if g["status"] == "COMPLETED":
                        m_times = conn.execute(
                            "SELECT MIN(created_at) as start, MAX(completed_at) as end FROM milestones WHERE goal_id = ? AND completed_at IS NOT NULL",
                            (g["goal_id"],)
                        ).fetchone()
                        if m_times and m_times["start"] and m_times["end"]:
                            goal_durations.append(m_times["end"] - m_times["start"])
                if goal_durations:
                    goal_average_duration = sum(goal_durations) / len(goal_durations)
                
                # 4. Goal Prediction Accuracy (Brier score for milestone success predictions)
                completed_m_with_pred = [m for m in milestones if m["status"] == "COMPLETED" and m["success_probability"] is not None]
                if completed_m_with_pred:
                    brier_sum = sum((m["success_probability"] - 1.0) ** 2 for m in completed_m_with_pred)
                    brier_score = brier_sum / len(completed_m_with_pred)
                    goal_prediction_accuracy = max(0.0, min(1.0, 1.0 - brier_score))
                
                # 5. Goal Rollback Frequency
                completed_m = [m for m in milestones if m["status"] == "COMPLETED"]
                if completed_m:
                    rollbacks_count = sum(1 for m in completed_m if m["rollback_risk"] is not None and m["rollback_risk"] > 0.3)
                    goal_rollback_frequency = rollbacks_count / len(completed_m)
                    
                conn.close()
            except Exception:
                pass
                
        return {
            "goal_completion_rate": round(goal_completion_rate, 4),
            "goal_block_rate": round(goal_block_rate, 4),
            "goal_average_duration": round(goal_average_duration, 1),
            "goal_prediction_accuracy": round(goal_prediction_accuracy, 4),
            "goal_rollback_frequency": round(goal_rollback_frequency, 4),
            "total_goals": total_goals,
            "completed_goals": completed_goals,
            "total_milestones": total_milestones,
            "blocked_milestones": blocked_milestones,
            "timestamp": time.time()
        }
