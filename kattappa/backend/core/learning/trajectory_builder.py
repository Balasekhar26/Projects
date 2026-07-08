"""Structured Trajectory Builder (Program 14.0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Trajectory:
    goal_id: str
    plan_id: str
    planner_version: str
    success: bool
    predicted_duration: float
    actual_duration: float
    predicted_cost: float
    actual_cost: float
    failures_count: int
    recoveries_count: int
    combined_score: float
    nodes_executed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "plan_id": self.plan_id,
            "planner_version": self.planner_version,
            "success": self.success,
            "predicted_duration": self.predicted_duration,
            "actual_duration": self.actual_duration,
            "predicted_cost": self.predicted_cost,
            "actual_cost": self.actual_cost,
            "failures_count": self.failures_count,
            "recoveries_count": self.recoveries_count,
            "combined_score": self.combined_score,
            "nodes_executed": self.nodes_executed,
        }


class TrajectoryBuilder:
    """Reconstructs and compiles execution history events into structured Trajectory logs."""

    @staticmethod
    def build_trajectory(goal_id: str, events_payloads: List[Dict[str, Any]]) -> Trajectory:
        """Parses a sequential list of ledger event payloads to reconstruct the trajectory."""
        plan_id = "unknown"
        planner_version = "unknown"
        success = False
        pred_duration = 0.0
        actual_duration = 0.0
        pred_cost = 0.0
        actual_cost = 0.0
        failures = 0
        recoveries = 0
        score = 0.0
        nodes = []

        for p in events_payloads:
            transition = p.get("transition", "")
            
            # Extract plan/planner identifiers
            if "plan_id" in p:
                plan_id = p["plan_id"]
            if "planner_version" in p:
                planner_version = p["planner_version"]

            # Capture simulation predictions
            if "expected_duration" in p:
                pred_duration = float(p["expected_duration"])
            if "expected_cost" in p:
                pred_cost = float(p["expected_cost"])

            # Capture actual cost/duration on evaluation completions
            if transition == "EVALUATION_COMPLETE":
                score = float(p.get("combined_score", 0.0))

            # Record recoveries & retries
            if transition == "REPAIR_START":
                recoveries += 1
            if transition == "REPAIR_FAILURE":
                failures += 1

            # Check status outcomes
            status = p.get("status", "")
            if status == "COMPLETED" or p.get("transition") == "REPAIR_SUCCESS":
                success = True
            elif status in {"FAILED", "ABORTED"}:
                success = False

            # Add node traces if logged
            if "node_title" in p:
                nodes.append(p["node_title"])
            elif "failed_node_id" in p:
                nodes.append(f"failed:{p['failed_node_id']}")

        return Trajectory(
            goal_id=goal_id,
            plan_id=plan_id,
            planner_version=planner_version,
            success=success,
            predicted_duration=pred_duration,
            actual_duration=actual_duration,
            predicted_cost=pred_cost,
            actual_cost=actual_cost,
            failures_count=failures,
            recoveries_count=recoveries,
            combined_score=score,
            nodes_executed=nodes,
        )
