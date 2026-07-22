from __future__ import annotations
import json
import os
from backend.core.logger import log_event
from backend.core.model_router import ask_model

class RelationshipExtractor:
    @classmethod
    def extract_relationships(cls, text: str, entities: list[dict]) -> list[dict]:
        import sys
        use_mock = (
            os.getenv("KATTAPPA_ENV") == "test" or 
            os.getenv("KATTAPPA_TEST_MODE") == "true" or
            os.getenv("KATTAPPA_MOCK_LLM") == "true"
        )
        
        if use_mock:
            relationships = []
            entity_ids = {e["id"] for e in entities}
            
            if "entity_bala" in entity_ids and "entity_kattappa" in entity_ids:
                relationships.append({
                    "id": "rel_bala_develops_kattappa",
                    "source_id": "entity_bala",
                    "target_id": "entity_kattappa",
                    "predicate": "develops",
                    "metadata": {}
                })
            if "entity_bala" in entity_ids and "entity_telugu" in entity_ids:
                relationships.append({
                    "id": "rel_bala_prefers_telugu",
                    "source_id": "entity_bala",
                    "target_id": "entity_telugu",
                    "predicate": "prefers",
                    "metadata": {}
                })
            if "entity_bala" in entity_ids and "entity_windows" in entity_ids:
                relationships.append({
                    "id": "rel_bala_uses_windows",
                    "source_id": "entity_bala",
                    "target_id": "entity_windows",
                    "predicate": "uses",
                    "metadata": {}
                })
            return relationships
        else:
            prompt = (
                f"You are a Knowledge Graph Relationship Extractor.\n"
                f"Given the text: \"{text}\"\n"
                f"And the list of extracted entities: {json.dumps(entities)}\n\n"
                f"Extract relationships linking these entities together.\n"
                f"Output ONLY a valid JSON array of objects. Each object must contain:\n"
                f"- id (string, lower_snake_case starting with rel_)\n"
                f"- source_id (string matching an entity id)\n"
                f"- target_id (string matching an entity id)\n"
                f"- predicate (string, one of: works_at, develops, owns, prefers, uses, depends_on, installed_on, located_in, related_to, created_by)\n"
                f"- metadata (dict of key-value pairs)\n"
                f"Example:\n"
                f'[{{"id": "rel_bala_prefers_telugu", "source_id": "entity_bala", "target_id": "entity_telugu", "predicate": "prefers", "metadata": {{}}}}]'
            )
            try:
                res = ask_model(prompt, role="planning")
                clean_res = res.strip()
                if clean_res.startswith("```json"):
                    clean_res = clean_res[7:]
                if clean_res.endswith("```"):
                    clean_res = clean_res[:-3]
                clean_res = clean_res.strip()
                return json.loads(clean_res)
            except Exception as e:
                log_event("relationship_extractor_llm_error", f"LLM failed to extract relationships: {e}")
                return []
