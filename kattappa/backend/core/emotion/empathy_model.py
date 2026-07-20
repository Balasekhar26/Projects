class EmpathyModel:
    @classmethod
    def get_style_recommendations(cls, mood_valence: float) -> dict:
        """Adapts response parameters recommendations based on user mood level."""
        if mood_valence < -0.30:
            return {
                "tone": "direct_and_helpful",
                "apology_needed": True,
                "verbosity": "low"
            }
        elif mood_valence > 0.30:
            return {
                "tone": "warm_and_acknowledging",
                "apology_needed": False,
                "verbosity": "medium"
            }
            
        return {
            "tone": "neutral_professional",
            "apology_needed": False,
            "verbosity": "medium"
        }
