"""
Goal Priority Scheduler — Ranks READY goals by composite urgency score.

Scoring formula:
    priority_score =
        0.40 × normalized_priority      (1–10 scale → 0.0–1.0)
        0.30 × deadline_urgency         (0.0 far future → 1.0 overdue)
        0.20 × confidence_score         (from goal.confidence field)
        0.10 × retry_freshness          (penalises goals that have been retried many times)

Usage:
    from backend.core.governance.goal_scheduler import GoalPriorityScheduler
    scheduler = GoalPriorityScheduler()
    ranked = scheduler.rank_ready_goals(goals)
"""
from __future__ import annotations

import time
from typing import Any

# Weight coefficients — must sum to 1.0
_W_PRIORITY = 0.40
_W_DEADLINE = 0.30
_W_CONFIDENCE = 0.20
_W_RETRY_FRESHNESS = 0.10

# Urgency horizon in seconds (7 days)
_URGENCY_HORIZON_SECS = 7 * 24 * 3600


class GoalPriorityScheduler:
    """
    Stateless goal ranker. Accepts a list of goal dicts and returns them sorted
    by composite urgency score in descending order (highest priority first).
    """

    def rank_ready_goals(self, goals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Ranks a list of READY goals by composite priority score.

        Non-READY goals are passed through unranked at the tail of the output.

        Args:
            goals: List of goal dicts from the ledger store.

        Returns:
            Goals sorted by priority_score descending (highest first).
            Each goal dict is returned with an injected `priority_score` field.
        """
        ready = []
        others = []
        for g in goals:
            if g.get("status") == "READY":
                score = self._compute_score(g)
                enriched = dict(g)
                enriched["priority_score"] = round(score, 4)
                ready.append(enriched)
            else:
                others.append(g)

        ready.sort(key=lambda g: g["priority_score"], reverse=True)
        return ready + others

    def compute_urgency_score(self, goal: dict[str, Any]) -> float:
        """
        Public convenience method: compute priority_score for a single goal.

        Args:
            goal: Goal dict.

        Returns:
            Float score in [0.0, 1.0].
        """
        return round(self._compute_score(goal), 4)

    # ─────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────

    def _compute_score(self, goal: dict[str, Any]) -> float:
        priority_norm = self._normalize_priority(goal.get("priority", 5))
        deadline_urg = self._deadline_urgency(goal.get("deadline_utc"))
        confidence = self._clamp(goal.get("confidence", 1.0))
        retry_fresh = self._retry_freshness(
            retry_count=goal.get("retry_count", 0),
            max_retries=goal.get("max_retries", 3),
        )
        return (
            _W_PRIORITY * priority_norm
            + _W_DEADLINE * deadline_urg
            + _W_CONFIDENCE * confidence
            + _W_RETRY_FRESHNESS * retry_fresh
        )

    @staticmethod
    def _normalize_priority(priority: int) -> float:
        """Normalises a 1–10 integer priority to [0.0, 1.0]."""
        clamped = max(1, min(10, int(priority)))
        return (clamped - 1) / 9.0

    @staticmethod
    def _deadline_urgency(deadline_utc: float | None) -> float:
        """
        Returns a deadline urgency score in [0.0, 1.0]:
        - 0.0 if no deadline or deadline > 7 days away
        - 1.0 if deadline is in the past (overdue)
        - Linear interpolation between now and 7 days out
        """
        if deadline_utc is None:
            return 0.0

        now = time.time()
        remaining = deadline_utc - now

        if remaining <= 0:
            return 1.0  # Overdue

        if remaining >= _URGENCY_HORIZON_SECS:
            return 0.0  # Far future

        return 1.0 - (remaining / _URGENCY_HORIZON_SECS)

    @staticmethod
    def _retry_freshness(retry_count: int, max_retries: int) -> float:
        """
        Penalises goals that have been retried many times.
        Fresh goals (retry_count=0) score 1.0; goals at max_retries score 0.0.
        """
        if max_retries <= 0:
            return 1.0
        ratio = retry_count / max_retries
        return max(0.0, 1.0 - ratio)

    @staticmethod
    def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, float(value)))
