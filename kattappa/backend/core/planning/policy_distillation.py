"""Policy Distillation Engine (Program 40.0).

Converts successful planning traces into formatted supervised fine-tuning (SFT)
dataset structures, and distills direct routing rules to bypass state searches.
"""
from __future__ import annotations

from typing import Any, Dict, List

from backend.core.planning.strategy_memory import StrategyMemory


class PolicyDistillationEngine:
    """Formats trace datasets and compiles planner sequence lookup shortcuts."""

    @classmethod
    def distill_policies_to_sft_format(cls, memory: StrategyMemory) -> List[Dict[str, Any]]:
        """Converts database policies into standard SFT instruction-response pairs."""
        db = memory.load_db()
        dataset = []

        for policy in db.get("policies", []):
            goal = policy.get("goal_name", "")
            constraints = ", ".join(policy.get("constraints", []))
            
            # Map steps to serialized name list
            step_names = [step.get("name", "") for step in policy.get("steps", [])]
            steps_str = ", ".join(step_names)

            dataset.append({
                "prompt": f"Goal: {goal} | Constraints: [{constraints}]",
                "completion": f"Plan steps: [{steps_str}]",
            })

        return dataset

    @classmethod
    def generate_planning_compression_rules(cls, memory: StrategyMemory) -> Dict[str, List[str]]:
        """Extracts pre-optimized operator paths to bypass HTN search states."""
        db = memory.load_db()
        rules: Dict[str, List[str]] = {}

        # Group steps by goal_name, prioritizing high utility score records
        for policy in db.get("policies", []):
            goal = policy.get("goal_name")
            if not goal:
                continue

            score = policy.get("utility_score", 0.0)
            if score < 0.80:
                continue  # skip low-quality paths

            step_names = [step.get("name", "") for step in policy.get("steps", [])]
            
            # Only save the best scoring path for each goal
            if goal not in rules:
                rules[goal] = step_names

        return rules
