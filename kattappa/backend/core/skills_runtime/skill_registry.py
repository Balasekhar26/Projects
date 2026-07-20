from dataclasses import dataclass, field

@dataclass
class Skill:
    name: str
    prerequisites: list[str] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)  # list of action command dicts
    post_conditions: list[str] = field(default_factory=list)
    description: str = ""

class SkillRegistry:
    def __init__(self):
        self.skills = {}

    def register(self, skill: Skill) -> None:
        """Registers a new skill structure in the skills runtime memory store."""
        self.skills[skill.name] = skill

    def get_skill(self, name: str) -> Skill | None:
        """Retrieves a registered skill configuration by its name."""
        return self.skills.get(name)

    def validate_prerequisites(self, skill_name: str, system_prereqs: list[str]) -> bool:
        """Verifies if the system configuration satisfies the skill pre-requisites."""
        skill = self.get_skill(skill_name)
        if not skill:
            return False
            
        for req in skill.prerequisites:
            if req not in system_prereqs:
                return False
        return True
