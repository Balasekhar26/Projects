from __future__ import annotations
from backend.core.world_state.world_state_manager import WORLD_STATE_MANAGER
from backend.core.memory.memory_manager import MemoryManager

class ContextBuilder:
    @classmethod
    def build_context(cls, goal: str) -> dict:
        """Assembles aggregated world state snapshots and knowledge graph facts matching goal queries."""
        world_snapshot = WORLD_STATE_MANAGER.get_snapshot()
        memory_context = MemoryManager.get_planner_context(goal)
        
        # Query local RAG engine for relevant manual content
        from backend.core.rag.rag_engine import RAGEngine
        rag_context = RAGEngine.query(goal)
        
        # Query local GraphRAG engine for relevant entity relations
        from backend.core.graphrag.graph_engine import GraphEngine
        graph_context = GraphEngine.query(goal)
        
        return {
            "world_state": world_snapshot,
            "memory": memory_context,
            "rag_context": rag_context,
            "graph_context": graph_context
        }
