from backend.core.semantic_memory_engine.semantic_store import SemanticStore
from backend.core.semantic_memory_engine.concept_ontology import ConceptOntology
from backend.core.semantic_memory_engine.knowledge_abstraction import KnowledgeAbstraction

class SemanticMemoryEngine:
    def __init__(self):
        self.store = SemanticStore()
        self.ontology = ConceptOntology()
        self.abstraction = KnowledgeAbstraction()

    def record_fact(self, concept_id: str, predicate: str, target_id: str, confidence: float) -> None:
        """Saves a semantic fact. If it already exists, consolidates confidence values dynamically."""
        existing = self.store.get_fact(concept_id, predicate, target_id)
        if existing:
            new_conf = self.abstraction.consolidate_confidence(existing["confidence"], confidence)
            self.store.save_fact(concept_id, predicate, target_id, new_conf)
        else:
            self.store.save_fact(concept_id, predicate, target_id, confidence)

    def get_relationship_chain(self, concept_id: str) -> list[str]:
        """Resolves taxonomic IS_A hierarchy chains."""
        return self.ontology.get_ancestors(concept_id)

    def get_fact_confidence(self, concept_id: str, predicate: str, target_id: str) -> float:
        """Retrieves confidence score for a registered fact statement."""
        fact = self.store.get_fact(concept_id, predicate, target_id)
        return fact["confidence"] if fact else 0.0
