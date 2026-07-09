"""Unit tests for Program 37.0: Autonomous Cognitive Loop Orchestrator.

Verifies full planning, selection, execution, evaluation, and reflection sequence cycles.
"""
from __future__ import annotations

import tempfile
import pytest

from backend.core.planning.goal import Goal
from backend.core.planning.task import Plan, Operator, PlannerState
from backend.core.planning.planner import HTNPlanner
from backend.core.planning.checkpoint_recovery import CheckpointRecovery
from backend.core.planning.resumable_runtime import ResumableWorkflowRuntime
from backend.core.orchestrator import CognitiveOrchestrator


@pytest.fixture
def setup_loop_env():
    # 1. Goal definition
    goal = Goal(
        goal_id="goal_solve",
        name="solve_task",
        constraints=["op_step"],
        reward=10.0,
    )

    # 2. HTN Planner registered with a simple baseline operator
    planner = HTNPlanner()
    op_base = Operator(
        operator_id="op_base",
        name="op_step",
        preconditions={"state": "A"},
        effects={"state": "B"},
        estimated_cost=2.0,
        estimated_time=5.0,
    )
    planner.register_operator(op_base)

    # 3. Setup substitution map for counterfactuals (better fast substitute)
    op_fast = Operator(
        operator_id="op_fast",
        name="op_step_fast",
        preconditions={"state": "A"},
        effects={"state": "B"},
        estimated_cost=1.0,
        estimated_time=2.0,
    )
    sub_map = {"op_step": [op_fast]}

    # 4. Standard weights and probabilities
    probs = {"op_step": 0.90, "op_step_fast": 0.99}
    weights = {"w_success": 1.0, "w_cost": 0.1, "w_duration": 0.05, "w_risk": 0.2}

    return goal, planner, sub_map, probs, weights


# ── Cognitive Orchestrator Loop Tests ─────────────────────────────────────────

class TestCognitiveOrchestrator:
    def test_run_cognitive_cycle_success_optimal_selection(self, setup_loop_env):
        goal, planner, sub_map, probs, weights = setup_loop_env
        
        with tempfile.TemporaryDirectory() as tmp:
            ckpt_engine = CheckpointRecovery(storage_dir=tmp)
            runtime = ResumableWorkflowRuntime(checkpoint_engine=ckpt_engine)
            orchestrator = CognitiveOrchestrator(runtime=runtime)
            
            initial_state = PlannerState(current_goal="solve_task", variables={"state": "A"})
            
            executed = []
            def step_executor(op: Operator):
                executed.append(op.name)

            # Executing cycle
            result = orchestrator.run_cognitive_cycle(
                goal=goal,
                initial_state=initial_state,
                htn_planner=planner,
                step_executor=step_executor,
                success_probability_map=probs,
                scenario_weights=weights,
                operator_substitution_map=sub_map,
            )
            
            assert result["status"] == "success"
            # It should have selected the fast plan alternative
            assert result["selected_plan_id"].endswith("_alt_op_fast")
            assert result["execution_outcome"]["status"] == "completed"
            assert result["execution_outcome"]["variables"]["state"] == "B"
            
            # Outcome score verification
            assert result["evaluation"]["is_success"] is True
            assert result["evaluation"]["score"] > 0.70
            
            # Counterfactual validation
            assert "optimal_plan_id" in result["counterfactual_utility"]
            # We already picked the fast alternative, so utility delta should be 0.0
            assert result["counterfactual_utility"]["utility_delta"] == 0.0

    def test_run_cognitive_cycle_failed_execution(self, setup_loop_env):
        goal, planner, sub_map, probs, weights = setup_loop_env
        
        with tempfile.TemporaryDirectory() as tmp:
            ckpt_engine = CheckpointRecovery(storage_dir=tmp)
            runtime = ResumableWorkflowRuntime(checkpoint_engine=ckpt_engine)
            orchestrator = CognitiveOrchestrator(runtime=runtime)
            
            initial_state = PlannerState(current_goal="solve_task", variables={"state": "A"})
            
            def step_executor(op: Operator):
                raise TimeoutError("Execution timed out")

            # Executing cycle
            result = orchestrator.run_cognitive_cycle(
                goal=goal,
                initial_state=initial_state,
                htn_planner=planner,
                step_executor=step_executor,
                success_probability_map=probs,
                scenario_weights=weights,
                operator_substitution_map=sub_map,
            )
            
            assert result["status"] == "failed"
            assert result["execution_outcome"]["status"] == "failed"
            assert result["execution_outcome"]["failure_type"] == "TIMEOUT"
            
            # Reflection contains crashed details
            assert "FAILURE" in result["reflection"]
            assert "deadline" in result["reflection"]
