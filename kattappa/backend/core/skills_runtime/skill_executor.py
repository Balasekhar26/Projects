from backend.core.skills_runtime.skill_registry import Skill, SkillRegistry
from backend.core.action.action_executor import ActionExecutor

class SkillExecutor:
    def __init__(self, registry: SkillRegistry):
        self.registry = registry
        self.action_executor = ActionExecutor()

    def execute_skill(self, skill_name: str, system_prereqs: list[str]) -> str:
        """Executes skill steps sequentially, validating prerequisites and managing rollbacks."""
        skill = self.registry.get_skill(skill_name)
        if not skill:
            return "SKILL_NOT_FOUND"
            
        # 1. Verify prerequisites
        if not self.registry.validate_prerequisites(skill_name, system_prereqs):
            return "PREREQUISITE_FAILED"
            
        # 2. Iterate and execute action steps
        for step in skill.steps:
            cmd = step.get("cmd", "")
            x = step.get("x", 0)
            y = step.get("y", 0)
            pre = step.get("pre_snap")
            post = step.get("post_snap")
            
            result = self.action_executor.execute_action(
                command=cmd,
                x=x,
                y=y,
                pre_snapshot=pre,
                post_snapshot=post
            )
            
            if result != "SUCCESS":
                return f"STEP_FAILED_{result}"
                
        return "SUCCESS"
