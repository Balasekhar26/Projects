"""Learning Engine Data Models (Program 7).

Defines candidate lifecycles, versions, and learning audit log formats.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CandidateStatus(str, Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    EXPIRED = "Expired"
    APPLIED = "Applied"
    ROLLED_BACK = "RolledBack"


@dataclass
class LearningCandidateVersion:
    """Represents a consolidated version update applied to long-term memory."""
    version_id: str
    timestamp: float = field(default_factory=time.time)
    changes: Dict[str, Any] = field(default_factory=dict)
    applied_by: str = "System"
    description: str = ""


@dataclass
class LearningAuditEntry:
    """Audit entry recording provenance and evidence details of applied learnings."""
    entry_id: str
    candidate_id: str
    target_type: str
    evidence_count: int
    confidence: float
    timestamp: float = field(default_factory=time.time)
    notes: str = ""
