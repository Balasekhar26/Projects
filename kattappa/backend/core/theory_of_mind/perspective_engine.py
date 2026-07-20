class PerspectiveEngine:
    EXPERTISE_LEVELS = {
        "beginner": {"detail": "high", "jargon": False, "examples": True},
        "intermediate": {"detail": "medium", "jargon": True, "examples": True},
        "expert": {"detail": "low", "jargon": True, "examples": False}
    }

    @classmethod
    def infer_expertise(cls, interaction_count: int, technical_terms_used: int) -> str:
        """Infers user expertise level from interaction history signals."""
        if technical_terms_used >= 10 and interaction_count >= 20:
            return "expert"
        elif technical_terms_used >= 3 or interaction_count >= 5:
            return "intermediate"
        return "beginner"

    @classmethod
    def get_communication_style(cls, expertise_level: str) -> dict:
        """Returns recommended communication parameters for the given expertise level."""
        return cls.EXPERTISE_LEVELS.get(expertise_level, cls.EXPERTISE_LEVELS["beginner"])
