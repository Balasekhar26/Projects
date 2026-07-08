"""Unit tests for Program 14.0 Experience Layer Foundation.
"""
from __future__ import annotations

import pytest
from backend.core.learning.experience_store import ExperienceStore
from backend.core.learning.trajectory_builder import Trajectory, TrajectoryBuilder
from backend.core.learning.trace_collector import TraceCollector


def test_trajectory_builder_compiles_correctly():
    """Verifies that builder parses list of event payloads to calculate metrics."""
    events = [
        {"plan_id": "p-1", "planner_version": "HTN-v1.1", "expected_duration": 12.5, "expected_cost": 1.5},
        {"node_title": "VerifyHardware"},
        {"transition": "REPAIR_START", "failed_node_id": "DownloadBinary"},
        {"transition": "REPAIR_SUCCESS", "status": "COMPLETED"},
        {"transition": "EVALUATION_COMPLETE", "combined_score": 85.5},
    ]

    trajectory = TrajectoryBuilder.build_trajectory("goal-1", events)

    assert trajectory.goal_id == "goal-1"
    assert trajectory.plan_id == "p-1"
    assert trajectory.planner_version == "HTN-v1.1"
    assert trajectory.success is True
    assert trajectory.predicted_duration == 12.5
    assert trajectory.predicted_cost == 1.5
    assert trajectory.failures_count == 0
    assert trajectory.recoveries_count == 1
    assert trajectory.combined_score == 85.5
    assert "VerifyHardware" in trajectory.nodes_executed
    assert "failed:DownloadBinary" in trajectory.nodes_executed


def test_experience_store_filters_and_summaries():
    """Verifies storing, filtering, and summary calculations in ExperienceStore."""
    store = ExperienceStore()

    t1 = Trajectory(
        goal_id="g-1",
        plan_id="p-1",
        planner_version="HTN-v1.1",
        success=True,
        predicted_duration=10.0,
        actual_duration=10.0,
        predicted_cost=1.0,
        actual_cost=1.0,
        failures_count=0,
        recoveries_count=0,
        combined_score=95.0,
    )

    t2 = Trajectory(
        goal_id="g-2",
        plan_id="p-2",
        planner_version="HTN-v1.1",
        success=True,
        predicted_duration=20.0,
        actual_duration=25.0,
        predicted_cost=2.0,
        actual_cost=2.0,
        failures_count=0,
        recoveries_count=2,  # recovered run
        combined_score=80.0,
    )

    t3 = Trajectory(
        goal_id="g-3",
        plan_id="p-3",
        planner_version="HTN-v1.2",  # different version
        success=False,                # failed run
        predicted_duration=5.0,
        actual_duration=5.0,
        predicted_cost=0.5,
        actual_cost=0.5,
        failures_count=1,
        recoveries_count=0,
        combined_score=0.0,
    )

    store.add_trajectory(t1)
    store.add_trajectory(t2)
    store.add_trajectory(t3)

    # Filter checks
    assert len(store.get_successful_trajectories()) == 2
    assert len(store.get_failed_trajectories()) == 1
    assert len(store.get_recovered_trajectories()) == 1

    # Analytical summaries check
    summary_v1_1 = store.get_performance_summary("HTN-v1.1")
    assert summary_v1_1["total_runs"] == 2.0
    assert summary_v1_1["success_rate"] == 1.0
    assert summary_v1_1["average_score"] == 87.5
    assert summary_v1_1["average_recoveries"] == 1.0


def test_trace_collector_ingest():
    """Verifies that TraceCollector saves trajectories and outputs structured logs."""
    store = ExperienceStore()
    collector = TraceCollector(store)

    events = [
        {"plan_id": "p-9", "planner_version": "MCTS-v1.0", "expected_duration": 5.0},
        {"node_title": "RunDiagnostics"},
        {"status": "FAILED"},
    ]

    trajectory = collector.collect_events("goal-9", events)

    assert trajectory.success is False
    assert trajectory.planner_version == "MCTS-v1.0"
    
    # Check stored trajectory in the experience store
    assert len(store.trajectories) == 1
    assert store.trajectories[0].goal_id == "goal-9"
