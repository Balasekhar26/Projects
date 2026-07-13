from __future__ import annotations
from typing import List, Optional
from backend.knowledge_graph.triple import Triple

class ContradictionDetector:
    """Detects logical contradictions (e.g. mutually exclusive values) in facts."""

    @staticmethod
    def detect_exclusivity_conflict(
        new_triple: Triple,
        existing_triples: List[Triple]
    ) -> Optional[Triple]:
        """Identifies if a new triple contradicts an existing active triple of same predicate (exclusivity rules)."""
        # Exclusivity rules: LOCATED_IN (cannot be in Hyderabad and Guntur simultaneously at same time)
        mutually_exclusive_predicates = {"LOCATED_IN", "WORKS_AT"}
        
        if new_triple.predicate not in mutually_exclusive_predicates:
            return None

        for ext in existing_triples:
            if ext.subject == new_triple.subject and ext.predicate == new_triple.predicate:
                if ext.object != new_triple.object:
                    return ext
        return None
