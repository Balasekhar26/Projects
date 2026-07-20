class KnowledgeAbstraction:
    @classmethod
    def consolidate_confidence(cls, current_confidence: float, observation_confidence: float) -> float:
        """Consolidates confidence indices iteratively using moving averages updates."""
        return float((current_confidence * 0.70) + (observation_confidence * 0.30))
