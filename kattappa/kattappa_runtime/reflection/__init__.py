"""
Kattappa Reflection Engine — Step 21
=====================================
The Reflection Engine is the self-awareness backbone of Kattappa.
After every action cycle (input → action → result), it:

  1. Classifies the outcome (success / partial / failure)
  2. Generates a structured Reflection record
  3. Adjusts confidence for the relevant skill domain
  4. Writes the reflection into episodic memory
  5. Promotes durable lessons to semantic memory
  6. Logs mistakes to a dedicated file for Step 25 (Self-Improvement Engine)

Public API
----------
  from kattappa_runtime.reflection import ReflectionEngine

  engine = ReflectionEngine(memory_provider)
  reflection = engine.reflect(
      input_text="translate 'hello' to Telugu",
      action_taken="called translation model",
      result="నమస్కారం",
      domain="translation",
      succeeded=True,
  )
"""

import warnings

warnings.warn(
    "kattappa_runtime.reflection is deprecated and will be removed in K5. Use backend.core.reflection_engine.py instead.",
    DeprecationWarning,
    stacklevel=2
)

from kattappa_runtime.reflection.engine import ReflectionEngine
from kattappa_runtime.reflection.schema import Reflection, OutcomeLabel

__all__ = ["ReflectionEngine", "Reflection", "OutcomeLabel"]
