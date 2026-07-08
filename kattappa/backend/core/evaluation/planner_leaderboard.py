"""Planner Leaderboard Comparison System (Program 13.0).
"""
from __future__ import annotations

from typing import Dict, List
from backend.core.evaluation.scorecard import Scorecard


class PlannerLeaderboard:
    """Manages rankings and performance comparisons between multiple planner engine variants."""

    def __init__(self) -> None:
        self.leaderboard: Dict[str, Scorecard] = {}

    def register_scorecard(self, scorecard: Scorecard) -> None:
        """Registers or updates a planner version's performance scorecard."""
        self.leaderboard[scorecard.planner_version] = scorecard

    def get_rankings(self) -> List[Scorecard]:
        """Returns registered scorecards sorted by combined score in descending order."""
        return sorted(
            self.leaderboard.values(),
            key=lambda sc: sc.combined_score,
            reverse=True,
        )

    def get_scorecard(self, version: str) -> Scorecard | None:
        return self.leaderboard.get(version)
