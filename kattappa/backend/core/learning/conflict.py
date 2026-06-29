"""Learning Conflict Detector (Program 7).

Identifies contradictory update rules targeted at identical policy variables.
"""
from __future__ import annotations

from typing import Any, Dict, List
from backend.core.reflection.models import LearningCandidate


class ConflictDetector:
    """Flags contradictory recommendation parameters targeting same policy variables."""

    @staticmethod
    def detect_conflicts(
        new_candidate: LearningCandidate,
        existing_candidates: List[LearningCandidate],
    ) -> List[LearningCandidate]:
        """Detects if any existing candidate targets the same type and has opposing parameters."""
        conflicts = []
        new_target = new_candidate.target_type
        new_update = new_candidate.proposed_update

        for existing in existing_candidates:
            if existing.target_type != new_target:
                continue

            # Compare keys
            for key, val in new_update.items():
                if key in existing.proposed_update:
                    exist_val = existing.proposed_update[key]
                    # If target is identical but value differs, flag conflict!
                    if val != exist_val:
                        conflicts.append(existing)
                        break

        return conflicts
