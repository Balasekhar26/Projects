from __future__ import annotations
import time
from typing import Any, Dict, List
from backend.knowledge_graph.triple import Triple

class TripleExtractor:
    """Extracts ontology-compliant semantic triples from natural query parameters."""

    @staticmethod
    def extract_from_query(query: str, entities: Dict[str, Any]) -> List[Triple]:
        triples = []
        now_ts = time.time()

        intent = entities.get("intent", "")
        
        # 1. Handle schedule_meeting
        if intent == "schedule_meeting":
            triples.append(Triple("user", "scheduled", "meeting", 0.95, now_ts, "runtime"))
            
            participants = entities.get("participants", [])
            for p in participants:
                triples.append(Triple("meeting", "MEMBER_OF", p, 0.90, now_ts, "runtime"))
            
            dt = entities.get("datetime")
            if dt:
                triples.append(Triple("meeting", "SCHEDULED", str(dt), 0.95, now_ts, "runtime"))

        # 2. Location mappings
        if "hyderabad" in query.lower():
            triples.append(Triple("user", "LOCATED_IN", "Hyderabad", 0.95, now_ts, "conversation"))
        elif "guntur" in query.lower():
            triples.append(Triple("user", "LOCATED_IN", "Guntur", 0.95, now_ts, "conversation"))

        # 3. Preferences mapping
        if "prefers" in query.lower() or "preference" in query.lower():
            triples.append(Triple("user", "PREFERS", "afternoon meetings", 0.90, now_ts, "conversation"))

        return triples
