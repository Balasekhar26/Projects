from __future__ import annotations
from typing import Any, Dict
from backend.core.memory import build_memory_context
from backend.core.knowledge_graph import KnowledgeGraph

class ContextBuilder:
    """Consolidates inputs from short-term memory, episodic memory, and the Knowledge Graph."""

    @staticmethod
    def build(user_input: str) -> Dict[str, Any]:
        # 1. Retrieve episodic/semantic memory context via memory engine
        try:
            memory_ctx = build_memory_context(user_input)
        except Exception:
            memory_ctx = "No relevant memory context retrieved."

        # 2. Retrieve related entities from Knowledge Graph
        kg_entities = []
        try:
            kg = KnowledgeGraph.get_instance()
            # Search for keyword matches in entity store
            keywords = [w.strip().upper() for w in user_input.split() if len(w) > 3]
            for kw in keywords:
                node = kg.get_node(kw)
                if node:
                    kg_entities.append(f"{node['name']} ({node['entity_type']}) - confidence: {node.get('confidence', 1.0)}")
        except Exception:
            pass

        kg_ctx = "\n".join(kg_entities) if kg_entities else "No matching knowledge graph entities found."

        return {
            "memory_context": memory_ctx,
            "kg_context": kg_ctx,
            "user_input": user_input
        }
