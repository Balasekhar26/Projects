from __future__ import annotations
from backend.core.skills.skill_registry import SkillRegistry

class SkillSelector:
    @classmethod
    def select_skill(cls, goal: str, context: dict | None = None) -> dict | None:
        """Finds the highest-confidence matched skill satisfying high-confidence limits."""
        matches = SkillRegistry.get_matching_skills(goal, context)
        if not matches:
            return None
            
        valid_matches = [m for m in matches if m["confidence_score"] >= 0.85]
        if not valid_matches:
            return None
            
        valid_matches.sort(key=lambda x: x["confidence_score"], reverse=True)
        return valid_matches[0]
