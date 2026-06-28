"""Belief Engine — Phase K21.3.

Implements the Belief Management System (BMS) with EvidenceFusion,
ContradictionDetector, TruthDependencyTracker, and BeliefEngine.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.cos.state_representation import BeliefState, ObservedState, PropertyValue
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


class EvidenceFusion:
    """Computes recursive Bayesian log-odds property value combinations."""

    @staticmethod
    def _to_log_odds(prob: float) -> float:
        # Clamp to avoid division by zero or log of zero
        p = max(0.001, min(0.999, prob))
        return math.log(p / (1.0 - p))

    @staticmethod
    def _to_probability(log_odds: float) -> float:
        try:
            return 1.0 / (1.0 + math.exp(-log_odds))
        except OverflowError:
            return 1.0 if log_odds > 0 else 0.0

    @classmethod
    def fuse_properties(cls, prior: PropertyValue, incoming: PropertyValue) -> PropertyValue:
        """Fuses incoming observation confidence with prior belief using log-odds summation."""
        # If the values are identical, we strengthen the belief using log-odds accumulation
        if prior.value == incoming.value:
            lo_prior = cls._to_log_odds(prior.confidence)
            lo_incoming = cls._to_log_odds(incoming.confidence)
            fused_prob = cls._to_probability(lo_prior + lo_incoming)
        else:
            # If values differ, we weigh them by source reliability
            alpha = incoming.source.reliability
            fused_prob = prior.confidence + alpha * (incoming.confidence - prior.confidence)

        # Build fused PropertyValue tracking history
        return PropertyValue(
            value=incoming.value if fused_prob > prior.confidence else prior.value,
            confidence=fused_prob,
            source=incoming.source,
            timestamp=max(prior.timestamp, incoming.timestamp),
            variance=(prior.variance + incoming.variance) / 2.0,
            history=[prior.clone()] + [h.clone() for h in prior.history]
        )


class ContradictionDetector:
    """Detects and registers conflicting assertions in property states."""

    def __init__(self, confidence_threshold: float = 0.60):
        self.confidence_threshold = confidence_threshold
        self.contradictions: List[Dict[str, Any]] = []

    def check_contradiction(
        self,
        entity_uuid: str,
        prop_name: str,
        prior: PropertyValue,
        incoming: PropertyValue
    ) -> Optional[Dict[str, Any]]:
        """Identifies conflicting assertions with high confidence scores."""
        if prior.value == incoming.value:
            return None

        # Contradiction triggers when both values have high confidence
        if prior.confidence >= self.confidence_threshold and incoming.confidence >= self.confidence_threshold:
            conflict = {
                "entity_uuid": entity_uuid,
                "property_name": prop_name,
                "prior_value": prior.value,
                "prior_confidence": prior.confidence,
                "incoming_value": incoming.value,
                "incoming_confidence": incoming.confidence,
                "timestamp": time.time()
            }
            self.contradictions.append(conflict)
            log_event(
                "contradiction_detected", 
                f"Conflict on {entity_uuid}.{prop_name}: '{prior.value}' vs '{incoming.value}'"
            )
            return conflict
        return None


class TruthDependencyTracker:
    """Maintains logical truth dependencies between parent and child derived properties."""

    def __init__(self):
        # Maps (parent_uuid, parent_prop) -> Set of (child_uuid, child_prop)
        self.dependencies: Dict[Tuple[str, str], Set[Tuple[str, str]]] = {}

    def register_dependency(
        self,
        child_uuid: str,
        child_prop: str,
        parent_uuid: str,
        parent_prop: str
    ) -> None:
        key = (parent_uuid, parent_prop)
        self.dependencies.setdefault(key, set()).add((child_uuid, child_prop))
        log_event("dependency_registered", f"Dependency: {child_uuid}.{child_prop} depends on {parent_uuid}.{parent_prop}")

    def propagate_change(self, state: BeliefState, parent_uuid: str, parent_prop: str) -> None:
        """Decays or invalidates child properties if their parent dependency is degraded."""
        key = (parent_uuid, parent_prop)
        if key not in self.dependencies:
            return

        parent_val = state.get_property(parent_uuid, parent_prop)
        if parent_val is None:
            return

        for child_uuid, child_prop in self.dependencies[key]:
            child_val = state.get_property(child_uuid, child_prop)
            if child_val is None:
                continue

            # If parent confidence is degraded, child confidence decays proportionally
            if parent_val.confidence < 0.50:
                decayed_confidence = child_val.confidence * parent_val.confidence
                updated_child = PropertyValue(
                    value=child_val.value,
                    confidence=decayed_confidence,
                    source=parent_val.source,
                    timestamp=time.time(),
                    history=[child_val.clone()] + [h.clone() for h in child_val.history]
                )
                state.set_property(child_uuid, child_prop, updated_child)
                log_event(
                    "dependency_degraded", 
                    f"Propagated decay to {child_uuid}.{child_prop} (conf={decayed_confidence:.2f})"
                )


class BeliefEngine:
    """Belief Management System (BMS) coordinator coordinating state revisions."""

    def __init__(self, belief_state: BeliefState):
        self.state = belief_state
        self.contradiction_detector = ContradictionDetector()
        self.dependency_tracker = TruthDependencyTracker()

    def process_observation(self, observation: ObservedState) -> List[Dict[str, Any]]:
        """Processes and fuses observed state updates, returning any contradictions found."""
        detected_contradictions = []

        for entity_id, props in observation.entity_states.items():
            for prop_name, incoming_pv in props.items():
                prior_pv = self.state.get_property(entity_id, prop_name)

                if prior_pv is None:
                    # Fresh property assertion
                    self.state.set_property(entity_id, prop_name, incoming_pv.clone())
                else:
                    # Check for contradiction first
                    conflict = self.contradiction_detector.check_contradiction(
                        entity_id, prop_name, prior_pv, incoming_pv
                    )
                    if conflict:
                        detected_contradictions.append(conflict)
                        # Conflict mitigation: reduce confidence of both claims to 0.50 (uncertainty)
                        fused_pv = PropertyValue(
                            value=prior_pv.value,  # Keep prior for stability
                            confidence=0.50,
                            source=incoming_pv.source,
                            timestamp=time.time(),
                            history=[prior_pv.clone()] + [h.clone() for h in prior_pv.history]
                        )
                    else:
                        # Standard Bayesian evidence fusion
                        fused_pv = EvidenceFusion.fuse_properties(prior_pv, incoming_pv)

                    self.state.set_property(entity_id, prop_name, fused_pv)

                # Propagate dependency changes down the truth tree
                self.dependency_tracker.propagate_change(self.state, entity_id, prop_name)

        return detected_contradictions
