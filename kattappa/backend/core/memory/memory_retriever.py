from __future__ import annotations
from backend.core.memory.memory_store import MemoryStore
from backend.core.memory.memory_scorer import MemoryScorer

class MemoryRetriever:
    @classmethod
    def retrieve_memories(cls, query: str, limit: int = 5) -> list[dict]:
        """Queries memories, scores them, increments access counts, and returns top relevance matches."""
        all_mems = MemoryStore.get_all_memories()
        query_words = set(query.lower().split())
        
        matches = []
        for mem in all_mems:
            content_lower = mem["content"].lower()
            if not query_words or any(word in content_lower for word in query_words):
                score = MemoryScorer.calculate_score(mem)
                mem_dict = dict(mem)
                mem_dict["relevance_score"] = score
                matches.append(mem_dict)
                MemoryStore.increment_memory_access(mem["id"])
                
        matches.sort(key=lambda x: x["relevance_score"], reverse=True)
        return matches[:limit]

    @classmethod
    def retrieve_graph_context(cls, query: str) -> list[str]:
        """Extracts entity triples matching context keywords to feed to the planner."""
        entities = MemoryStore.get_all_entities()
        relationships = MemoryStore.get_all_relationships()
        
        query_words = set(query.lower().split())
        
        ent_by_id = {e["id"]: e for e in entities}
        matched_ent_ids = set()
        
        for ent in entities:
            name_lower = ent["name"].lower()
            if any(word in name_lower for word in query_words):
                matched_ent_ids.add(ent["id"])
                
        triples = []
        for rel in relationships:
            if rel["source_id"] in matched_ent_ids or rel["target_id"] in matched_ent_ids:
                src_name = ent_by_id.get(rel["source_id"], {}).get("name", rel["source_id"])
                tgt_name = ent_by_id.get(rel["target_id"], {}).get("name", rel["target_id"])
                triples.append(f"{src_name} {rel['predicate']} {tgt_name}")
                
        return triples
