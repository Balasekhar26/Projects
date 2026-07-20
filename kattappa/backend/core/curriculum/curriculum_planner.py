class CurriculumPlanner:
    @classmethod
    def generate_curriculum(cls, weak_skills: list[str]) -> list[dict]:
        """Formulates targeted learning exercises for identified weak skills."""
        curriculum = []
        for skill_id in weak_skills:
            curriculum.append({
                "skill_id": skill_id,
                "exercise_name": f"rehearse_{skill_id}",
                "difficulty": "medium",
                "iterations": 3
            })
        return curriculum
