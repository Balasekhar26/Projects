"""Truth Maintenance System (TMS) — Phase K21.6.

Implements explicit justifications, a justification manager, dependency tracking,
and transactional propagation (begin, commit, rollback) for belief updates.
"""
from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.cos.state_representation import BeliefState, BeliefStatus, PropertyValue
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass
class Justification:
    """Explicit justification tracking why a belief node is IN or OUT."""
    justification_id: str
    entity_uuid: str
    property_name: str
    supporting_evidence_ids: List[str] = field(default_factory=list)
    supporting_antecedents: List[Tuple[str, str]] = field(default_factory=list)  # (parent_uuid, parent_prop)
    status: str = "IN"  # IN or OUT


class JustificationManager:
    """Stores and manages justifications for all active belief nodes."""

    def __init__(self):
        # Maps (entity_uuid, property_name) -> Justification
        self.justifications: Dict[Tuple[str, str], Justification] = {}

    def add_justification(self, entity_uuid: str, property_name: str, justification: Justification) -> None:
        self.justifications[(entity_uuid, property_name)] = justification

    def get_justification(self, entity_uuid: str, property_name: str) -> Optional[Justification]:
        return self.justifications.get((entity_uuid, property_name))

    def invalidate_justification(self, entity_uuid: str, property_name: str) -> None:
        key = (entity_uuid, property_name)
        if key in self.justifications:
            self.justifications[key].status = "OUT"


class TruthMaintenanceSystem:
    """Truth Maintenance System (TMS) coordinator managing justifications and transactions."""

    def __init__(self, justification_manager: JustificationManager):
        self.justification_manager = justification_manager
        self.transaction_checkpoint: Optional[Tuple[Dict[Tuple[str, str], PropertyValue], Dict[Tuple[str, str], Justification]]] = None

    def begin(self, state: BeliefState) -> None:
        """Starts a revision transaction by checkpointing the active beliefs and justifications."""
        # Create a deep copy of all property values in the BeliefState
        state_checkpoint = {}
        for entity_id, props in state.entity_states.items():
            for prop_name, pv in props.items():
                state_checkpoint[(entity_id, prop_name)] = pv.clone()

        # Create a deep copy of the justifications
        justification_checkpoint = {}
        for key, j in self.justification_manager.justifications.items():
            justification_checkpoint[key] = copy.deepcopy(j)

        self.transaction_checkpoint = (state_checkpoint, justification_checkpoint)
        log_event("tms_transaction_started", "TMS transaction boundary successfully initialized.")

    def commit(self) -> None:
        """Commits the active transaction, clearing the rollback checkpoint."""
        self.transaction_checkpoint = None
        log_event("tms_transaction_committed", "TMS transaction successfully committed.")

    def rollback(self, state: BeliefState) -> None:
        """Rolls back the active state and justifications to the pre-transaction checkpoint."""
        if not self.transaction_checkpoint:
            logger.warning("Rollback requested but no active transaction checkpoint exists.")
            return

        state_checkpoint, justification_checkpoint = self.transaction_checkpoint

        # Restore BeliefState property values
        state.entity_states.clear()
        for (entity_id, prop_name), pv in state_checkpoint.items():
            state.set_property(entity_id, prop_name, pv)

        # Restore Justifications
        self.justification_manager.justifications = justification_checkpoint
        self.transaction_checkpoint = None
        log_event("tms_transaction_rolled_back", "TMS transaction successfully rolled back.")

    def propagate_justifications(self, state: BeliefState, dependencies: Dict[Tuple[str, str], Set[Tuple[str, str]]]) -> None:
        """Propagates justification invalidations downstream recursively."""
        visited: Set[Tuple[str, str]] = set()

        # Build list of initially invalid nodes
        invalid_nodes = []
        for entity_id, props in state.entity_states.items():
            for prop_name, pv in props.items():
                key = (entity_id, prop_name)
                justification = self.justification_manager.get_justification(entity_id, prop_name)

                # A node is invalid if its justification is OUT or it is retracted/refuted/unknown
                if ((justification is not None and justification.status == "OUT") or 
                    pv.status in (BeliefStatus.RETRACTED, BeliefStatus.REFUTED, BeliefStatus.UNKNOWN)):
                    invalid_nodes.append(key)

        # Recursively propagate justification loss to dependent child nodes
        for node in invalid_nodes:
            self._propagate_node_loss(state, dependencies, node, visited)

    def _propagate_node_loss(
        self,
        state: BeliefState,
        dependencies: Dict[Tuple[str, str], Set[Tuple[str, str]]],
        node: Tuple[str, str],
        visited: Set[Tuple[str, str]]
    ) -> None:
        if node in visited:
            return
        visited.add(node)

        parent_entity, parent_prop = node
        parent_pv = state.get_property(parent_entity, parent_prop)

        # If parent is invalid, propagate this to all downstream child nodes
        if node in dependencies:
            for child_entity, child_prop in dependencies[node]:
                child_key = (child_entity, child_prop)
                child_pv = state.get_property(child_entity, child_prop)

                if child_pv is not None:
                    # Invalidate child justification
                    self.justification_manager.invalidate_justification(child_entity, child_prop)

                    # Update child belief status to UNKNOWN and confidence to 0.0
                    child_pv.status = BeliefStatus.UNKNOWN
                    child_pv.confidence = 0.0
                    log_event(
                        "justification_loss_propagated", 
                        f"Justification loss propagated to child {child_entity}.{child_prop} due to parent {parent_entity}.{parent_prop}"
                    )

                    # Recurse downstream
                    self._propagate_node_loss(state, dependencies, child_key, visited)
