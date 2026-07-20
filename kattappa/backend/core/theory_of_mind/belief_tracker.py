class BeliefTracker:
    def __init__(self):
        self._beliefs: dict[str, dict] = {}

    def update_belief(self, topic: str, belief: str, confidence: float) -> None:
        """Records or updates what the user believes about a topic."""
        existing = self._beliefs.get(topic)
        if existing:
            # Bayesian-style consolidation: weight history 0.7, new evidence 0.3
            old_conf = existing["confidence"]
            new_conf = (old_conf * 0.7) + (confidence * 0.3)
            self._beliefs[topic] = {"belief": belief, "confidence": new_conf}
        else:
            self._beliefs[topic] = {"belief": belief, "confidence": confidence}

    def get_belief(self, topic: str) -> dict | None:
        """Returns the user's current belief about a topic, or None."""
        return self._beliefs.get(topic)

    def get_all_beliefs(self) -> dict[str, dict]:
        """Returns the complete belief model."""
        return dict(self._beliefs)
