from __future__ import annotations
import time
from typing import Any, List, Tuple
from backend.knowledge_graph.triple import Triple
from backend.knowledge_graph.graph_store import GraphStore
from backend.reasoning.confidence_propagation import ConfidencePropagator
from backend.reasoning.explanation_engine import ExplanationEngine

class InferenceEngine:
    """Performs forward-chaining semantic reasoning over active triples in storage."""

    def __init__(self, store: GraphStore = None) -> None:
        self.store = store or GraphStore()

    def run_inference(self) -> List[Tuple[Triple, str]]:
        """Scans the active triples store, deduces new relationships, and persists them."""
        inferred: List[Tuple[Triple, str]] = []
        now_ts = time.time()
        
        # 1. Fetch active triples
        active = self.store.get_triples(status="ACTIVE")

        # Helper to find matching triples
        def find_facts(subj: str = None, pred: str = None, obj: str = None) -> List[Triple]:
            results = []
            for t in active:
                if subj and t.subject != subj:
                    continue
                if pred and t.predicate != pred:
                    continue
                if obj and t.object != obj:
                    continue
                results.append(t)
            return results

        # Deduce Location: (X, WORKS_AT, Y) & (Y, LOCATED_IN, Z) => (X, LOCATED_IN, Z)
        works_at_triples = find_facts(pred="WORKS_AT")
        for w in works_at_triples:
            org = w.object
            org_locations = find_facts(subj=org, pred="LOCATED_IN")
            for loc in org_locations:
                dest = loc.object
                # We inferred that X is located in dest
                derived_conf = ConfidencePropagator.propagate([w.confidence, loc.confidence], weight=0.95)
                derived_triple = Triple(w.subject, "LOCATED_IN", dest, derived_conf, now_ts, "inference")
                
                explanation = ExplanationEngine.generate_explanation(
                    derived_triple,
                    "Transitive Location Rule",
                    [w, loc]
                )
                inferred.append((derived_triple, explanation))

        # Persist newly derived triples to graph store
        for t, _ in inferred:
            self.store.add_triple(t)

        return inferred
