from backend.core.skills_runtime.skill_registry import Skill, SkillRegistry

class SkillComposer:
    @classmethod
    def compose_dag_skill(
        cls, 
        composite_name: str, 
        sub_skills_list: list[str], 
        registry: SkillRegistry
    ) -> Skill | None:
        """Combines multiple independent sub-skills into a single aggregated sequential Skill DAG."""
        combined_prereqs = set()
        combined_steps = []
        combined_postconditions = set()
        
        for name in sub_skills_list:
            sub = registry.get_skill(name)
            if not sub:
                return None
                
            combined_prereqs.update(sub.prerequisites)
            combined_steps.extend(sub.steps)
            combined_postconditions.update(sub.post_conditions)
            
        return Skill(
            name=composite_name,
            prerequisites=list(combined_prereqs),
            steps=combined_steps,
            post_conditions=list(combined_postconditions),
            description=f"Composite skill assembling: {', '.join(sub_skills_list)}"
        )
