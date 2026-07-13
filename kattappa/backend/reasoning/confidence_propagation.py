from __future__ import annotations
from typing import List

class ConfidencePropagator:
    """Computes uncertainty propagation through multi-hop logical deduction chains."""

    @staticmethod
    def propagate(confidences: List[float], weight: float = 0.90) -> float:
        """Combines multiple input confidences, bounding the result by a reasoning step weight."""
        if not confidences:
            return 0.0
        # Multiplicative propagation (independent probabilities assumption)
        product = 1.0
        for c in confidences:
            product *= c
        return round(product * weight, 2)
