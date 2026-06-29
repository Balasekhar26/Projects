"""Memory Consolidation and Version Manager (Program 7).

Applies learning candidates to long-term memory configurations with version rollback support.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.core.learning.models import LearningCandidateVersion
from backend.core.reflection.models import LearningCandidate

logger = logging.getLogger(__name__)


class MemoryConsolidator:
    """Manages versioned configuration updates and rollbacks of consolidated memory policies."""

    def __init__(self) -> None:
        # Active consolidated memory configurations/policies
        self.active_config: Dict[str, Any] = {
            "max_retries": 3,
            "backoff_policy": "linear",
            "verify_permissions_preflight": False,
            "cache_results": False,
        }
        # Version history stack
        self.versions: List[LearningCandidateVersion] = []

    def consolidate(self, candidate: LearningCandidate) -> LearningCandidateVersion:
        """Saves current state snapshot, consolidates candidate updates, and commits version."""
        version_id = f"v_{uuid.uuid4().hex[:6]}"
        logger.info("Consolidating candidate %s to memory (version %s)", candidate.candidate_id, version_id)

        # Record changes
        changes = dict(candidate.proposed_update)
        
        # Save snapshot of previous states to allow rollbacks
        previous_state = {}
        for key in changes:
            previous_state[key] = self.active_config.get(key)

        # Apply updates
        self.active_config.update(changes)

        # Save version metadata
        version = LearningCandidateVersion(
            version_id=version_id,
            changes={
                "applied": changes,
                "previous": previous_state,
            },
            description=candidate.explanation,
        )
        self.versions.append(version)
        return version

    def rollback(self, version_id: str) -> bool:
        """Finds version and rolls back active configurations to their pre-applied states."""
        target_idx = -1
        for idx, ver in enumerate(self.versions):
            if ver.version_id == version_id:
                target_idx = idx
                break

        if target_idx == -1:
            logger.warning("Version %s not found. Cannot rollback.", version_id)
            return False

        # Roll back from top of the stack down to the target index (inclusive)
        # to ensure state updates remain sequentially consistent.
        while len(self.versions) > target_idx:
            ver = self.versions.pop()
            previous = ver.changes.get("previous", {})
            for key, val in previous.items():
                self.active_config[key] = val
            logger.info("Rolled back version: %s", ver.version_id)

        return True
