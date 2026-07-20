from __future__ import annotations
from typing import Dict

class ConfidenceAggregator:
    WEIGHTS = {
        "planner": 0.20,
        "critic": 0.20,
        "security": 0.30,
        "resource": 0.15,
        "efficiency": 0.075,
        "alignment": 0.075
    }

    @classmethod
    def aggregate(cls, scores: Dict[str, float]) -> float:
        """Computes a normalized weighted average from active specialist agent confidence scores."""
        total_weight = 0.0
        weighted_sum = 0.0
        
        for agent, score in scores.items():
            weight = cls.WEIGHTS.get(agent.lower(), 0.1)
            total_weight += weight
            weighted_sum += score * weight
            
        if total_weight == 0.0:
            return 1.0
            
        return round(weighted_sum / total_weight, 3)
