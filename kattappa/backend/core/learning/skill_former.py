"""Skill Former (Program 21.0).

Distills successful execution trajectories into reusable procedural templates inside SkillLibrary.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from backend.core.learning.experience_store import ExperienceStore
from backend.core.learning.trajectory_builder import Trajectory
from backend.core.skill_library import SkillLibrary

logger = logging.getLogger(__name__)


class SkillFormer:
    """Extracts repeatable workflow recipes from high-performing historical plans."""

    @classmethod
    def distill_trajectory_to_skill(
        cls,
        trajectory: Trajectory,
        skill_name: str,
        description: str = "",
        tags: List[str] | None = None
    ) -> Dict[str, Any]:
        """Converts a specific successful trajectory into a persistent procedural skill template.

        Filters out failed or repair nodes from the execution sequence.
        """
        if not trajectory.success:
            raise ValueError(f"Cannot distill failed trajectory '{trajectory.goal_id}' into a skill template.")

        # Filter nodes to construct steps sequence (exclude error/failed tags)
        cleaned_steps = []
        for node in trajectory.nodes_executed:
            if not node.startswith("failed:") and node not in cleaned_steps:
                cleaned_steps.append(node)

        if not cleaned_steps:
            raise ValueError("No valid execution steps found in trajectory; distillation aborted.")

        # Default values if empty
        desc = description or f"Auto-distilled recipe from successful plan execution: {trajectory.plan_id}"
        resolved_tags = tags or ["distilled", trajectory.planner_version.lower()]

        logger.info(
            "SkillFormer: Distilling trajectory '%s' into procedural skill template '%s'",
            trajectory.goal_id, skill_name
        )

        # Write to SkillLibrary
        try:
            skill = SkillLibrary.add_skill(
                name=skill_name,
                description=desc,
                inputs=[],
                steps=cleaned_steps,
                outputs=[],
                tags=resolved_tags
            )
            return {
                "success": True,
                "skill": skill,
                "message": f"Successfully compiled and stored skill '{skill_name}' in library."
            }
        except ValueError as e:
            # Handle duplicate key conflicts
            logger.warning("SkillFormer: Skill registration warning — %s", e)
            return {
                "success": False,
                "skill": None,
                "message": str(e)
            }

    @classmethod
    def run_auto_promotion(cls, store: ExperienceStore, score_threshold: float = 90.0) -> List[Dict[str, Any]]:
        """Scans store for trajectories with success=True and score >= threshold to promote.

        Creates draft skills for any high-performing recipes not yet registered.
        """
        promoted = []
        successful_runs = [t for t in store.trajectories if t.success and t.combined_score >= score_threshold]

        for idx, t in enumerate(successful_runs):
            # Form clean name
            name = f"AutoSkill-{t.plan_id or 'plan'}-{idx + 1}"
            
            # Check if already registered
            if SkillLibrary.get(name):
                continue

            res = cls.distill_trajectory_to_skill(
                trajectory=t,
                skill_name=name,
                description=f"Auto-promoted successful trajectory from goal {t.goal_id} (Score: {t.combined_score:.1f})"
            )
            if res["success"]:
                promoted.append(res["skill"])

        logger.info("SkillFormer: Promoted %d trajectories to procedural skills.", len(promoted))
        return promoted
