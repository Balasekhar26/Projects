from __future__ import annotations
from typing import List, Tuple
from backend.knowledge_graph.triple import Triple

class ExplanationEngine:
    """Generates human-readable rationales and trace justifications for inferred facts."""

    @staticmethod
    def generate_explanation(
        inferred_triple: Triple,
        rules_applied: str,
        premises: List[Triple]
    ) -> str:
        """Constructs a natural language summary explaining how a triple was deduced."""
        premise_texts = []
        for p in premises:
            premise_texts.append(f"({p.subject} {p.predicate.lower().replace('_', ' ')} {p.object})")
        
        explanation = (
            f"Inferred fact: [{inferred_triple.subject} {inferred_triple.predicate} {inferred_triple.object}] "
            f"with confidence {inferred_triple.confidence:.2f}.\n"
            f"Reasoning Rule: {rules_applied}\n"
            f"Premises: {', '.join(premise_texts)}"
        )
        return explanation
