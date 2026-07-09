"""Kattappa Evaluation and Reflection Engine package (Program 35.0)."""
from __future__ import annotations

from backend.core.reflection.outcome_evaluator import OutcomeEvaluator
from backend.core.reflection.reflection_generator import ReflectionGenerator
from backend.core.reflection.self_critique import SelfCritiqueLoop
from backend.core.reflection.reflection_engine import ReflectionEngine
from backend.core.reflection.counterfactual_engine import CounterfactualSimulationEngine

__all__ = [
    "OutcomeEvaluator",
    "ReflectionGenerator",
    "SelfCritiqueLoop",
    "ReflectionEngine",
    "CounterfactualSimulationEngine",
]
