"""Planner Simulation Result Schema (Program 12.3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SimulationResult:
    """Holds predicted outcome metrics for a simulated execution Plan."""
    success_probability: float
    expected_duration: float
    duration_variance: float
    expected_cost: float
    risk_score: float
    failure_modes: List[str] = field(default_factory=list)
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success_probability": self.success_probability,
            "expected_duration": self.expected_duration,
            "duration_variance": self.duration_variance,
            "expected_cost": self.expected_cost,
            "risk_score": self.risk_score,
            "failure_modes": self.failure_modes,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }
