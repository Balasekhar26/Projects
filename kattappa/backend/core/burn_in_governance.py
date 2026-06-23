"""
Step 8.0 — Operational Burn-In Governance Engine

Observes, measures, audits, and enforces safety freeze conditions.
INVARIANT: Registered in Protected Core to prevent autonomous override.
"""
from __future__ import annotations

import json
import time
import threading
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _state_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "burn_in_state.json"


def _history_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "burn_in_history.json"


class BurnInGovernance:
    _lock = threading.RLock()

    @classmethod
    def get_state(cls) -> dict[str, Any]:
        """Return current burn-in state: NORMAL or AUDIT."""
        with cls._lock:
            path = _state_path()
            if not path.exists():
                return {"state": "NORMAL", "active_freezes": []}
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return {
                    "state": data.get("state", "NORMAL"),
                    "active_freezes": data.get("active_freezes", []),
                }
            except Exception:
                return {"state": "NORMAL", "active_freezes": []}

    @classmethod
    def _save_state(cls, state: str, active_freezes: list[str]) -> None:
        with cls._lock:
            path = _state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {"state": state, "active_freezes": active_freezes, "updated_at": time.time()}
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def is_frozen(cls) -> bool:
        """Returns True if system is in AUDIT mode (frozen)."""
        return cls.get_state().get("state") == "AUDIT"

    @classmethod
    def reset_audit_mode(cls, reviewer: str) -> None:
        """Reset system from AUDIT back to NORMAL. Human reviewer name mandatory."""
        if not reviewer or reviewer.strip().lower() in {"system", "auto", ""}:
            raise ValueError(
                "Resetting audit mode requires an explicit human reviewer identity. "
                "System actors may never override a freeze."
            )
        with cls._lock:
            cls._save_state("NORMAL", [])

    @classmethod
    def get_weekly_snapshots(cls) -> list[dict[str, Any]]:
        """Return historical weekly snapshots."""
        with cls._lock:
            path = _history_path()
            if not path.exists():
                return []
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []

    @classmethod
    def _save_snapshots(cls, snapshots: list[dict[str, Any]]) -> None:
        with cls._lock:
            path = _history_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(snapshots, indent=2), encoding="utf-8")

    @classmethod
    def record_weekly_snapshot(cls) -> dict[str, Any]:
        """Aggregate current metrics, append to registry, run freeze rules, and save."""
        with cls._lock:
            # Query current state from LearningDashboard
            from backend.core.learning_dashboard import LearningDashboard

            exec_summary = LearningDashboard.executive_summary()
            panels = {p["id"]: p for p in exec_summary.get("panels", [])}

            # Safety Panel Metrics
            safety_metrics = {m["key"]: m["value"] for m in panels.get("safety_governance", {}).get("metrics", [])}
            # Learning Reality Metrics
            learning_metrics = {m["key"]: m["value"] for m in panels.get("learning_reality", {}).get("metrics", [])}

            # Gather costs / gains for debt and reliability
            debt_report = ResearchDebtLedger.get_debt_report()
            rel_report = PredictionReliabilityTracker.get_reliability_report()

            snapshots = cls.get_weekly_snapshots()
            next_idx = len(snapshots) + 1

            snapshot = {
                "week_index": next_idx,
                "timestamp": time.time(),
                "production_eroi": learning_metrics.get("eroi"),
                "rollback_rate": safety_metrics.get("rollback_rate", 0.0),
                "approval_error_rate": safety_metrics.get("approval_error_rate", 0.0),
                "transfer_rate": learning_metrics.get("sandbox_transfer_rate", 0.0) or 0.0,
                "research_debt": debt_report.get("research_debt", 0.0),
                "reviewer_backlog": safety_metrics.get("reviewer_backlog", 0),
                "false_improvement_rate": learning_metrics.get("false_negative_rate", 0.0) or 0.0,
                "prediction_reliability_error": rel_report.get("average_prediction_error"),
                "protected_core_violations": safety_metrics.get("protected_core_violations", 0),
            }

            snapshots.append(snapshot)
            cls._save_snapshots(snapshots)

            # Evaluate freeze conditions
            triggers = cls.evaluate_freeze_rules()
            if triggers:
                cls._save_state("AUDIT", triggers)

            return snapshot

    @classmethod
    def evaluate_freeze_rules(cls) -> list[str]:
        """Check weekly snapshots for 4-week degradation or triggers."""
        snapshots = cls.get_weekly_snapshots()
        triggers: list[str] = []

        if not snapshots:
            return triggers

        # Rule 1: Economic Failure (EROI < 1.0 for 4 consecutive weeks)
        # Needs at least 4 snapshots
        if len(snapshots) >= 4:
            last_4 = snapshots[-4:]
            eroi_values = [s.get("production_eroi") for s in last_4]
            if all(v is not None and v < 1.0 for v in eroi_values):
                triggers.append("Economic Failure: Production EROI is below 1.0 for 4 consecutive weeks.")

        # For trend checks, we need at least 5 snapshots to represent 4 transitions/weeks
        if len(snapshots) >= 5:
            last_5 = snapshots[-5:]

            # Helper to check strict week-over-week rise (4 steps of rising)
            def is_rising(keys: list[str]) -> bool:
                for k in keys:
                    vals = [s.get(k) for s in last_5]
                    if any(v is None for v in vals):
                        continue
                    # Check W4 > W3 > W2 > W1 > W0
                    if vals[4] > vals[3] > vals[2] > vals[1] > vals[0]:
                        return True
                return False

            # Helper to check strict week-over-week fall (4 steps of falling)
            def is_falling(k: str) -> bool:
                vals = [s.get(k) for s in last_5]
                if any(v is None for v in vals):
                    return False
                return vals[4] < vals[3] < vals[2] < vals[1] < vals[0]

            # Rule 2: Safety Failure (Rollback rate rising for 4 consecutive weeks)
            if is_rising(["rollback_rate"]):
                triggers.append("Safety Failure: Rollback Rate rising for 4 consecutive weeks.")

            # Rule 3: Governance Failure (Approval error rate rising for 4 consecutive weeks)
            if is_rising(["approval_error_rate"]):
                triggers.append("Governance Failure: Approval Error Rate rising for 4 consecutive weeks.")

            # Rule 4: Research Failure (Sandbox Transfer Rate falling for 4 consecutive weeks)
            if is_falling("transfer_rate"):
                triggers.append("Research Failure: Sandbox Transfer Rate falling for 4 consecutive weeks.")

            # Rule 5: Reliability Failure (Prediction Error rising for 4 consecutive weeks)
            if is_rising(["prediction_reliability_error"]):
                triggers.append("Reliability Failure: Prediction Reliability Error rising for 4 consecutive weeks.")

        return triggers


