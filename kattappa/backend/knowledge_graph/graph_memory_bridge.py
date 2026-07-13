from __future__ import annotations
from typing import Any, Dict
from backend.knowledge_graph.triple import Triple
from backend.knowledge_graph.graph_store import GraphStore
from backend.knowledge_graph.extractor import TripleExtractor

class GraphMemoryBridge:
    """Interceptors syncing memory event updates into the persistent GraphStore."""

    def __init__(self, store: GraphStore = None) -> None:
        self.store = store or GraphStore()

    def sync_conversation(self, query: str, entities: Dict[str, Any]) -> None:
        """Parses queries and entities, updating graph mappings."""
        triples = TripleExtractor.extract_from_query(query, entities)
        for t in triples:
            self.store.add_triple(t)
