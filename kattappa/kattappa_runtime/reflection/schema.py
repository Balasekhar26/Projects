"""
Reflection Schema — core data structures for the Reflection Engine.

A Reflection is an immutable snapshot of what Kattappa did,
what happened, and what was learned from it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class OutcomeLabel(str, Enum):
    """Coarse classification of an action cycle's result."""
    SUCCESS  = "success"   # Goal fully achieved
    PARTIAL  = "partial"   # Goal partially achieved or ambiguous
    FAILURE  = "failure"   # Goal failed or produced wrong output


@dataclass
class Reflection:
    """
    A structured record of one completed action cycle.

    Fields
    ------
    reflection_id : str
        UUID4 identifier, auto-generated.
    timestamp : str
        ISO-8601 UTC timestamp of when the reflection was created.
    domain : str
        The skill/knowledge domain involved (e.g. "translation",
        "code_generation", "reasoning").
    input_text : str
        The original request or context given to Kattappa.
    action_taken : str
        The specific action or tool call that was made.
    result : str
        The observable outcome of the action.
    outcome : OutcomeLabel
        Coarse classification: success / partial / failure.
    lesson : str
        One-sentence distilled lesson from this event.
    confidence_delta : float
        How much to adjust domain confidence by (positive or negative).
        Range: -1.0 … +1.0
    is_mistake : bool
        True when the outcome was a failure or partial that should be
        tracked for future self-improvement analysis.
    notes : str
        Optional free-form notes for richer context.
    """
    reflection_id:    str           = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:        str           = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    domain:           str           = "general"
    input_text:       str           = ""
    action_taken:     str           = ""
    result:           str           = ""
    outcome:          OutcomeLabel  = OutcomeLabel.SUCCESS
    lesson:           str           = ""
    confidence_delta: float         = 0.0
    is_mistake:       bool          = False
    notes:            str           = ""

    def to_dict(self) -> dict:
        return {
            "reflection_id":    self.reflection_id,
            "timestamp":        self.timestamp,
            "domain":           self.domain,
            "input_text":       self.input_text,
            "action_taken":     self.action_taken,
            "result":           self.result,
            "outcome":          self.outcome.value,
            "lesson":           self.lesson,
            "confidence_delta": self.confidence_delta,
            "is_mistake":       self.is_mistake,
            "notes":            self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Reflection":
        d = dict(d)
        d["outcome"] = OutcomeLabel(d.get("outcome", "success"))
        return cls(**d)
