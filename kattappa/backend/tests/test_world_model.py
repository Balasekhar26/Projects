"""Unit tests for Program 42.0: World Model Engine.

Verifies state transition predictions, multi-step trajectory simulated roll-forwards,
and resource budget depletion boundaries.
"""
from __future__ import annotations

import pytest

from backend.core.planning.task import PlannerState, Operator
from backend.core.planning import WorldModelEngine


@pytest.fixture
def base_planner_state():
    return PlannerState(
        current_goal="test_goal",
        variables={"auth": True, "budget": 10.0, "time_elapsed": 0.0},
    )


# ── World Model Engine Tests ──────────────────────────────────────────────────

class TestWorldModel:
    def test_predict_transition_effects_and_budget(self, base_planner_state):
        action = Operator(
            operator_id="op_network",
            name="download_file",
            preconditions={"auth": True},
            effects={"has_file": True},
            estimated_cost=2.0,
            estimated_time=4.0,
        )

        next_state = WorldModelEngine.predict_transition(base_planner_state, action)
        
        # Verify effects applied
        assert next_state.variables["has_file"] is True
        # Verify resources evolved (10.0 - 2.0 = 8.0)
        assert next_state.variables["budget"] == 8.0
        assert next_state.variables["time_elapsed"] == 4.0
        assert "op_network" in next_state.visited_nodes

    def test_simulate_trajectory_feasible(self, base_planner_state):
        op1 = Operator(
            operator_id="op_1",
            name="step_one",
            preconditions={"auth": True},
            effects={"step_one_done": True},
            estimated_cost=1.0,
            estimated_time=2.0,
        )
        op2 = Operator(
            operator_id="op_2",
            name="step_two",
            preconditions={"step_one_done": True},
            effects={"step_two_done": True},
            estimated_cost=2.0,
            estimated_time=3.0,
        )

        res = WorldModelEngine.simulate_trajectory(base_planner_state, [op1, op2])
        
        assert res["is_feasible"] is True
        assert res["projected_cost"] == 3.0
        assert res["projected_duration"] == 5.0
        assert res["final_variables"]["step_two_done"] is True
        assert res["final_variables"]["budget"] == 7.0
        # Success probability joint product (0.95 * 0.95 = 0.9025)
        assert res["final_confidence"] == 0.9025

    def test_simulate_trajectory_budget_drained(self, base_planner_state):
        # Action that costs more than the starting budget (10.0)
        op_expensive = Operator(
            operator_id="op_exp",
            name="run_heavy_compute",
            preconditions={"auth": True},
            effects={"done": True},
            estimated_cost=12.0,
            estimated_time=10.0,
        )

        res = WorldModelEngine.simulate_trajectory(base_planner_state, [op_expensive])
        
        # Should be unfeasible due to budget depletion (<= 0.0)
        assert res["is_feasible"] is False
        assert "budget" in res["failure_reason"]
