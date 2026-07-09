"""Audit Dashboard (Program 28.0).

Aggregates telemetry profiles into audit reports suitable for billing, security,
and administrative validation.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List
from backend.core.observability.telemetry import Span


class AuditDashboard:
    """Consolidates execution logs into structural diagnostic reports."""

    @classmethod
    def generate_report(cls, spans: List[Span]) -> Dict[str, Any]:
        """Summarizes structural parameters, costs, safety alerts, and run bounds."""
        total_time = 0.0
        safety_alerts: List[Dict[str, Any]] = []
        policy_checks = 0
        policy_violations = 0

        # Heuristic: Total elapsed duration is the difference between
        # the earliest start time and latest end time of root spans.
        start_bounds = [s.start_time for s in spans if s.parent_span_id is None]
        end_bounds = [s.end_time for s in spans if s.parent_span_id is None and s.end_time is not None]

        if start_bounds and end_bounds:
            total_time = max(end_bounds) - min(start_bounds)
        elif spans:
            # Fallback to sum of spans
            total_time = sum(s.duration for s in spans if s.parent_span_id is None)

        for s in spans:
            # Extract policy checkpoints from metadata
            if s.metadata.get("is_policy_check", False):
                policy_checks += 1
                if s.status == "error" or s.metadata.get("policy_violation", False):
                    policy_violations += 1

            # Extract safety flags from annotations or metadata
            is_safety_alert = s.metadata.get("safety_alert", False) or "safety" in s.name.lower() and s.status == "error"
            if is_safety_alert:
                safety_alerts.append({
                    "timestamp": s.start_time,
                    "span_name": s.name,
                    "message": s.metadata.get("safety_message", "Anomalous operation blocked"),
                    "severity": s.metadata.get("safety_severity", "high"),
                })

        return {
            "session": {
                "generated_at": time.time(),
                "total_spans": len(spans),
                "total_duration_sec": round(total_time, 4),
            },
            "governance": {
                "policy_checks": policy_checks,
                "policy_violations": policy_violations,
                "policy_pass_rate": round((policy_checks - policy_violations) / policy_checks, 4) if policy_checks > 0 else 1.0,
            },
            "security": {
                "total_safety_alerts": len(safety_alerts),
                "alerts": safety_alerts,
            },
        }

    @classmethod
    def render_cli_report(cls, spans: List[Span]) -> str:
        """Assembles a clean multi-line text-based console report card."""
        rep = cls.generate_report(spans)
        session = rep["session"]
        gov = rep["governance"]
        sec = rep["security"]

        lines = [
            "====================================================",
            "             KATTAPPA SESSION AUDIT REPORT           ",
            "====================================================",
            f" Total Spans Traced   : {session['total_spans']}",
            f" Session Duration     : {session['total_duration_sec']:.2f}s",
            "----------------------------------------------------",
            " Governance & Policies:",
            f"   Policy Invocations : {gov['policy_checks']}",
            f"   Violations Blocked : {gov['policy_violations']}",
            f"   Policy Pass Rate   : {gov['policy_pass_rate'] * 100:.2f}%",
            "----------------------------------------------------",
            " Security & Safety:",
            f"   Active Safety Alerts: {sec['total_safety_alerts']}",
        ]

        if sec["alerts"]:
            for alert in sec["alerts"]:
                lines.append(f"   [!] ALERT ({alert['severity'].upper()}): {alert['message']} in span '{alert['span_name']}'")
        else:
            lines.append("   ✓ No safety hazards identified.")

        lines.append("====================================================")
        return "\n".join(lines)
