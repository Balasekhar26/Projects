import json
import re
from backend.core.memory.memory_store import MemoryStore

class GraphRetriever:
    @classmethod
    def traverse_relationships(cls, start_entity_id: str, max_depth: int = 3) -> list[dict]:
        """Performs a Breadth-First Search (BFS) path traversal to resolve multi-hop relationships up to max_depth, enforcing budget limits."""
        MAX_NODES = 50
        MAX_RELATIONS = 100
        
        visited = set()
        # queue stores: (entity_id, current_depth, accumulated_confidence)
        queue = [(start_entity_id, 0, 1.0)]
        results = []
        
        while queue:
            if len(visited) >= MAX_NODES or len(results) >= MAX_RELATIONS:
                break
                
            current, depth, path_conf = queue.pop(0)
            if current in visited or depth >= max_depth:
                continue
                
            visited.add(current)
            rels = MemoryStore.get_entity_relationships(current)
            
            for rel in rels:
                if len(results) >= MAX_RELATIONS:
                    break
                    
                meta = {}
                try:
                    meta = json.loads(rel["metadata_json"]) if rel.get("metadata_json") else {}
                except Exception:
                    pass
                edge_conf = meta.get("confidence", 0.80)
                
                # Apply confidence decay propagation
                rel_with_decay = dict(rel)
                rel_with_decay["confidence"] = path_conf * edge_conf
                rel_with_decay["metadata"] = meta
                
                if rel_with_decay not in results:
                    results.append(rel_with_decay)
                    
                neighbor = rel["target_id"] if rel["source_id"] == current else rel["source_id"]
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1, rel_with_decay["confidence"]))
                    
        return results

    @classmethod
    def query_graph(cls, query_text: str, max_depth: int = 3) -> str:
        """Finds matching entity seeds in the query and returns their dynamic depth traversals within budget limits."""
        query_words = re.findall(r"\w+", query_text.lower())
        
        conn = MemoryStore._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM entities")
        all_entities = [dict(row) for row in cursor.fetchall()]
        
        matching_entities = []
        for ent in all_entities:
            ent_name_clean = ent["name"].lower()
            if ent_name_clean in query_text.lower() or ent["id"] in query_words:
                matching_entities.append(ent)
                
        if not matching_entities:
            return ""
            
        all_traversals = []
        visited_rel_ids = set()
        
        # Implement dynamic depth expansion: start at depth 1, expand if results < 2
        for depth in range(1, max_depth + 1):
            all_traversals = []
            visited_rel_ids = set()
            
            for ent in matching_entities:
                rels = cls.traverse_relationships(ent["id"], max_depth=depth)
                for r in rels:
                    if r["id"] not in visited_rel_ids:
                        visited_rel_ids.add(r["id"])
                        all_traversals.append(r)
            
            if len(all_traversals) >= 2:
                break
                
        if not all_traversals:
            return ""
            
        blocks = []
        max_words_limit = 1125
        accumulated_words = 0
        
        for rel in all_traversals:
            cursor.execute("SELECT name FROM entities WHERE id = ?", (rel["source_id"],))
            src_row = cursor.fetchone()
            src_name = src_row["name"] if src_row else rel["source_id"]
            
            cursor.execute("SELECT name FROM entities WHERE id = ?", (rel["target_id"],))
            tgt_row = cursor.fetchone()
            tgt_name = tgt_row["name"] if tgt_row else rel["target_id"]
            
            category = rel.get("metadata", {}).get("category", "Unknown")
            
            line = f"- ({src_name}) --[{rel['predicate']}]--> ({tgt_name}) [confidence: {rel.get('confidence', 0.80):.2f}, category: {category}, method: {rel.get('extraction_method', 'regex_rule')}]"
            line_words_count = len(line.split())
            
            if accumulated_words + line_words_count > max_words_limit:
                break
                
            blocks.append(line)
            accumulated_words += line_words_count
            
        if not blocks:
            return ""
            
        return "\n=== RETRIEVED GRAPH KNOWLEDGE ===\n" + "\n".join(blocks) + "\n=================================\n"
