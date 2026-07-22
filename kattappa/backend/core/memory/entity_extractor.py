from __future__ import annotations
import json
import os
import uuid
from backend.core.logger import log_event
from backend.core.model_router import ask_model

class EntityExtractor:
    @classmethod
    def extract_entities(cls, text: str) -> list[dict]:
        import sys
        use_mock = (
            os.getenv("KATTAPPA_ENV") == "test" or 
            os.getenv("KATTAPPA_TEST_MODE") == "true" or
            os.getenv("KATTAPPA_MOCK_LLM") == "true"
        )
        
        if use_mock:
            entities = []
            lower_text = text.lower()
            if "bala" in lower_text:
                entities.append({
                    "id": "entity_bala",
                    "name": "Bala",
                    "type": "Person",
                    "metadata": {"role": "developer"}
                })
            if "kattappa" in lower_text:
                entities.append({
                    "id": "entity_kattappa",
                    "name": "Kattappa",
                    "type": "Project",
                    "metadata": {"role": "AI agent"}
                })
            if "telugu" in lower_text:
                entities.append({
                    "id": "entity_telugu",
                    "name": "Telugu",
                    "type": "Language",
                    "metadata": {}
                })
            if "windows" in lower_text:
                entities.append({
                    "id": "entity_windows",
                    "name": "Windows",
                    "type": "Device",
                    "metadata": {"os": "Windows"}
                })
            if not entities:
                entities.append({
                    "id": f"entity_{uuid.uuid4().hex[:6]}",
                    "name": text[:30].strip(),
                    "type": "Concept",
                    "metadata": {}
                })
            return entities
        else:
            prompt = (
                f"You are a Knowledge Graph Entity Extractor.\n"
                f"Analyze the following text and extract all entities (people, projects, organizations, languages, devices, concepts).\n"
                f"Text: \"{text}\"\n\n"
                f"Output ONLY a valid JSON array of objects. Each object must contain:\n"
                f"- id (string, lower_snake_case starting with entity_)\n"
                f"- name (string, original capitalizations)\n"
                f"- type (string, one of: Person, Organization, Project, Device, File, Location, Skill, Goal, Tool, Concept)\n"
                f"- metadata (dict of key-value pairs)\n"
                f"Example: "
                f'[{{"id": "entity_bala", "name": "Bala", "type": "Person", "metadata": {{"role": "developer"}}}}]'
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
                log_event("entity_extractor_llm_error", f"LLM failed to extract entities: {e}")
                return []
