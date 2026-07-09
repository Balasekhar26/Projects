"""Unit tests for Program 29.0: Autonomous Research Loop.

Verifies the Research Ledger, Hypothesis Generator, Rollback Engine,
Experiment Manager, and Research Scheduler cycle.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.core.learning import (
    ResearchLedger,
    ExperimentRecord,
    HypothesisGenerator,
    RollbackEngine,
    ExperimentManager,
    ResearchScheduler,
)


class MockConfig:
    """Mock configuration object for testing parameter updates and rollbacks."""

    def __init__(self) -> None:
        self.max_cost = 1.0
        self.max_calls = 100
        self.max_duration = 300.0
        self.allow_network = False
        self.tool_file_read_retries = 1

    def to_dict(self) -> dict:
        return {
            "max_cost": self.max_cost,
            "max_calls": self.max_calls,
            "max_duration": self.max_duration,
            "allow_network": self.allow_network,
            "tool_file_read_retries": self.tool_file_read_retries,
        }


# ── Research Ledger Tests ─────────────────────────────────────────────────────

class TestResearchLedger:
    def test_register_and_retrieve_experiment(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ResearchLedger(storage_dir=tmp)
            
            # Register experiment
            record = ledger.register_experiment(
                hypothesis="Increasing max steps improves planning",
                parameters={"planner_max_steps": 20},
                baseline_metrics={"score": 0.85},
            )
            
            assert record.experiment_id.startswith("exp_")
            assert record.status == "pending"
            assert record.verdict == "undecided"
            
            # Retrieve experiment
            retrieved = ledger.get_experiment(record.experiment_id)
            assert retrieved is not None
            assert retrieved.hypothesis == record.hypothesis
            
            # Update metrics
            updated = ledger.update_experiment(
                record.experiment_id,
                experimental_metrics={"score": 0.95},
                status="completed",
                verdict="promoted",
            )
            
            assert updated.status == "completed"
            assert updated.verdict == "promoted"
            assert updated.experimental_metrics["score"] == 0.95

            # List check
            experiments = ledger.list_experiments()
            assert len(experiments) == 1
            assert experiments[0].experiment_id == record.experiment_id


# ── Hypothesis Generator Tests ────────────────────────────────────────────────

class TestHypothesisGenerator:
    def test_budget_exceeded_hypothesis(self):
        analytics = {
            "failures": {"BudgetExceededError": 5},
            "tools": {},
        }
        proposals = HypothesisGenerator.propose_hypotheses(analytics)
        assert len(proposals) >= 1
        assert "max_cost" in proposals[0]["parameters"]
        assert "cost budget bounds" in proposals[0]["hypothesis"]

    def test_policy_violation_hypothesis(self):
        analytics = {
            "failures": {"PolicyViolationError": 3},
            "tools": {},
        }
        proposals = HypothesisGenerator.propose_hypotheses(analytics)
        assert len(proposals) >= 1
        assert proposals[0]["parameters"]["allow_network"] is True
        assert "directory path restrictions" in proposals[0]["hypothesis"]

    def test_high_error_rate_tool_hypothesis(self):
        analytics = {
            "failures": {},
            "tools": {
                "file_read": {"calls": 10, "error_rate": 0.4},
            },
        }
        proposals = HypothesisGenerator.propose_hypotheses(analytics)
        assert len(proposals) >= 1
        assert "tool_file_read_retries" in proposals[0]["parameters"]
        assert "retry margins" in proposals[0]["hypothesis"]


# ── Rollback Engine Tests ──────────────────────────────────────────────────────

class TestRollbackEngine:
    def test_backup_and_restore_object(self):
        cfg = MockConfig()
        re = RollbackEngine()

        state_id = re.backup_state(cfg)
        assert state_id.startswith("state_")

        # Mutate config attributes
        cfg.max_cost = 5.0
        cfg.allow_network = True

        # Restore
        re.restore_state(cfg, state_id)
        assert cfg.max_cost == 1.0
        assert cfg.allow_network is False

    def test_backup_and_restore_dict(self):
        cfg = {"lr": 1e-4, "steps": 50}
        re = RollbackEngine()

        state_id = re.backup_state(cfg)
        cfg["lr"] = 5e-5
        cfg["steps"] = 100

        re.restore_state(cfg, state_id)
        assert cfg["lr"] == 1e-4
        assert cfg["steps"] == 50


# ── Experiment Manager Tests ──────────────────────────────────────────────────

class TestExperimentManager:
    def test_successful_experiment_promotes(self):
        cfg = MockConfig()
        manager = ExperimentManager()

        # Score is lower is better (e.g. error rate)
        # Baseline = 0.5, experimental = 0.2 -> improvement!
        eval_fn = lambda: 0.2

        result = manager.run_experiment(
            config_object=cfg,
            parameters={"max_cost": 2.5},
            evaluation_fn=eval_fn,
            revert_on_failure=True,
            baseline_score=0.5,
        )

        assert result["success"] is True
        assert result["verdict"] == "promoted"
        assert cfg.max_cost == 2.5  # retained change

    def test_failed_experiment_rolls_back(self):
        cfg = MockConfig()
        manager = ExperimentManager()

        # Baseline = 0.5, experimental = 0.8 -> regression!
        eval_fn = lambda: 0.8

        result = manager.run_experiment(
            config_object=cfg,
            parameters={"max_cost": 2.5},
            evaluation_fn=eval_fn,
            revert_on_failure=True,
            baseline_score=0.5,
        )

        assert result["success"] is True
        assert result["verdict"] == "rejected"
        assert cfg.max_cost == 1.0  # restored baseline!


# ── Research Scheduler Tests ──────────────────────────────────────────────────

class TestResearchScheduler:
    def test_scheduler_loop_roll_back_on_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ResearchLedger(storage_dir=tmp)
            scheduler = ResearchScheduler(ledger=ledger)

            cfg = MockConfig()
            analytics = {
                "failures": {"BudgetExceededError": 2},
                "tools": {},
            }

            # Regression score (baseline = 0.1, experimental = 0.4)
            eval_fn = lambda: 0.4

            exp_id = scheduler.run_cycle(
                config_object=cfg,
                analytics=analytics,
                evaluation_fn=eval_fn,
                baseline_score=0.1,
            )

            assert exp_id is not None
            record = ledger.get_experiment(exp_id)
            assert record.status == "rolled_back"
            assert record.verdict == "rejected"
            
            # Config remains unchanged
            assert cfg.max_cost == 1.0
