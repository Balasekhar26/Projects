from typing import List, Dict, Any

from kattappa_runtime.memory.working_memory import WorkingMemory
from kattappa_runtime.memory.episodic_memory import EpisodicMemory
from kattappa_runtime.memory.semantic_memory import SemanticMemory
from kattappa_runtime.memory.ranker import MemoryRanker

class MemoryRetriever:
    def __init__(self, working: WorkingMemory, episodic: EpisodicMemory, semantic: SemanticMemory):
        self.working = working
        self.episodic = episodic
        self.semantic = semantic
        self.ranker = MemoryRanker()

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Queries episodic and semantic memory pools and ranks candidate context."""
        # 1. Gather all candidates from Episodic and Semantic memories
        candidates = []
        candidates.extend(self.episodic.get_all())
        candidates.extend(self.semantic.get_all())
        
        if not candidates:
            return []
            
        # 2. Rank candidates using triple-weighted similarity formula
        ranked = self.ranker.rank_memories(query, candidates)
        
        # 3. Slice top_k
        return ranked[:top_k]

    def get_context_string(self, query: str, top_k: int = 3) -> str:
        """Helper returns clean markdown context string to inject into Prompts."""
        # Include working memory state variables
        wm_context = []
        for k, v in self.working.state.items():
            if v:
                wm_context.append(f"{k}: {v}")
        wm_str = "Working Memory State:\n  - " + "\n  - ".join(wm_context) if wm_context else "No active working memory state."

        # Retrieve long term memories
        results = self.retrieve(query, top_k=top_k)
        if not results:
            return f"{wm_str}\n\nNo relevant historical memories recalled."
            
        mem_lines = []
        for item in results:
            mem_lines.append(f"  - {item['text']} (relevance score: {item['score']})")
            
        history_str = "Recalled Historical Memories:\n" + "\n".join(mem_lines)
        return f"{wm_str}\n\n{history_str}"
