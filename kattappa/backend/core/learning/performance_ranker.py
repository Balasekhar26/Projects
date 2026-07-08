"""Performance Ranker (Program 21.0).

Analyzes historical success rates, execution latencies, and costs to rank agents and tools.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List

from backend.core.learning.experience_store import ExperienceStore

logger = logging.getLogger(__name__)


class PerformanceRanker:
    """Aggregates metrics over historical trajectories to identify optimal execution choices."""

    @classmethod
    def rank_planners(cls, store: ExperienceStore) -> List[Dict[str, Any]]:
        """Calculates success rates and average scores for planner configurations.

        Returns planners ordered by success rate desc, then avg score desc.
        """
        if not store.trajectories:
            return []

        stats = defaultdict(lambda: {"runs": 0, "successes": 0, "score_sum": 0.0})
        
        for t in store.trajectories:
            v = t.planner_version or "unknown"
            stats[v]["runs"] += 1
            if t.success:
                stats[v]["successes"] += 1
            stats[v]["score_sum"] += t.combined_score

        ranked = []
        for version, data in stats.items():
            runs = data["runs"]
            rate = data["successes"] / runs if runs else 0.0
            avg_score = data["score_sum"] / runs if runs else 0.0
            
            ranked.append({
                "planner_version": version,
                "runs": runs,
                "success_rate": round(rate, 3),
                "average_score": round(avg_score, 2)
            })

        # Rank by success rate desc, then average score desc
        ranked.sort(key=lambda item: (-item["success_rate"], -item["average_score"]))
        return ranked

    @classmethod
    def rank_executed_nodes(cls, store: ExperienceStore) -> List[Dict[str, Any]]:
        """Computes failure frequency statistics for distinct action titles/nodes.

        Helps planner isolate fragile tools or tasks.
        """
        if not store.trajectories:
            return []

        stats = defaultdict(lambda: {"total": 0, "failures": 0})
        
        for t in store.trajectories:
            for node in t.nodes_executed:
                if node.startswith("failed:"):
                    raw_node = node.replace("failed:", "")
                    stats[raw_node]["failures"] += 1
                    stats[raw_node]["total"] += 1
                else:
                    stats[node]["total"] += 1

        ranked = []
        for node, data in stats.items():
            total = data["total"]
            fail_rate = data["failures"] / total if total else 0.0
            
            ranked.append({
                "node_title": node,
                "occurrences": total,
                "failures": data["failures"],
                "failure_rate": round(fail_rate, 3)
            })

        # Rank by failure rate desc (worst nodes first for warnings)
        ranked.sort(key=lambda item: (-item["failure_rate"], -item["failures"]))
        return ranked
