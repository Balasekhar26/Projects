"""
Self-Improvement Engine Schema — Step 25
==========================================

ImprovementGoal
    The primary output of the Self-Improvement Engine.
    Represents a detected weakness + a plan to fix it.

WeaknessReport
    Aggregated analysis of all domains' weakness signals.
    Produced before generating goals; used for triage.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


class ImprovementPriority(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"


class GoalStatus(str, Enum):
    OPEN        = "open"         # Not yet acted on
    IN_PROGRESS = "in_progress"  # Actions have been started
    COMPLETED   = "completed"    # Domain weakness resolved
    STALE       = "stale"        # No progress in review window


@dataclass
class ImprovementGoal:
    """
    A concrete, actionable plan to improve performance in a domain.

    Fields
    ------
    goal_id : str
        UUID4 identifier.
    domain : str
        The skill/knowledge domain this goal targets.
    problem : str
        Human-readable description of the observed problem.
        e.g. "RF calculations fail 67% of the time"
    root_cause : str
        Hypothesised underlying cause derived from mistake patterns.
        e.g. "Insufficient understanding of impedance matching"
    evidence_count : int
        How many mistakes/failures led to this goal.
    priority : ImprovementPriority
        Urgency level.
    recommended_actions : List[str]
        Ordered list of concrete steps to improve the domain.
    status : GoalStatus
        Lifecycle state of this goal.
    created_at : str
        ISO-8601 UTC creation timestamp.
    completed_at : str
        ISO-8601 UTC completion timestamp (empty if not completed).
    effectiveness : float
        Measured improvement after goal completion. [0.0 – 1.0]
        -1.0 = not yet measured.
    success_rate_before : float
        Domain success_rate at time of goal creation.
    notes : str
        Optional free-form context.
    """
    goal_id:              str                  = field(default_factory=lambda: str(uuid.uuid4()))
    domain:               str                  = "general"
    problem:              str                  = ""
    root_cause:           str                  = ""
    evidence_count:       int                  = 1
    priority:             ImprovementPriority  = ImprovementPriority.MEDIUM
    recommended_actions:  List[str]            = field(default_factory=list)
    status:               GoalStatus           = GoalStatus.OPEN
    created_at:           str                  = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at:         str                  = ""
    effectiveness:        float                = -1.0
    success_rate_before:  float                = -1.0
    notes:                str                  = ""

    def to_dict(self) -> dict:
        return {
            "goal_id":             self.goal_id,
            "domain":              self.domain,
            "problem":             self.problem,
            "root_cause":          self.root_cause,
            "evidence_count":      self.evidence_count,
            "priority":            self.priority.value,
            "recommended_actions": self.recommended_actions,
            "status":              self.status.value,
            "created_at":          self.created_at,
            "completed_at":        self.completed_at,
            "effectiveness":       self.effectiveness,
            "success_rate_before": self.success_rate_before,
            "notes":               self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ImprovementGoal":
        d = dict(d)
        d["priority"] = ImprovementPriority(d.get("priority", "medium"))
        d["status"]   = GoalStatus(d.get("status", "open"))
        return cls(**d)


@dataclass
class DomainWeakness:
    """
    Aggregated weakness signal for one domain.
    Intermediate output of the PatternMiner.

    Fields
    ------
    domain : str
        The domain being analysed.
    failure_count : int
        Total failures detected in this domain.
    partial_count : int
        Total partial outcomes.
    total_attempts : int
        Total attempts (from SkillMemory, if available).
    failure_rate : float
        failure_count / max(total_attempts, failure_count).
    top_lessons : List[str]
        Most common lessons/patterns from mistakes.
    top_knowledge_gaps : List[str]
        Identified knowledge gaps from LearningStore.
    weakness_score : float
        Composite weakness signal in [0.0, 1.0].
        Higher = weaker, more urgent to improve.
    """
    domain:             str        = "general"
    failure_count:      int        = 0
    partial_count:      int        = 0
    total_attempts:     int        = 0
    failure_rate:       float      = 0.0
    top_lessons:        List[str]  = field(default_factory=list)
    top_knowledge_gaps: List[str]  = field(default_factory=list)
    weakness_score:     float      = 0.0

    def to_dict(self) -> dict:
        return {
            "domain":             self.domain,
            "failure_count":      self.failure_count,
            "partial_count":      self.partial_count,
            "total_attempts":     self.total_attempts,
            "failure_rate":       round(self.failure_rate, 4),
            "top_lessons":        self.top_lessons,
            "top_knowledge_gaps": self.top_knowledge_gaps,
            "weakness_score":     round(self.weakness_score, 4),
        }
