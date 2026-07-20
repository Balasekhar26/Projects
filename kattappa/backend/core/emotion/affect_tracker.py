class AffectTracker:
    def __init__(self):
        self.current_mood = 0.0

    def update_affect(self, valence: float) -> float:
        """Consolidates rolling user sentiment over multiple interaction turns."""
        # Rolling average: 70% history, 30% new sentiment input
        self.current_mood = (self.current_mood * 0.70) + (valence * 0.30)
        return self.current_mood
