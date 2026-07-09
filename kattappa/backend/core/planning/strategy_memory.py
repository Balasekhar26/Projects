"""Lifelong Strategy & Policy Memory (Program 39.0).

Stores successful planning policies, indexes trace structures, resolves semantically
similar strategies, groups macro actions, and distills parameters adjustments.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import runtime_data_root
from backend.core.planning.task import Plan, Operator


def _strategy_dir() -> Path:
    p = runtime_data_root() / "backend" / "data" / "planning"
    p.mkdir(parents=True, exist_ok=True)
    return p


class StrategyMemory:
    """Manages strategy database reads, writes, and record index updates."""

    _lock = threading.RLock()

    def __init__(self, storage_dir: Optional[str | Path] = None) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else _strategy_dir()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_file = self.storage_dir / "strategy_memory.json"

    def load_db(self) -> Dict[str, Any]:
        with self._lock:
            if not self.db_file.exists():
                return {"policies": [], "macros": {}}
            try:
                with self.db_file.open(encoding="utf-8") as fh:
                    return json.load(fh)
            except json.JSONDecodeError:
                return {"policies": [], "macros": {}}

    def save_db(self, db: Dict[str, Any]) -> None:
        with self._lock:
            with self.db_file.open("w", encoding="utf-8") as fh:
                json.dump(db, fh, indent=2)


class PolicyConsolidationEngine:
    """Consolidates verified plan traces into reusable policy records."""

    @classmethod
    def consolidate_trace(
        cls,
        plan: Plan,
        evaluation: Dict[str, Any],
        memory: StrategyMemory,
    ) -> Optional[str]:
        """Saves a plan trace as a reusable policy if success scores pass thresholds."""
        is_success = evaluation.get("is_success", False)
        score = evaluation.get("score", 0.0)

        # Only consolidate high-quality successful traces (score >= 0.8)
        if not is_success or score < 0.80:
            return None

        retriever = StrategyRetriever(memory)
        # Convert steps back to dictionary definitions
        steps_data = []
        for op in plan.steps:
            steps_data.append({
                "operator_id": op.operator_id,
                "name": op.name,
                "preconditions": op.preconditions,
                "effects": op.effects,
                "estimated_cost": op.estimated_cost,
                "estimated_time": op.estimated_time,
            })

        policy_id = retriever.store_policy(
            goal_name=plan.goal_id,  # Index by goal ID key
            constraints=list(plan.steps[0].preconditions.keys()) if plan.steps else [],
            steps=steps_data,
            score=score,
        )
        return policy_id


class StrategyRetriever:
    """Saves and queries consolidated execution policies."""

    def __init__(self, memory: StrategyMemory) -> None:
        self.memory = memory

    def store_policy(
        self,
        goal_name: str,
        constraints: List[str],
        steps: List[Dict[str, Any]],
        score: float,
    ) -> str:
        """Stores a new policy in the database."""
        db = self.memory.load_db()
        policy_id = f"policy_{uuid.uuid4().hex[:8]}"
        
        db["policies"].append({
            "policy_id": policy_id,
            "goal_name": goal_name,
            "constraints": list(constraints),
            "steps": steps,
            "utility_score": score,
            "timestamp": time.time(),
        })
        self.memory.save_db(db)
        return policy_id

    def retrieve_strategy(
        self,
        goal_name: str,
        constraints: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Finds matching strategy based on goal name and constraint overlaps."""
        db = self.memory.load_db()
        best_match = None
        best_score = -1.0

        target_set = set(constraints)

        for policy in db["policies"]:
            if policy["goal_name"] != goal_name:
                continue

            policy_set = set(policy["constraints"])
            # Match if target constraints are a subset or identical to policy constraints
            if target_set.issubset(policy_set) or policy_set.issubset(target_set):
                if policy["utility_score"] > best_score:
                    best_score = policy["utility_score"]
                    best_match = policy

        return best_match


class MacroActionLibrary:
    """Caches sequences of operators into unified macro actions."""

    def __init__(self, memory: StrategyMemory) -> None:
        self.memory = memory

    def register_macro(self, macro_name: str, steps: List[Dict[str, Any]]) -> None:
        """Saves a group sequence as a single macro action."""
        db = self.memory.load_db()
        db["macros"][macro_name] = steps
        self.memory.save_db(db)

    def get_macro(self, macro_name: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieves macro actions steps list."""
        db = self.memory.load_db()
        return db["macros"].get(macro_name)


class ExperienceDistillationEngine:
    """Distills execution trace histories into policy updates."""

    @classmethod
    def distill_weights_adjustment(cls, past_runs: List[Dict[str, Any]]) -> Dict[str, float]:
        """Suggests context scenario weights changes based on resource trends."""
        suggested = {"w_success": 1.0, "w_cost": 0.1, "w_duration": 0.05, "w_risk": 0.2}
        if not past_runs:
            return suggested

        total_runs = len(past_runs)
        failed_count = sum(1 for r in past_runs if not r.get("is_success", True))
        avg_cost_variance = sum(r.get("cost_variance_ratio", 1.0) for r in past_runs) / total_runs
        avg_duration_variance = sum(r.get("duration_variance_ratio", 1.0) for r in past_runs) / total_runs

        # If failures are high (e.g. > 30%), increase risk avoidance factor
        if (failed_count / total_runs) > 0.30:
            suggested["w_risk"] = 0.5
            suggested["w_success"] = 0.8

        # If actual cost is regularly exceeding expected budget, lift cost weight penalty
        if avg_cost_variance > 1.20:
            suggested["w_cost"] = 0.3

        # If execution regularly takes longer, lift duration weight penalty
        if avg_duration_variance > 1.20:
            suggested["w_duration"] = 0.15

        return suggested
