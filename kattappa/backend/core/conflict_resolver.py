"""Conflict Resolver — Phase K11.5.

Arbitrates conflicting signals from Planner, World Model risk checks, Scientist
evidence metrics, and Wisdom Engine principles, and decides the final dominant
execution path.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass
class ConflictResolutionDecision:
    action: str  # PROCEED, HALT, DEGRADE_PLAN, USER_APPROVAL_REQUIRED
    dominant_factor: str  # WISDOM, SAFETY_RISK, SCIENTIST_UNCERTAINTY, PLANNER
    confidence: float
    explanation: str


class ConflictResolver:
    """Arbitrates clashing system decisions using priority-ordered rules."""

    @classmethod
    def resolve(
        cls,
        planner_advice: Dict[str, Any],
        world_model_risk: Dict[str, Any],
        scientist_evidence: Dict[str, Any],
        wisdom_guidance: Optional[Dict[str, Any]] = None,
        user_policy: Optional[Dict[str, Any]] = None,
    ) -> ConflictResolutionDecision:
        """Arbitrate advice and return the resolved system-level decision.

        Priority Order:
        1. Wisdom Engine: Strict ethical blocks/gates (always overrides plans).
        2. World Model: Severe risk blocks/gates (override plans, trigger throttle/halt).
        3. Scientist Engine: Falsification signals (degrade plan confidence or request review).
        4. Planner Strategy: Default direction when no high-priority blocks exist.
        """
        log_event("conflict_resolver_start", "Resolving potential plan conflicts")

        # ── 1. Wisdom Engine check ──────────────────────────────────────────
        if wisdom_guidance:
            # Check if wisdom advice indicates an ethical, duty, or safety block
            block_flag = wisdom_guidance.get("block_action", False)
            if block_flag:
                desc = wisdom_guidance.get("reason") or "Wisdom Engine advised action halt due to value principles"
                log_event("conflict_resolved_wisdom_block", f"Wisdom override triggered: {desc}")
                return ConflictResolutionDecision(
                    action="HALT",
                    dominant_factor="WISDOM",
                    confidence=0.99,
                    explanation=f"Wisdom Engine Override: {desc}"
                )

        # ── 2. World Model Risk check ────────────────────────────────────────
        risk_score = float(world_model_risk.get("risk_score", 0.0))
        # Severe safety risks trigger immediate halts
        if risk_score >= 0.85:
            desc = world_model_risk.get("risk_description") or f"Severe safety hazard detected (risk={risk_score})"
            log_event("conflict_resolved_safety_halt", f"Safety risk halt triggered: {desc}")
            return ConflictResolutionDecision(
                action="HALT",
                dominant_factor="SAFETY_RISK",
                confidence=0.95,
                explanation=f"World Model Safety Gate: {desc}"
            )
        # Moderate safety risks require operator review
        elif risk_score >= 0.50:
            desc = world_model_risk.get("risk_description") or f"Moderate safety hazard detected (risk={risk_score})"
            log_event("conflict_resolved_safety_approval", f"Safety risk approval triggered: {desc}")
            return ConflictResolutionDecision(
                action="USER_APPROVAL_REQUIRED",
                dominant_factor="SAFETY_RISK",
                confidence=0.85,
                explanation=f"World Model Safety Gate: {desc}"
            )

        # ── 3. Scientist Engine check ────────────────────────────────────────
        scientist_p = float(scientist_evidence.get("p_survival", 1.0))
        # Falsification signals lower final confidence and can force plan degradation
        if scientist_p < 0.50:
            desc = scientist_evidence.get("details") or f"Scientist engine detected high uncertainty (P={scientist_p})"
            log_event("conflict_resolved_scientist_halt", f"Scientist engine halt triggered: {desc}")
            return ConflictResolutionDecision(
                action="HALT",
                dominant_factor="SCIENTIST_UNCERTAINTY",
                confidence=0.90,
                explanation=f"Scientist Engine Falsification Gate: {desc}"
            )
        elif scientist_p < 0.95:
            desc = scientist_evidence.get("details") or f"Scientist engine detected moderate uncertainty (P={scientist_p})"
            log_event("conflict_resolved_scientist_degrade", f"Scientist engine degradation triggered: {desc}")
            return ConflictResolutionDecision(
                action="DEGRADE_PLAN",
                dominant_factor="SCIENTIST_UNCERTAINTY",
                confidence=0.80,
                explanation=f"Scientist Engine Falsification Gate: {desc}"
            )

        # ── 4. Planner Strategy (Default) ───────────────────────────────────
        action = planner_advice.get("action", "PROCEED")
        confidence = float(planner_advice.get("confidence", 1.0))
        desc = planner_advice.get("details") or "Nominal planner execution path"
        log_event("conflict_resolved_planner_default", f"Planner strategy accepted: {action}")
        return ConflictResolutionDecision(
            action=action,
            dominant_factor="PLANNER",
            confidence=confidence,
            explanation=desc
        )
