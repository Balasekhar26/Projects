import os
from typing import Dict, Any

from kattappa_runtime.memory.working_memory import WorkingMemory
from kattappa_runtime.memory.episodic_memory import EpisodicMemory
from kattappa_runtime.memory.semantic_memory import SemanticMemory
from kattappa_runtime.memory.retriever import MemoryRetriever
from kattappa_runtime.memory.writer import MemoryWriter

class MemoryProvider:
    def retrieve(self, query: str) -> str:
        raise NotImplementedError
    def store(self, fact_dict: Dict[str, Any]):
        raise NotImplementedError
    def update(self, key: str, value: Any):
        raise NotImplementedError
    def forget(self, key: str) -> bool:
        raise NotImplementedError

class DummyMemoryProvider(MemoryProvider):
    def __init__(self, cache_file=None):
        base_dir = os.path.dirname(__file__)
        self.working = WorkingMemory()
        
        # Load episodic & semantic databases
        ep_file = os.path.abspath(os.path.join(base_dir, "episodic.jsonl"))
        sem_file = os.path.abspath(os.path.join(base_dir, "semantic.jsonl"))
        
        self.episodic = EpisodicMemory(filepath=ep_file)
        self.semantic = SemanticMemory(filepath=sem_file)
        
        # Initialize retriever and writer sub-systems
        self.retriever = MemoryRetriever(self.working, self.episodic, self.semantic)
        self.writer = MemoryWriter(self.working, self.episodic, self.semantic)
        
        # For backward compatibility with tests accessing .memory directly
        self.memory = {}
        self.sync_compat_memory()

    def sync_compat_memory(self):
        """Syncs semantic facts back to self.memory dictionary for compatibility with legacy tests."""
        self.memory = {}
        for f in self.semantic.get_all():
            self.memory[f["subject"]] = f["fact"]

    def retrieve(self, query: str) -> str:
        """Retrieves matching memory facts based on query keywords and appends multi-tier context."""
        q_words = set(query.lower().split())
        matched = []
        for key, val in self.memory.items():
            k_words = set(key.lower().replace("_", " ").split())
            if q_words.intersection(k_words) or any(w in key.lower() for w in q_words):
                matched.append(f"{key}: {val}")
        legacy_str = "\n".join(matched) if matched else "No relevant memories found."
        
        multi_tier_ctx = self.retriever.get_context_string(query, top_k=3)
        return f"{legacy_str}\n\n{multi_tier_ctx}"

    def store(self, fact_dict: Dict[str, Any]):
        """Stores dictionary items into semantic memory facts."""
        for k, v in fact_dict.items():
            self.writer.store_fact(subject=k, relation="detail", fact=str(v))
            self.writer.store_episode(event=f"Stored memory fact detail for '{k}': '{v}'", importance=0.6)
        self.sync_compat_memory()

    def update(self, key: str, value: Any):
        """Updates or overrides a key detail fact."""
        self.writer.store_fact(subject=key, relation="detail", fact=str(value))
        self.writer.store_episode(event=f"Updated fact for '{key}' to '{value}'", importance=0.7)
        self.sync_compat_memory()

    def forget(self, key: str) -> bool:
        """Purges a fact from semantic memory."""
        res = self.writer.delete_fact(subject=key, relation="detail")
        if res:
            self.writer.store_episode(event=f"Forgets fact for key '{key}'", importance=0.8)
        self.sync_compat_memory()
        return res
