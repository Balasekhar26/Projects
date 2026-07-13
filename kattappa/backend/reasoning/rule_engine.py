from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List, Tuple

@dataclass
class Rule:
    """Represents a logic rule for forward-chaining inference reasoning."""
    name: str
    antecedents: List[Tuple[str, str, str]]  # Patterns of (S, P, O)
    consequent: Tuple[str, str, str]        # Inferred pattern of (S, P, O)
    propagation_weight: float = 0.90         # Penalty applied to propagated confidence

    def evaluate(self, facts: List[dict]) -> bool:
        # Simple evaluation logic matching fact keys
        pass
