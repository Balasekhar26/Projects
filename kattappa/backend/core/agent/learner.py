from backend.core.skills_runtime.skill_registry import Skill
from backend.core.skills_runtime.skills_runtime_engine import SkillsRuntimeEngine

class Learner:
    def __init__(self, skills_engine: SkillsRuntimeEngine):
        self.skills_engine = skills_engine

    def learn_new_skill(self, skill_name: str, action_sequence: list[dict]) -> Skill:
        """Analyzes successful action coordinate command paths and logs a reusable Skill schema."""
        # Clean sequence by removing repeated/redundant clicks
        cleaned_steps = []
        last_step = None
        
        for step in action_sequence:
            # Skip step if it represents exact duplicate action of the last step
            if last_step and step.get("cmd") == last_step.get("cmd") and step.get("x") == last_step.get("x") and step.get("y") == last_step.get("y"):
                continue
            cleaned_steps.append(step)
            last_step = step
            
        skill = Skill(
            name=skill_name,
            prerequisites=[],
            steps=cleaned_steps,
            post_conditions=["execution_verified"],
            description=f"Autonomously learned skill: {skill_name}"
        )
        
        self.skills_engine.register_skill(skill)
        return skill
