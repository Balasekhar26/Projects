import re
from backend.core.memory.memory_store import MemoryStore

class GraphRetriever:
    @classmethod
    def traverse_relationships(cls, start_entity_id: str, max_depth: int = 3) -> list[dict]:
        """Performs a Breadth-First Search (BFS) path traversal to resolve multi-hop relationships up to max_depth."""
        visited = set()
        queue = [(start_entity_id, 0)]
        results = []
        
        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth >= max_depth:
                continue
                
            visited.add(current)
            rels = MemoryStore.get_entity_relationships(current)
            
            for rel in rels:
                if rel not in results:
                    results.append(rel)
                    
                # Identify neighboring entity and add to traversal queue
                neighbor = rel["target_id"] if rel["source_id"] == current else rel["source_id"]
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))
                    
        return results

    @classmethod
    def query_graph(cls, query_text: str, max_depth: int = 3) -> str:
        """Finds matching entity seeds in the query and returns their time-decayed traversals."""
        # Simple extraction of candidate word tokens to match entity IDs
        query_words = re.findall(r"\w+", query_text.lower())
        
        # Load all entities to check name matches
        conn = MemoryStore._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM entities")
        all_entities = [dict(row) for row in cursor.fetchall()]
        
        matching_entities = []
        for ent in all_entities:
            ent_name_clean = ent["name"].lower()
            # If entity name exists as substring/word in query
            if ent_name_clean in query_text.lower() or ent["id"] in query_words:
                matching_entities.append(ent)
                
        if not matching_entities:
            return ""
            
        all_traversals = []
        visited_rel_ids = set()
        
        for ent in matching_entities:
            rels = cls.traverse_relationships(ent["id"], max_depth=max_depth)
            for r in rels:
                if r["id"] not in visited_rel_ids:
                    visited_rel_ids.add(r["id"])
                    all_traversals.append(r)
                    
        if not all_traversals:
            return ""
            
        # Format graph context blocks
        blocks = []
        for rel in all_traversals:
            # Query source and target names
            cursor.execute("SELECT name FROM entities WHERE id = ?", (rel["source_id"],))
            src_row = cursor.fetchone()
            src_name = src_row["name"] if src_row else rel["source_id"]
            
            cursor.execute("SELECT name FROM entities WHERE id = ?", (rel["target_id"],))
            tgt_row = cursor.fetchone()
            tgt_name = tgt_row["name"] if tgt_row else rel["target_id"]
            
            blocks.append(
                f"- ({src_name}) --[{rel['predicate']}]--> ({tgt_name}) [confidence: {rel.get('confidence', 0.80):.2f}, method: {rel.get('extraction_method', 'regex')}]"
            )
            
        return "\n=== RETRIEVED GRAPH KNOWLEDGE ===\n" + "\n".join(blocks) + "\n=================================\n"
