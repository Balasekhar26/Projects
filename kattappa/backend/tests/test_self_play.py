"""Unit tests for Program 41.0: Background Counterfactual Self-Play.

Verifies plan self-play simulations, utility scores selections, and auto-registration
into lifelong memory databases.
"""
from __future__ import annotations

import tempfile
import pytest

from backend.core.planning.goal import Goal
from backend.core.planning.task import PlannerState, Operator
from backend.core.planning.planner import HTNPlanner
from backend.core.planning import (
    StrategyMemory,
    StrategyRetriever,
    BackgroundSelfPlayEngine,
)


@pytest.fixture
def self_play_env():
    goal = Goal(
        goal_id="self_play_goal",
        name="test_self_play",
        constraints=["op_main"],
        reward=10.0,
    )
    
    planner = HTNPlanner()
    op_base = Operator(
        operator_id="op_base",
        name="op_main",
        preconditions={"status": "init"},
        effects={"status": "completed"},
        estimated_cost=3.0,
        estimated_time=8.0,
    )
    planner.register_operator(op_base)

    op_fast = Operator(
        operator_id="op_fast",
        name="op_fast_step",
        preconditions={"status": "init"},
        effects={"status": "completed"},
        estimated_cost=1.0,
        estimated_time=2.0,
    )

    sub_map = {"op_main": [op_fast]}
    probs = {"op_main": 0.85, "op_fast_step": 0.99}
    weights = {"w_success": 1.0, "w_cost": 0.1, "w_duration": 0.05, "w_risk": 0.2}

    return goal, planner, sub_map, probs, weights


# ── Self-Play Engine Tests ────────────────────────────────────────────────────

class TestSelfPlay:
    def test_run_self_play_simulation_success(self, self_play_env):
        goal, planner, sub_map, probs, weights = self_play_env
        
        with tempfile.TemporaryDirectory() as tmp:
            memory = StrategyMemory(storage_dir=tmp)
            initial_state = PlannerState(current_goal="test_self_play", variables={"status": "init"})

            result = BackgroundSelfPlayEngine.run_self_play_simulation(
                goal=goal,
                initial_state=initial_state,
                htn_planner=planner,
                operator_substitution_map=sub_map,
                success_probability_map=probs,
                scenario_weights=weights,
                strategy_memory=memory,
            )

            assert result["status"] == "completed"
            assert result["best_plan_id"] is not None
            assert result["best_plan_id"].endswith("_alt_op_fast")
            assert result["best_utility"] > 0.0
            
            # Since the simulated score is high, it must have registered the policy
            assert result["registered_policy_id"] is not None
            
            # Query retriever to verify the dynamic policy is persisted
            retriever = StrategyRetriever(memory)
            match = retriever.retrieve_strategy("self_play_goal", ["status"])
            assert match is not None
            assert match["policy_id"] == result["registered_policy_id"]
            assert match["steps"][0]["name"] == "op_fast_step"
