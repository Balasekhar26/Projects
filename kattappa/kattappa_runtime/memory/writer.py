from typing import Dict, Any, List

from kattappa_runtime.memory.working_memory import WorkingMemory
from kattappa_runtime.memory.episodic_memory import EpisodicMemory
from kattappa_runtime.memory.semantic_memory import SemanticMemory

class MemoryWriter:
    def __init__(self, working: WorkingMemory, episodic: EpisodicMemory, semantic: SemanticMemory):
        self.working = working
        self.episodic = episodic
        self.semantic = semantic

    def store_episode(self, event: str, importance: float = 0.5, confidence: float = 1.0):
        """Logs a chronological conversational action or state change."""
        return self.episodic.add_episode(event, importance, confidence)

    def store_fact(self, subject: str, relation: str, fact: str, confidence: float = 1.0):
        """Stores a generalized profile metadata fact."""
        return self.semantic.store_fact(subject, relation, fact, confidence)

    def delete_fact(self, subject: str, relation: str) -> bool:
        """Purges a fact entry."""
        return self.semantic.remove_fact(subject, relation)

    def update_working_state(self, updates: Dict[str, Any]):
        """Updates fast transient memory variables."""
        for k, v in updates.items():
            self.working.set(k, v)

    def compress_memory(self, items_to_compress: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Combines multiple chronological episodes into a single synthesized summary fact."""
        if not items_to_compress:
            return {}
            
        events = [item.get("event") for item in items_to_compress if "event" in item]
        if not events:
            return {}
            
        summary_text = f"Summarized log of multiple historical activities: {'; '.join(events[:5])}."
        
        # Save summary fact
        self.store_fact("User History", "consolidated_events", summary_text, confidence=0.9)
        return {"summary": summary_text}
