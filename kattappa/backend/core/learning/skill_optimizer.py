"""Skill Optimizer & Evolution Engine (Program 23.0).

Automates procedural skill version updates, compares sequence variants,
and retires/demotes underperforming templates.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from backend.core.skill_library import SkillLibrary
from backend.core.learning.experience_store import ExperienceStore

logger = logging.getLogger(__name__)


class SkillOptimizer:
    """Manages skill lifecycles by auditing success parameters and updating step sequences."""

    DEMOTION_THRESHOLD = 0.60
    MIN_USES_FOR_EVALUATION = 5

    @classmethod
    def evaluate_and_evolve_skill(cls, skill_name: str, store: ExperienceStore) -> Dict[str, Any]:
        """Scans execution history to demote or retire fragile skills in the SkillLibrary."""
        skill = SkillLibrary.get(skill_name)
        if not skill:
            return {"success": False, "message": f"Skill '{skill_name}' not found."}

        # Filter trajectories relating to this skill name
        rel_trajectories = [
            t for t in store.trajectories
            if t.goal_id.lower() == skill_name.lower() or skill_name.lower() in t.goal_id.lower()
        ]

        total_runs = len(rel_trajectories)
        if total_runs < cls.MIN_USES_FOR_EVALUATION:
            return {
                "success": True,
                "message": f"Insufficient runs ({total_runs}/{cls.MIN_USES_FOR_EVALUATION}) for lifecycle evaluation.",
                "action": "skipped"
            }

        successes = sum(1 for t in rel_trajectories if t.success)
        success_rate = successes / total_runs

        # Update SkillLibrary usage counters
        # We record each result sequentially to refresh internal library statistics
        for t in rel_trajectories:
            try:
                SkillLibrary.record_result(skill_name, t.success)
            except Exception:
                pass

        # Demote to draft if success rate drops below threshold
        updated_skill = SkillLibrary.get(skill_name) or skill
        action = "none"
        if success_rate < cls.DEMOTION_THRESHOLD and updated_skill.get("trust") == "trusted":
            with SkillLibrary._lock:
                data = SkillLibrary._load()
                sk = data.get("skills", {}).get(SkillLibrary._key(skill_name))
                if sk:
                    sk["trust"] = "draft"  # Demote to draft
                    sk["description"] += f" [Demoted due to low success rate: {success_rate * 100:.1f}%]"
                    SkillLibrary._save(data)
                    action = "demoted"
                    logger.warning(
                        "SkillOptimizer: Demoted '%s' to draft due to low success rate: %.1f%%",
                        skill_name, success_rate * 100
                    )

        return {
            "success": True,
            "total_runs": total_runs,
            "success_rate": round(success_rate, 3),
            "action": action,
            "trust": SkillLibrary.get(skill_name).get("trust") if SkillLibrary.get(skill_name) else "draft"
        }

    @classmethod
    def compare_and_upgrade_steps(
        cls,
        skill_name: str,
        new_steps: List[str],
        new_performance_score: float
    ) -> Dict[str, Any]:
        """Compares current skill steps against a candidate variant, upgrading if superior."""
        skill = SkillLibrary.get(skill_name)
        if not skill:
            return {"success": False, "message": f"Skill '{skill_name}' not found."}

        # Calculate current baseline score using success rate
        # If success rate is not calculated yet, default to a base reference score (e.g. 75.0)
        curr_rate = skill.get("success_rate")
        baseline_score = curr_rate * 100.0 if curr_rate is not None else 75.0

        if new_performance_score > baseline_score:
            # Upgrade steps in persistent registry
            with SkillLibrary._lock:
                data = SkillLibrary._load()
                sk = data.get("skills", {}).get(SkillLibrary._key(skill_name))
                if sk:
                    old_steps = sk.get("steps", [])
                    sk["steps"] = new_steps
                    sk["description"] += f" [Upgraded steps on score improvement: {baseline_score:.1f} -> {new_performance_score:.1f}]"
                    SkillLibrary._save(data)
                    
                    logger.info(
                        "SkillOptimizer: Upgraded steps for '%s' (score improved from %.1f to %.1f)",
                        skill_name, baseline_score, new_performance_score
                    )
                    return {
                        "success": True,
                        "action": "upgraded",
                        "old_steps": old_steps,
                        "new_steps": new_steps
                    }

        return {
            "success": True,
            "action": "none",
            "message": f"Candidate variant score ({new_performance_score:.1f}) did not exceed baseline ({baseline_score:.1f})."
        }
