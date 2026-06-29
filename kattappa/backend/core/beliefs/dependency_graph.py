"""Belief Management Component 3: Dependency Graph.

Builds and manages a directed dependency graph (DAG) over versioned beliefs.
Handles circular cycle detection and propagates confidence changes downstream.
"""
from __future__ import annotations

import time
import logging
from typing import List, Set, Optional

from backend.core.beliefs.belief import BeliefDependency, Belief
from backend.core.beliefs.belief_store import BeliefStore
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


class DependencyGraph:
    """Manages parent-child belief truth dependencies and propagation walks."""

    def __init__(self, store: BeliefStore) -> None:
        self._store = store

    def add_dependency(self, parent_id: str, child_id: str, dependency_type: str = "supports") -> None:
        """Establishes a dependency edge. Prevents circular dependencies from being saved."""
        if parent_id == child_id:
            raise ValueError("Belief cannot depend on itself")

        # 1. Circular path check
        if self._has_path(child_id, parent_id):
            log_event(
                "circular_dependency_aborted",
                f"Aborted dependency registration: {child_id} -> {parent_id} would introduce a cycle.",
            )
            raise ValueError(f"Circular dependency detected: {child_id} already leads to {parent_id}")

        dep = BeliefDependency(
            parent_belief_id=parent_id,
            child_belief_id=child_id,
            dependency_type=dependency_type,
        )
        self._store.add_dependency(dep)
        log_event(
            "belief_dependency_registered",
            f"Belief dependency registered: {child_id} ({dependency_type}) parent={parent_id}",
        )

    def remove_dependency(self, parent_id: str, child_id: str) -> None:
        self._store.remove_dependency(parent_id, child_id)

    def propagate_confidence(self, parent_belief: Belief, visited: Optional[Set[str]] = None) -> None:
        """Recursively walks downstream child dependencies and bounds their confidence.

        Formula: child.confidence = min(child.confidence, parent.confidence)
        """
        if visited is None:
            visited = set()

        if parent_belief.belief_id in visited:
            logger.warning("Circular loop detected during propagation at %s", parent_belief.belief_id)
            return

        visited.add(parent_belief.belief_id)

        # Retrieve downstream child links
        links = self._store.get_child_dependencies(parent_belief.belief_id)
        for link in links:
            child = self._store.get_belief(link.child_belief_id)
            if not child:
                continue

            # Bounding check
            if parent_belief.confidence < child.confidence:
                updated_confidence = min(child.confidence, parent_belief.confidence)
                
                # Create a versioned revision of the child belief
                revised_child = Belief(
                    belief_id=child.belief_id,
                    claim_subject=child.claim_subject,
                    claim_predicate=child.claim_predicate,
                    claim_value=child.claim_value,
                    confidence=updated_confidence,
                    truth_status=child.truth_status,
                    source_ids=child.source_ids,
                    evidence_ids=child.evidence_ids + parent_belief.evidence_ids,
                    created_at=child.created_at,
                    updated_at=time.time(),
                    valid_from=child.valid_from,
                    valid_until=child.valid_until,
                    version=child.version + 1,
                    metadata=child.metadata,
                )
                self._store.save_belief(revised_child)

                log_event(
                    "tms_confidence_propagated",
                    f"Propagated confidence bound to child belief {child.belief_id} "
                    f"({child.claim_subject}.{child.claim_predicate}) -> {updated_confidence:.2f}",
                )

                # Recursively walk further downstream
                self.propagate_confidence(revised_child, visited)

    # ------------------------------------------------------------------
    # Helper path search (DFS)
    # ------------------------------------------------------------------

    def _has_path(self, start_id: str, target_id: str, visited: Optional[Set[str]] = None) -> bool:
        """Returns True if there is a path from start_id to target_id in the dependency tree."""
        if start_id == target_id:
            return True

        if visited is None:
            visited = set()

        visited.add(start_id)

        children = self._store.get_child_dependencies(start_id)
        for c in children:
            child_id = c.child_belief_id
            if child_id not in visited:
                if self._has_path(child_id, target_id, visited):
                    return True
        return False