class ResearchDebtLedger:
    @classmethod
    def get_debt_report(cls) -> dict[str, Any]:
        """Calculate Research Debt = Total Costs - Production Gains."""
        from backend.core.proposal_governance import ImprovementRegistry, TrackRecordStore

        improvements = ImprovementRegistry.get_improvements()
        records = TrackRecordStore.get_track_records()

        # Costs: research_cost + sandbox_cost + review_cost
        total_costs = 0.0
        for rec in records:
            research = float(rec.get("research_cost", 10.0) or 10.0)
            sandbox = float(rec.get("sandbox_cost", 5.0) or 5.0)
            review = float(rec.get("review_cost", 2.0) or 2.0)
            total_costs += (research + sandbox + review)

        # Gains: production_gain from DEPLOYED_SUCCESSFUL
        total_gains = 0.0
        for imp in improvements:
            if imp.get("final_outcome") == "DEPLOYED_SUCCESSFUL":
                gain = imp.get("production_gain")
                if gain is not None:
                    total_gains += float(gain)

        debt = total_costs - total_gains
        return {
            "total_costs": round(total_costs, 2),
            "total_gains": round(total_gains, 2),
            "research_debt": round(debt, 2),
            "debt_accumulating": debt > 0.0,
        }


class PredictionReliabilityTracker:
    @classmethod
    def get_reliability_report(cls) -> dict[str, Any]:
        """Audit predicted gain vs actual production gain and average error."""
        from backend.core.proposal_governance import ImprovementRegistry, TrackRecordStore

        improvements = ImprovementRegistry.get_improvements()
        records = TrackRecordStore.get_track_records()

        cost_by_proposal: dict[str, dict[str, Any]] = {
            r.get("proposal_id"): r for r in records if r.get("proposal_id")
        }

        evaluations = []
        errors = []

        for imp in improvements:
            if imp.get("final_outcome") != "DEPLOYED_SUCCESSFUL":
                continue
            actual = imp.get("production_gain")
            if actual is None:
                continue

            pid = imp.get("proposal_id")
            rec = cost_by_proposal.get(pid, {})
            predicted = rec.get("predicted_gain")
            if predicted is None:
                # Fallback to proposal level
                predicted = imp.get("predicted_gain")

            if predicted is not None:
                predicted = float(predicted)
                actual = float(actual)
                error = abs(predicted - actual)
                errors.append(error)
                evaluations.append({
                    "proposal_id": pid,
                    "predicted": round(predicted, 4),
                    "actual": round(actual, 4),
                    "error": round(error, 4),
                })

        avg_error = sum(errors) / len(errors) if errors else None
        return {
            "evaluations": evaluations,
            "average_prediction_error": round(avg_error, 4) if avg_error is not None else None,
            "total_audited_predictions": len(evaluations),
        }
