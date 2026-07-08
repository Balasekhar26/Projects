"""Trajectory Analyzer (Program 21.0).

Mines execution logs to identify failure hotspots and extract planning warnings.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List

from backend.core.learning.experience_store import ExperienceStore
from backend.core.learning.trajectory_builder import Trajectory

logger = logging.getLogger(__name__)


class TrajectoryAnalyzer:
    """Analyzes execution traces to discover repetitive error states and warning logs."""

    @classmethod
    def compile_failure_diagnostics(cls, store: ExperienceStore) -> Dict[str, Any]:
        """Scans failed trajectories to locate fragile nodes, rollbacks, and recovery counts."""
        failed = [t for t in store.trajectories if not t.success]
        if not failed:
            return {"status": "healthy", "failure_hotspots": [], "total_failures": 0}

        # Count nodes that frequently fail
        failed_nodes_counter: Counter[str] = Counter()
        total_recoveries = 0

        for t in failed:
            total_recoveries += t.recoveries_count
            for node in t.nodes_executed:
                if node.startswith("failed:"):
                    failed_nodes_counter[node.replace("failed:", "")] += 1

        # Format hotspots
        hotspots = []
        for node, count in failed_nodes_counter.most_common(5):
            hotspots.append({
                "node_title": node,
                "fail_count": count,
                "percentage_of_failures": round(count / len(failed), 3)
            })

        logger.info(
            "TrajectoryAnalyzer: Compiled %d failures. Hotspots: %s",
            len(failed), [item["node_title"] for item in hotspots]
        )

        return {
            "status": "warning",
            "total_failures": len(failed),
            "total_repair_attempts": total_recoveries,
            "failure_hotspots": hotspots
        }

    @classmethod
    def generate_planning_warnings(cls, store: ExperienceStore) -> List[str]:
        """Generates dynamic planning constraints/rules to prevent recurring traps.

        If a node fails in > 50% of its runs, creates an explicit planning warning.
        """
        failed_stats = cls.compile_failure_diagnostics(store)
        warnings = []

        for hotspot in failed_stats.get("failure_hotspots", []):
            rate = hotspot["percentage_of_failures"]
            if rate >= 0.50:
                warnings.append(
                    f"Warning: Node '{hotspot['node_title']}' has failed in {rate * 100:.1f}% "
                    f"of recorded failed trajectories. Review dependencies or preconditions."
                )

        return warnings
