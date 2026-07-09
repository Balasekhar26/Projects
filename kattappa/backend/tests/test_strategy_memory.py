"""Unit tests for Program 39.0: Lifelong Strategy & Policy Memory.

Verifies trace consolidation, strategy retriever searches, macro sequence caches,
and experience weight adjustments.
"""
from __future__ import annotations

import tempfile
import pytest

from backend.core.planning.task import Plan, Operator
from backend.core.planning import (
    StrategyMemory,
    PolicyConsolidationEngine,
    StrategyRetriever,
    MacroActionLibrary,
    ExperienceDistillationEngine,
)


@pytest.fixture
def memory_db():
    with tempfile.TemporaryDirectory() as tmp:
        yield StrategyMemory(storage_dir=tmp)


@pytest.fixture
def sample_plan():
    op = Operator(
        operator_id="op_custom",
        name="op_1",
        preconditions={"auth": True},
        effects={"state": "ready"},
    )
    return Plan(
        plan_id="plan_abc",
        goal_id="goal_setup",
        steps=[op],
        expected_cost=2.0,
        expected_duration=5.0,
        expected_reward=10.0,
    )


# ── Strategy Memory Tests ─────────────────────────────────────────────────────

class TestStrategyMemory:
    def test_store_and_retrieve_strategy(self, memory_db):
        retriever = StrategyRetriever(memory_db)
        
        steps = [{"name": "op_1", "operator_id": "op_custom"}]
        policy_id = retriever.store_policy(
            goal_name="goal_setup",
            constraints=["auth"],
            steps=steps,
            score=0.90,
        )
        
        assert policy_id.startswith("policy_")
        
        # Retrieve match
        match = retriever.retrieve_strategy("goal_setup", ["auth"])
        assert match is not None
        assert match["policy_id"] == policy_id
        assert match["steps"] == steps
        
        # Unmatched constraint list should return None
        no_match = retriever.retrieve_strategy("goal_setup", ["missing"])
        assert no_match is None

    def test_policy_consolidation_filters(self, memory_db, sample_plan):
        # 1. Failed execution -> should NOT consolidate
        eval_failed = {"is_success": False, "score": 0.0}
        ckpt1 = PolicyConsolidationEngine.consolidate_trace(sample_plan, eval_failed, memory_db)
        assert ckpt1 is None

        # 2. Low score success (e.g. 0.6) -> should NOT consolidate
        eval_low = {"is_success": True, "score": 0.60}
        ckpt2 = PolicyConsolidationEngine.consolidate_trace(sample_plan, eval_low, memory_db)
        assert ckpt2 is None

        # 3. High score success (e.g. 0.85) -> consolidated successfully!
        eval_high = {"is_success": True, "score": 0.85}
        ckpt3 = PolicyConsolidationEngine.consolidate_trace(sample_plan, eval_high, memory_db)
        assert ckpt3 is not None
        assert ckpt3.startswith("policy_")

        # Verify it exists in database
        retriever = StrategyRetriever(memory_db)
        match = retriever.retrieve_strategy("goal_setup", ["auth"])
        assert match is not None
        assert match["policy_id"] == ckpt3

    def test_macro_action_library(self, memory_db):
        lib = MacroActionLibrary(memory_db)
        steps = [{"name": "op_1"}, {"name": "op_2"}]
        
        lib.register_macro("compile_workflow", steps)
        
        # Fetch macro
        loaded = lib.get_macro("compile_workflow")
        assert loaded == steps
        
        assert lib.get_macro("unknown") is None

    def test_experience_distillation_weights(self):
        # Scenario 1: Stable successful profile
        past_runs_good = [
            {"is_success": True, "cost_variance_ratio": 1.0, "duration_variance_ratio": 1.0},
        ]
        w_good = ExperienceDistillationEngine.distill_weights_adjustment(past_runs_good)
        assert w_good["w_risk"] == 0.2
        assert w_good["w_cost"] == 0.1

        # Scenario 2: High failure rate (e.g., 2 failures in 3 runs > 30%)
        past_runs_bad = [
            {"is_success": False, "cost_variance_ratio": 1.0, "duration_variance_ratio": 1.0},
            {"is_success": False, "cost_variance_ratio": 1.0, "duration_variance_ratio": 1.0},
            {"is_success": True, "cost_variance_ratio": 1.0, "duration_variance_ratio": 1.0},
        ]
        w_bad = ExperienceDistillationEngine.distill_weights_adjustment(past_runs_bad)
        # Should raise risk avoidance and decrease success reward weight
        assert w_bad["w_risk"] == 0.5
        assert w_bad["w_success"] == 0.8

        # Scenario 3: High cost variance ratio
        past_runs_costly = [
            {"is_success": True, "cost_variance_ratio": 1.5, "duration_variance_ratio": 1.0},
        ]
        w_costly = ExperienceDistillationEngine.distill_weights_adjustment(past_runs_costly)
        assert w_costly["w_cost"] == 0.3
