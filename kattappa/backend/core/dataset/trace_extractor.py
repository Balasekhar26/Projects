"""Trace Extractor (Program 26.0).

Converts Trajectory objects from ExperienceStore into raw extraction records
suitable for dataset construction.
"""
from __future__ import annotations

from typing import Any, Dict, List

from backend.core.learning.trajectory_builder import Trajectory


class TraceExtractor:
    """Converts execution trajectories into structured extraction records."""

    @classmethod
    def extract(cls, trajectory: Trajectory) -> Dict[str, Any]:
        """Extracts one JSONL-ready record from a single Trajectory.

        Output schema:
            instruction   : str   — goal_id phrased as a user instruction
            context       : dict  — planner version, prediction estimates
            reasoning_trace: str  — comma-joined sequence of executed nodes
            actions       : list  — nodes_executed list
            result        : str   — "success" | "failure" | "recovered"
            metrics       : dict  — actual duration, cost, combined_score
        """
        if trajectory.recoveries_count > 0 and trajectory.success:
            result = "recovered"
        elif trajectory.success:
            result = "success"
        else:
            result = "failure"

        return {
            "instruction": trajectory.goal_id,
            "context": {
                "planner_version": trajectory.planner_version,
                "predicted_duration": trajectory.predicted_duration,
                "predicted_cost": trajectory.predicted_cost,
            },
            "reasoning_trace": " -> ".join(trajectory.nodes_executed) if trajectory.nodes_executed else "",
            "actions": list(trajectory.nodes_executed),
            "result": result,
            "metrics": {
                "duration": trajectory.actual_duration,
                "cost": trajectory.actual_cost,
                "combined_score": trajectory.combined_score,
                "failures": trajectory.failures_count,
                "recoveries": trajectory.recoveries_count,
            },
        }

    @classmethod
    def extract_all(cls, trajectories: List[Trajectory]) -> List[Dict[str, Any]]:
        """Batch-extracts records from a list of trajectories."""
        return [cls.extract(t) for t in trajectories]
