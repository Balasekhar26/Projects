"""Unit tests for Program 12.3 Planner Simulator.
"""
from __future__ import annotations

import pytest
from backend.core.planning.task_library import TaskLibrary
from backend.core.planning.htn_planner import HTNPlanner
from backend.core.planning.simulator import PlannerSimulator
from backend.core.planning.utility_estimator import UtilityEstimator


def test_planner_simulator_deterministic_and_probabilistic_aggregation():
    """Verifies duration critical path, variance summation, and joint probability calculations."""
    planner = HTNPlanner()
    simulator = PlannerSimulator()

    # Generate the standard 5-step plan:
    # VerifyHardware (2.0s, var 0.1)
    # DownloadBinary (10.0s, var 0.1)
    # ConfigureSettings (3.0s, var 0.1)
    # RunDiagnostics (5.0s, var 0.1)
    # GenerateReport (1.5s, var 0.1)
    # Joint success prob: 0.99 * 0.92 * 0.98 * 0.95 * 0.99 = 0.839
    plan = planner.generate_plan(
        goal_id="demo-goal",
        root_task_name="PrepareDemoSystem",
        initial_state=["internet_available"]
    )

    # Simulate under standard state
    world_state = {"goal_reward": 100.0}
    result = simulator.simulate_plan(plan, world_state)

    # 1. Verify durations & path: critical path duration should be 19.5s
    assert result.expected_duration == 19.5
    path_titles = [plan.graph.nodes[nid].title for nid in result.metadata["critical_path"]]
    assert path_titles == ["DownloadBinary", "ConfigureSettings", "RunDiagnostics", "GenerateReport"]

    # 2. Verify variance along critical path (4 nodes * 0.1 = 0.4)
    assert result.duration_variance == 0.4

    # 3. Verify joint success probability product (~0.839)
    assert result.success_probability == 0.839


def test_planner_simulator_risk_and_failures():
    """Verifies SCM environment risk boosting and failure predictions."""
    planner = HTNPlanner()
    simulator = PlannerSimulator()

    plan = planner.generate_plan(
        goal_id="demo-goal",
        root_task_name="PrepareDemoSystem",
        initial_state=["internet_available"]
    )

    # 1. Clean run - no risk boost
    world_state_ok = {"goal_reward": 100.0, "internet_instability": False}
    result_ok = simulator.simulate_plan(plan, world_state_ok)
    assert result_ok.risk_score <= 0.35
    assert len(result_ok.failure_modes) == 1
    assert "low base success probability" in result_ok.failure_modes[0]

    # 2. Risk boost & failure modes under internet instability
    world_state_unstable = {"goal_reward": 100.0, "internet_instability": True}
    result_unstable = simulator.simulate_plan(plan, world_state_unstable)
    
    # Risk should be boosted due to online task DownloadBinary
    assert result_unstable.risk_score >= 0.6
    assert len(result_unstable.failure_modes) == 2
    # Ensure one of them is the internet instability failure mode
    internet_fail = [f for f in result_unstable.failure_modes if "internet is marked unstable" in f]
    assert len(internet_fail) == 1



def test_utility_estimator_math():
    """Verifies utility calculations mathematically."""
    estimator = UtilityEstimator(cost_weight=2.0, risk_weight=15.0)

    # Utility = (success_probability * reward) - (expected_cost * cost_weight) - (risk_score * risk_weight)
    # Utility = (0.8 * 100) - (1.5 * 2.0) - (0.2 * 15.0) = 80 - 3.0 - 3.0 = 74.0
    utility = estimator.calculate_utility(
        success_probability=0.8,
        reward=100.0,
        expected_cost=1.5,
        risk_score=0.2
    )
    assert utility == 74.0
