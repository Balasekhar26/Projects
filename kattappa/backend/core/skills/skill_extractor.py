from __future__ import annotations
import uuid
from backend.core.skills.skill_registry import SkillRegistry

class SkillExtractor:
    @classmethod
    def extract_skill_from_reflection(cls, reflection: dict, action_sequence: list[dict] | None = None) -> dict | None:
        """Converts successful reflections into reusable learned skills registered in the database."""
        # Only extract skills for successful tasks
        if reflection.get("status") != "COMPLETED":
            return None
            
        goal = reflection.get("goal_text") or reflection.get("goal") or ""
        if not goal:
            return None
            
        words = goal.lower().split()
        keywords = [w.strip(".,!?\"'") for w in words if len(w) > 3]
        
        clean_goal = "".join(c for c in goal if c.isalnum() or c.isspace()).replace(" ", "_").lower()
        skill_id = f"skill_{clean_goal[:30]}_{str(uuid.uuid4())[:4]}"
        
        triggers = {
            "keywords": keywords,
            "goal": goal
        }
        
        prereqs = {
            "os": "any"
        }
        
        actions = action_sequence or [
            {
                "step_id": "step1",
                "description": f"Execute cached step for: {goal}",
                "agent": "coder",
                "action": "RUN_SHELL",
                "params": {"command": f"echo 'Running {goal}'"},
                "dependencies": []
            }
        ]
        
        confidence = reflection.get("confidence_rating") or reflection.get("confidence_score") or 1.0
        
        SkillRegistry.register_skill(
            skill_id=skill_id,
            trigger_conditions=triggers,
            prerequisites=prereqs,
            action_sequence=actions,
            confidence_score=confidence,
            success_count=1
        )
        
        return {
            "skill_id": skill_id,
            "trigger_conditions": triggers,
            "action_sequence": actions
        }
