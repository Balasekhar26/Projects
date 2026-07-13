from __future__ import annotations
from typing import Any, Dict, List
from backend.knowledge_graph.graph_store import GraphStore

class UtilityAdjuster:
    """Adapts and modifies planner utility scores based on inferred semantic constraints."""

    def __init__(self, store: GraphStore = None) -> None:
        self.store = store or GraphStore()

    def adjust_utility(self, action_name: str, payload: Dict[str, Any], base_utility: float) -> float:
        """Applies penalties or boosts to the plan branch utility based on preference reasoning."""
        adjusted = base_utility
        
        # Check meeting preferences
        if action_name == "create_meeting":
            time_val = payload.get("time", "").lower()
            
            # Fetch active user preferences
            prefs = self.store.get_triples(subject="user", predicate="PREFERS")
            for p in prefs:
                if p.object == "afternoon meetings":
                    # If meeting is scheduled in morning, penalize utility score
                    is_morning = any(m in time_val for m in ["am", "morning", "10:00", "09:00", "11:00", "10 am", "9 am"])
                    if is_morning:
                        # Penalize utility score by 0.35
                        adjusted -= 0.35

        return round(max(0.1, adjusted), 2)
