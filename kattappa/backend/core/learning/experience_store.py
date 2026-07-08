"""Thread-Safe Experience Store Database Registry (Program 14.0).
"""
from __future__ import annotations

import threading
from typing import Dict, List, Optional
from backend.core.learning.trajectory_builder import Trajectory


class ExperienceStore:
    """Provides thread-safe access to stored execution trajectories for offline analytics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.trajectories: List[Trajectory] = []

    def add_trajectory(self, trajectory: Trajectory) -> None:
        """Stores a new trajectory trace in the experience buffer."""
        with self._lock:
            self.trajectories.append(trajectory)

    def get_successful_trajectories(self) -> List[Trajectory]:
        with self._lock:
            return [t for t in self.trajectories if t.success]

    def get_failed_trajectories(self) -> List[Trajectory]:
        with self._lock:
            return [t for t in self.trajectories if not t.success]

    def get_recovered_trajectories(self) -> List[Trajectory]:
        with self._lock:
            return [t for t in self.trajectories if t.recoveries_count > 0]

    def get_performance_summary(self, planner_version: str) -> Dict[str, float]:
        """Performs analytical pattern mining over the recorded trajectories."""
        with self._lock:
            filtered = [t for t in self.trajectories if t.planner_version == planner_version]
            if not filtered:
                return {}

            total = len(filtered)
            successes = sum(1 for t in filtered if t.success)
            total_score = sum(t.combined_score for t in filtered)
            total_recoveries = sum(t.recoveries_count for t in filtered)

            return {
                "total_runs": float(total),
                "success_rate": round(successes / total, 3),
                "average_score": round(total_score / total, 2),
                "average_recoveries": round(total_recoveries / total, 2),
            }

    def clear(self) -> None:
        with self._lock:
            self.trajectories.clear()
