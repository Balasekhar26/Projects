"""
Learning Engine Schema — core data structures for Step 22.

A LearningRecord is the output of the Learning Engine: a structured,
durable knowledge unit derived from one or more Reflections.

It is the bridge between raw experience and actionable knowledge:

    Reflection (what happened)
        ↓ LessonExtractor
    LearningRecord (what was learned)
        ↓ MemoryPromoter
    Semantic Memory / Skill Memory (durable state)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class LearningPriority(str, Enum):
    """Priority level for acting on a learning record."""
    CRITICAL = "critical"   # Must be acted on immediately
    HIGH     = "high"       # Important, act soon
    MEDIUM   = "medium"     # Useful, schedule for review
    LOW      = "low"        # Nice-to-know, low urgency


class RecordType(str, Enum):
    """What kind of knowledge this record represents."""
    RULE       = "rule"        # A behavioural rule ("always validate X before Y")
    PATTERN    = "pattern"     # A recurring pattern observed across reflections
    KNOWLEDGE  = "knowledge"   # A domain fact or concept
    SKILL_GAP  = "skill_gap"   # An identified weakness in a skill domain
    SKILL_WIN  = "skill_win"   # A confirmed strength in a skill domain


@dataclass
class LearningRecord:
    """
    A structured, durable unit of knowledge derived from reflection.

    Fields
    ------
    record_id : str
        UUID4 identifier.
    timestamp : str
        ISO-8601 UTC creation timestamp.
    source_reflection_id : str
        ID of the Reflection that triggered this record.
        May be empty if derived from multiple reflections.
    domain : str
        Skill/knowledge domain (e.g. "translation", "reasoning").
    record_type : RecordType
        What kind of knowledge this record represents.
    lesson : str
        The raw lesson text copied from the source Reflection.
    knowledge : str
        The distilled knowledge statement in durable form.
        e.g. "RF calculations require impedance matching analysis first."
    priority : LearningPriority
        How urgently this knowledge should be acted on.
    confidence : float
        Current confidence that this knowledge is correct. [0.0 – 1.0]
    importance : float
        How important this knowledge is for Kattappa's goals. [0.0 – 1.0]
    frequency : int
        How many times this same lesson/pattern has been reinforced.
    success_rate : float
        Observed success rate when applying this knowledge. [0.0 – 1.0]
        Starts at -1.0 (unobserved) until first application.
    next_review : str
        ISO-8601 UTC timestamp of when this record should be reviewed.
        Empty string = no scheduled review.
    notes : str
        Optional extra context.
    """
    record_id:             str            = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:             str            = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_reflection_id:  str            = ""
    domain:                str            = "general"
    record_type:           RecordType     = RecordType.KNOWLEDGE
    lesson:                str            = ""
    knowledge:             str            = ""
    priority:              LearningPriority = LearningPriority.MEDIUM
    confidence:            float          = 0.6
    importance:            float          = 0.5
    frequency:             int            = 1
    success_rate:          float          = -1.0   # -1.0 = not yet observed
    next_review:           str            = ""
    notes:                 str            = ""

    def to_dict(self) -> dict:
        return {
            "record_id":            self.record_id,
            "timestamp":            self.timestamp,
            "source_reflection_id": self.source_reflection_id,
            "domain":               self.domain,
            "record_type":          self.record_type.value,
            "lesson":               self.lesson,
            "knowledge":            self.knowledge,
            "priority":             self.priority.value,
            "confidence":           self.confidence,
            "importance":           self.importance,
            "frequency":            self.frequency,
            "success_rate":         self.success_rate,
            "next_review":          self.next_review,
            "notes":                self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LearningRecord":
        d = dict(d)
        d["record_type"] = RecordType(d.get("record_type", "knowledge"))
        d["priority"]    = LearningPriority(d.get("priority", "medium"))
        return cls(**d)
