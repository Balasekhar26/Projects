from backend.core.skills_runtime.skill_registry import Skill, SkillRegistry
from backend.core.skills_runtime.skill_executor import SkillExecutor
from backend.core.skills_runtime.skill_composer import SkillComposer

class SkillsRuntimeEngine:
    def __init__(self):
        self.registry = SkillRegistry()
        self.executor = SkillExecutor(self.registry)
        self.composer = SkillComposer()

    def register_skill(self, skill: Skill) -> None:
        """Registers a skill configuration inside the runtime engines registry."""
        self.registry.register(skill)

    def compose_skill(self, composite_name: str, sub_skills: list[str]) -> bool:
        """Assembles a composite skill configuration out of previously registered sub-skills."""
        composite = self.composer.compose_dag_skill(composite_name, sub_skills, self.registry)
        if composite:
            self.registry.register(composite)
            return True
        return False

    def execute(self, skill_name: str, system_prereqs: list[str]) -> str:
        """Runs the registered skill steps validation and dispatch actions loops."""
        return self.executor.execute_skill(skill_name, system_prereqs)
