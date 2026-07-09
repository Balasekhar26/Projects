"""Unit tests for Program 40.0: Policy Distillation.

Verifies conversion of policy database traces to SFT pairs, extraction of
lookup compression rules, and score-based filter rules.
"""
from __future__ import annotations

import tempfile
import pytest

from backend.core.planning import (
    StrategyMemory,
    StrategyRetriever,
    PolicyDistillationEngine,
)


@pytest.fixture
def temp_memory():
    with tempfile.TemporaryDirectory() as tmp:
        yield StrategyMemory(storage_dir=tmp)


# ── Policy Distillation Engine Tests ──────────────────────────────────────────

class TestPolicyDistillation:
    def test_distill_policies_to_sft_format(self, temp_memory):
        retriever = StrategyRetriever(temp_memory)
        
        # Save a sample policy
        steps = [
            {"name": "op_first", "operator_id": "op_1"},
            {"name": "op_second", "operator_id": "op_2"},
        ]
        retriever.store_policy(
            goal_name="compile_report",
            constraints=["has_file", "auth_valid"],
            steps=steps,
            score=0.90,
        )

        dataset = PolicyDistillationEngine.distill_policies_to_sft_format(temp_memory)
        assert len(dataset) == 1
        
        item = dataset[0]
        assert "Goal: compile_report" in item["prompt"]
        assert "Constraints: [has_file, auth_valid]" in item["prompt"]
        assert "Plan steps: [op_first, op_second]" in item["completion"]

    def test_generate_planning_compression_rules(self, temp_memory):
        retriever = StrategyRetriever(temp_memory)
        
        # High quality policy -> should compile as a compression rule
        steps_good = [{"name": "op_clean", "operator_id": "op_1"}]
        retriever.store_policy(
            goal_name="clean_disk",
            constraints=["disk_full"],
            steps=steps_good,
            score=0.95,
        )

        # Low quality policy -> should be ignored
        steps_bad = [{"name": "op_risky", "operator_id": "op_2"}]
        retriever.store_policy(
            goal_name="delete_system",
            constraints=["root_access"],
            steps=steps_bad,
            score=0.50,
        )

        rules = PolicyDistillationEngine.generate_planning_compression_rules(temp_memory)
        
        # 'clean_disk' is high score -> registered
        assert "clean_disk" in rules
        assert rules["clean_disk"] == ["op_clean"]
        
        # 'delete_system' is low score -> skipped
        assert "delete_system" not in rules
