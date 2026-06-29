"""Learning and Consolidation Orchestrator Engine (Program 7).

Coordinates candidate evaluation queues, conflict detection, safety,
consolidations, and version rollbacks.
"""
from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

from backend.core.learning.confidence import ConfidenceEngine
from backend.core.learning.conflict import ConflictDetector
from backend.core.learning.safety import SafetyPolicyEngine
from backend.core.learning.consolidator import MemoryConsolidator
from backend.core.learning.models import CandidateStatus, LearningAuditEntry, LearningCandidateVersion
from backend.core.reflection.models import LearningCandidate

logger = logging.getLogger(__name__)


class LearningEngine:
    """Master coordinator directing the safety-guarded memory update loop."""

    _instance: Optional[LearningEngine] = None

    def __init__(self) -> None:
        self.queue: Dict[str, LearningCandidate] = {}
        self.audit_log: List[LearningAuditEntry] = []
        self.consolidator = MemoryConsolidator()

    @classmethod
    def get_instance(cls) -> LearningEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def submit_candidate(self, candidate: LearningCandidate, evidence_count: int = 1) -> LearningCandidate:
        """Submits a new candidate, validating conflicts and safety rules to auto-apply or queue."""
        # 1. Update confidence based on evidence count
        candidate.confidence = ConfidenceEngine.calculate_score(evidence_count)

        # 2. Check for conflicts
        conflicts = ConflictDetector.detect_conflicts(candidate, list(self.queue.values()))
        if conflicts:
            logger.warning("Conflict detected for candidate: %s. Quarantining.", candidate.candidate_id)
            candidate.status = CandidateStatus.PENDING
            candidate.priority = "High"  # Boost priority for human resolution
            self.queue[candidate.candidate_id] = candidate
            return candidate

        # 3. Filter via SafetyPolicyEngine
        if SafetyPolicyEngine.is_safe_to_auto_apply(candidate):
            logger.info("Candidate %s passed safety checks. Auto-applying.", candidate.candidate_id)
            self._apply(candidate)
        else:
            logger.info("Candidate %s flagged as unsafe or low confidence. Queued.", candidate.candidate_id)
            candidate.status = CandidateStatus.PENDING
            self.queue[candidate.candidate_id] = candidate

        return candidate

    def approve_candidate(self, candidate_id: str) -> bool:
        """Manually approves and applies a queued pending learning candidate."""
        candidate = self.queue.get(candidate_id)
        if not candidate or candidate.status != CandidateStatus.PENDING:
            return False

        self._apply(candidate)
        return True

    def reject_candidate(self, candidate_id: str) -> bool:
        """Manually rejects and cancels a queued pending learning candidate."""
        candidate = self.queue.get(candidate_id)
        if not candidate or candidate.status != CandidateStatus.PENDING:
            return False

        candidate.status = CandidateStatus.REJECTED
        return True

    def rollback_version(self, version_id: str) -> bool:
        """Rolls back applied configuration changes to their pre-applied states."""
        return self.consolidator.rollback(version_id)

    def _apply(self, candidate: LearningCandidate) -> None:
        # Consolidate memory configurations
        version = self.consolidator.consolidate(candidate)
        candidate.status = CandidateStatus.APPLIED
        self.queue[candidate.candidate_id] = candidate

        # Log audit entry
        audit_id = f"aud_{uuid.uuid4().hex[:6]}"
        audit_entry = LearningAuditEntry(
            entry_id=audit_id,
            candidate_id=candidate.candidate_id,
            target_type=candidate.target_type,
            evidence_count=1,
            confidence=candidate.confidence,
            notes=f"Consolidated successfully into version {version.version_id}",
        )
        self.audit_log.append(audit_entry)

    def get_pending_candidates(self) -> List[LearningCandidate]:
        """Returns all candidates requiring manual human approval review."""
        return [c for c in self.queue.values() if c.status == CandidateStatus.PENDING]

    def get_all_candidates(self) -> List[LearningCandidate]:
        """Returns all registered candidates."""
        return list(self.queue.values())
