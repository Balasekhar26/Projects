from backend.core.theory_of_mind.belief_tracker import BeliefTracker
from backend.core.theory_of_mind.knowledge_asymmetry import KnowledgeAsymmetry
from backend.core.theory_of_mind.perspective_engine import PerspectiveEngine

class TheoryOfMindEngine:
    def __init__(self):
        self.beliefs = BeliefTracker()
        self.asymmetry = KnowledgeAsymmetry()
        self.perspective = PerspectiveEngine()

    def update_user_belief(self, topic: str, belief: str, confidence: float) -> None:
        """Records what the user believes about a topic."""
        self.beliefs.update_belief(topic, belief, confidence)

    def detect_knowledge_gaps(self, system_facts: set[str]) -> dict:
        """Compares system knowledge against user belief topics."""
        user_topics = set(self.beliefs.get_all_beliefs().keys())
        return self.asymmetry.detect_gaps(system_facts, user_topics)

    def get_adapted_style(self, interaction_count: int, technical_terms: int) -> dict:
        """Returns communication style adapted to inferred user expertise."""
        level = self.perspective.infer_expertise(interaction_count, technical_terms)
        return {
            "expertise_level": level,
            **self.perspective.get_communication_style(level)
        }
