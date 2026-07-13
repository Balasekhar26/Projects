from __future__ import annotations
from typing import Any, List
from backend.knowledge_graph.graph_store import GraphStore

class GraphQueryEngine:
    """Performs semantic queries and path traversals over persistent graph stores."""

    def __init__(self, store: GraphStore = None) -> None:
        self.store = store or GraphStore()

    def get_user_location(self) -> str:
        """Finds current active location nodes for user."""
        triples = self.store.get_triples(subject="user", predicate="LOCATED_IN")
        if triples:
            return triples[0].object
        return "Unknown"

    def get_user_preferences(self) -> List[str]:
        """Finds all active preference mappings."""
        triples = self.store.get_triples(subject="user", predicate="PREFERS")
        return [t.object for t in triples]

    def query_relationships(self, subject: str) -> List[dict]:
        """Returns structured map of all relationships for a node."""
        triples = self.store.get_triples(subject=subject)
        return [{"predicate": t.predicate, "object": t.object, "confidence": t.confidence} for t in triples]
