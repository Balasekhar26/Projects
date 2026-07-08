"""Unit tests for Program 15.0 Strategy Layer Foundation.
"""
from __future__ import annotations

import pytest
from backend.core.strategy.planner_router import PlannerRouter
from backend.core.strategy.model_router import ModelRouter
from backend.core.strategy.tool_selector import ToolSelector
from backend.core.strategy.strategy_store import StrategyDecision, StrategyStore
from backend.core.strategy.strategy_optimizer import StrategyOptimizer


# ─── PlannerRouter ──────────────────────────────────────────────────────────

class TestPlannerRouter:
    def test_routes_to_risk_aware_when_flagged(self):
        result = PlannerRouter.route_planner(
            task_complexity=3, latency_budget_seconds=30.0, requires_risk_aware=True
        )
        assert result == "RiskAware_Planner"

    def test_routes_to_fast_planner_under_latency_constraint(self):
        result = PlannerRouter.route_planner(
            task_complexity=2, latency_budget_seconds=3.0
        )
        assert result == "Fast_Planner"

    def test_routes_to_htn_for_high_complexity(self):
        result = PlannerRouter.route_planner(
            task_complexity=8, latency_budget_seconds=60.0
        )
        assert result == "HTN_Planner"

    def test_defaults_to_htn_for_simple_tasks(self):
        result = PlannerRouter.route_planner(
            task_complexity=1, latency_budget_seconds=120.0
        )
        assert result == "HTN_Planner"


# ─── ModelRouter ────────────────────────────────────────────────────────────

class TestModelRouter:
    def test_routes_to_local_for_low_budget(self):
        result = ModelRouter.route_model(
            task_category="general", dollar_budget=0.01, latency_budget_seconds=30.0
        )
        assert result == "local_small"

    def test_routes_to_local_for_tight_latency(self):
        result = ModelRouter.route_model(
            task_category="analysis", dollar_budget=1.0, latency_budget_seconds=1.0
        )
        assert result == "local_small"

    def test_routes_to_code_specialist_for_coding_tasks(self):
        result = ModelRouter.route_model(
            task_category="coding", dollar_budget=0.50, latency_budget_seconds=30.0
        )
        assert result == "code_specialist"

    def test_routes_to_cloud_reasoning_by_default(self):
        result = ModelRouter.route_model(
            task_category="planning", dollar_budget=2.0, latency_budget_seconds=60.0
        )
        assert result == "cloud_reasoning"


# ─── ToolSelector ───────────────────────────────────────────────────────────

class TestToolSelector:
    def test_selects_highest_success_rate_tool(self):
        selector = ToolSelector(default_success_rates={
            "BrowserTool": 0.65,
            "APITool": 0.96,
            "CLI_Tool": 0.88,
        })
        result = selector.select_best_tool(["BrowserTool", "APITool", "CLI_Tool"])
        assert result == "APITool"

    def test_respects_tabu_exclusions(self):
        selector = ToolSelector(default_success_rates={
            "BrowserTool": 0.65,
            "APITool": 0.96,
            "CLI_Tool": 0.88,
        })
        result = selector.select_best_tool(
            ["BrowserTool", "APITool", "CLI_Tool"],
            tabu_list={"APITool"},
        )
        assert result == "CLI_Tool"

    def test_alpha_update_adjusts_rate(self):
        selector = ToolSelector(default_success_rates={"MyTool": 0.5})
        selector.update_success_rate("MyTool", success=True)
        # Expected: 0.5 + 0.1 * (1.0 - 0.5) = 0.55
        assert selector.success_rates["MyTool"] == pytest.approx(0.55, rel=1e-3)


# ─── StrategyStore ──────────────────────────────────────────────────────────

class TestStrategyStore:
    def test_records_and_updates_outcome(self):
        store = StrategyStore()
        decision = StrategyDecision(
            goal_id="g-1", planner="HTN_Planner", model="cloud_reasoning",
            tool="APITool", context={}
        )
        store.record(decision)
        store.update_outcome("g-1", success=True, score=90.0)

        all_decisions = store.get_all()
        assert len(all_decisions) == 1
        assert all_decisions[0].success is True
        assert all_decisions[0].score == 90.0

    def test_planner_success_rate_aggregation(self):
        store = StrategyStore()
        for i in range(3):
            d = StrategyDecision(
                goal_id=f"g-{i}", planner="HTN_Planner",
                model="cloud_reasoning", tool="APITool", context={}
            )
            store.record(d)
            store.update_outcome(f"g-{i}", success=(i < 2), score=80.0)

        rates = store.get_planner_success_rates()
        # 2 successes out of 3 runs
        assert rates["HTN_Planner"] == pytest.approx(0.667, rel=1e-2)


# ─── StrategyOptimizer ──────────────────────────────────────────────────────

class TestStrategyOptimizer:
    def test_recommends_local_model_on_network_instability(self):
        optimizer = StrategyOptimizer()
        rec = optimizer.recommend({"network_unstable": True})
        assert rec.model == "local_small"
        assert rec.planner == "Fast_Planner"
        assert any("Network instability" in r for r in rec.reasoning)

    def test_promotes_risk_aware_on_high_failure_rate(self):
        optimizer = StrategyOptimizer()
        rec = optimizer.recommend({
            "planner_failure_rate": 0.40,
            "network_unstable": False,
        })
        assert rec.planner == "RiskAware_Planner"

    def test_no_changes_on_healthy_context(self):
        optimizer = StrategyOptimizer()
        rec = optimizer.recommend({
            "network_unstable": False,
            "dollar_budget": 1.0,
            "planner_failure_rate": 0.05,
            "cost_overrun_rate": 0.05,
            "current_planner": "HTN_Planner",
            "current_model": "cloud_reasoning",
        })
        assert rec.planner == "HTN_Planner"
        assert rec.model == "cloud_reasoning"
        assert "No contextual anomalies" in rec.reasoning[0]
