"""Belief Engine — Phase K21.3.5.

Implements the Belief Management System (BMS) with EvidenceFusion,
ContradictionDetector, TruthDependencyTracker, and BeliefEngine,
stabilized and refined with recursive propagation, cycles detection,
explainability APIs, and sensor likelihood ratio updates.
"""

from __future__ import annotations

import copy
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.cos.state_representation import (
    BeliefState,
    Evidence,
    ObservedState,
    PropertyValue,
)
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass
class Contradiction:
    """Represents a first-class contradiction object inside the BMS."""

    contradiction_id: str
    entity_uuid: str
    property_name: str
    prior_value: Any
    prior_confidence: float
    incoming_value: Any
    incoming_confidence: float
    timestamp: float
    status: str = (
        "OPEN"  # OPEN, UNDER_REVIEW, AUTO_RESOLVED, HUMAN_RESOLVED, STALE, ARCHIVED
    )


class EvidenceFusion:
    """Computes recursive Bayesian log-odds property value combinations using Likelihood Ratios."""

    @staticmethod
    def _to_log_odds(prob: float) -> float:
        p = max(0.001, min(0.999, prob))
        return math.log(p / (1.0 - p))

    @staticmethod
    def _to_probability(log_odds: float) -> float:
        try:
            return 1.0 / (1.0 + math.exp(-log_odds))
        except OverflowError:
            return 1.0 if log_odds > 0 else 0.0

    @classmethod
    def fuse_properties(
        cls, prior: PropertyValue, incoming: PropertyValue
    ) -> PropertyValue:
        """Fuses incoming observation with prior belief using Bayesian Likelihood Ratios with Correlation Discounting."""
        R = incoming.source.reliability
        C = incoming.confidence

        # 1. Correlation Discounting
        correlation_id = None
        if incoming.evidence_history:
            correlation_id = incoming.evidence_history[0].correlation_id

        if correlation_id:
            has_correlation = any(
                e.correlation_id == correlation_id for e in prior.evidence_history
            )
            if has_correlation:
                R = R * 0.5  # Halve the reliability (diminishing returns)
                log_event(
                    "correlation_detected",
                    f"Correlated evidence source discount applied for correlation ID: {correlation_id}",
                )

        # 2. Freshness Decay of Prior Confidence
        elapsed = max(0.0, incoming.timestamp - prior.timestamp)
        # Apply standard decay over elapsed time (lambda = 0.01 per second)
        decayed_prior_conf = prior.confidence * math.exp(-0.01 * elapsed)

        p_match = R * C + (1.0 - R) * (1.0 - C)
        p_miss = (1.0 - R) * C + R * (1.0 - C)

        lo_prior = cls._to_log_odds(decayed_prior_conf)

        if prior.value == incoming.value:
            # Supporting evidence: increase confidence
            LR = p_match / max(0.001, p_miss)
            lo_new = lo_prior + math.log(max(0.01, min(100.0, LR)))
            fused_prob = cls._to_probability(lo_new)
            fused_value = prior.value
        else:
            # Opposing evidence: decrease prior confidence
            LR = p_miss / max(0.001, p_match)
            lo_new = lo_prior + math.log(max(0.01, min(100.0, LR)))
            fused_prob = cls._to_probability(lo_new)

            # If confidence drops below 0.50, we switch active value to the incoming one
            if fused_prob < 0.50:
                fused_value = incoming.value
                fused_prob = 1.0 - fused_prob
            else:
                fused_value = prior.value

        # Build fresh Evidence object
        new_ev = Evidence(
            evidence_id=f"ev_{int(time.time() * 1000)}",
            value=incoming.value,
            confidence=incoming.confidence,
            source=copy.deepcopy(incoming.source),
            timestamp=incoming.timestamp,
            correlation_id=correlation_id,
        )

        return PropertyValue(
            value=fused_value,
            confidence=fused_prob,
            source=incoming.source,
            timestamp=max(prior.timestamp, incoming.timestamp),
            variance=(prior.variance + incoming.variance) / 2.0,
            history=[prior.clone()] + [h.clone() for h in prior.history],
            evidence_history=[new_ev]
            + [copy.deepcopy(e) for e in prior.evidence_history],
        )


class ContradictionDetector:
    """Detects and registers conflicting assertions in property states."""

    def __init__(self, confidence_threshold: float = 0.60):
        self.confidence_threshold = confidence_threshold
        self.contradictions: List[Contradiction] = []

    def check_contradiction(
        self,
        entity_uuid: str,
        prop_name: str,
        prior: PropertyValue,
        incoming: PropertyValue,
    ) -> Optional[Contradiction]:
        """Identifies conflicting assertions with high confidence scores."""
        if prior.value == incoming.value:
            return None

        if (
            prior.confidence >= self.confidence_threshold
            and incoming.confidence >= self.confidence_threshold
        ):
            conflict = Contradiction(
                contradiction_id=f"conflict_{int(time.time() * 1000)}",
                entity_uuid=entity_uuid,
                property_name=prop_name,
                prior_value=prior.value,
                prior_confidence=prior.confidence,
                incoming_value=incoming.value,
                incoming_confidence=incoming.confidence,
                timestamp=time.time(),
            )
            self.contradictions.append(conflict)
            log_event(
                "contradiction_detected",
                f"Conflict on {entity_uuid}.{prop_name}: '{prior.value}' (conf={prior.confidence}) vs '{incoming.value}' (conf={incoming.confidence})",
            )
            return conflict
        return None


class TruthDependencyTracker:
    """Maintains logical truth dependency DAG between parent and child derived properties."""

    def __init__(self):
        # Maps (parent_uuid, parent_prop) -> Set of (child_uuid, child_prop)
        self.dependencies: Dict[Tuple[str, str], Set[Tuple[str, str]]] = {}

    def register_dependency(
        self, child_uuid: str, child_prop: str, parent_uuid: str, parent_prop: str
    ) -> None:
        key = (parent_uuid, parent_prop)
        self.dependencies.setdefault(key, set()).add((child_uuid, child_prop))
        log_event(
            "dependency_registered",
            f"Dependency: {child_uuid}.{child_prop} depends on {parent_uuid}.{parent_prop}",
        )

    def propagate_change(
        self,
        state: BeliefState,
        parent_uuid: str,
        parent_prop: str,
        visited: Optional[Set[Tuple[str, str]]] = None,
    ) -> None:
        """Decays or bounds child properties recursively, handling circular cycles."""
        if visited is None:
            visited = set()

        key = (parent_uuid, parent_prop)
        if key in visited:
            log_event(
                "circular_dependency_detected",
                f"Cycle hit at parent {parent_uuid}.{parent_prop}. Halting propagation.",
            )
            return

        visited.add(key)

        if key not in self.dependencies:
            return

        parent_val = state.get_property(parent_uuid, parent_prop)
        if parent_val is None:
            return

        for child_uuid, child_prop in self.dependencies[key]:
            child_val = state.get_property(child_uuid, child_prop)
            if child_val is None:
                continue

            # In K21.3.5 we bound child confidence by parent confidence: child_conf = min(child_conf, parent_conf)
            if parent_val.confidence < child_val.confidence:
                updated_confidence = min(child_val.confidence, parent_val.confidence)
                updated_child = PropertyValue(
                    value=child_val.value,
                    confidence=updated_confidence,
                    source=parent_val.source,
                    timestamp=time.time(),
                    history=[child_val.clone()]
                    + [h.clone() for h in child_val.history],
                    evidence_history=list(child_val.evidence_history),
                )
                state.set_property(child_uuid, child_prop, updated_child)
                log_event(
                    "dependency_bounded",
                    f"Propagated bound to {child_uuid}.{child_prop} (conf={updated_confidence:.2f})",
                )
                try:
                    from backend.core.knowledge_graph import KnowledgeGraph
                    kg = KnowledgeGraph.get_instance()
                    node_data = kg.get_node(child_uuid)
                    node_props = dict(node_data.get("properties", {})) if node_data else {}
                    node_props[child_prop] = child_val.value
                    kg.add_node(
                        name=child_uuid,
                        entity_type="CONCEPT",
                        node_id=child_uuid,
                        properties=node_props,
                        confidence=updated_confidence,
                        belief_state="BELIEVED" if updated_confidence >= 0.5 else "HYPOTHESIS"
                    )
                except Exception as exc:
                    logger.debug("Persisting bounded TMS property to KG failed: %s", exc)

                # Recursively propagate downstream updates
                self.propagate_change(state, child_uuid, child_prop, visited)


class BeliefEngine:
    """Belief Management System (BMS) coordinator coordinating state revisions and explanations."""

    def __init__(self, belief_state: BeliefState):
        self.state = belief_state
        self.contradiction_detector = ContradictionDetector()
        self.dependency_tracker = TruthDependencyTracker()

    def process_observation(self, observation: ObservedState) -> List[Contradiction]:
        """Processes and fuses observed state updates, returning any contradictions found."""
        detected_contradictions = []

        for entity_id, props in observation.entity_states.items():
            for prop_name, incoming_pv in props.items():
                prior_pv = self.state.get_property(entity_id, prop_name)

                if prior_pv is None:
                    # Fresh property assertion - initialize evidence history
                    fresh_pv = incoming_pv.clone()
                    fresh_ev = Evidence(
                        evidence_id=f"ev_{int(time.time() * 1000)}",
                        value=incoming_pv.value,
                        confidence=incoming_pv.confidence,
                        source=copy.deepcopy(incoming_pv.source),
                        timestamp=incoming_pv.timestamp,
                    )
                    fresh_pv.evidence_history.append(fresh_ev)
                    self.state.set_property(entity_id, prop_name, fresh_pv)
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
                            history=[prior_pv.clone()]
                            + [h.clone() for h in prior_pv.history],
                            evidence_history=list(prior_pv.evidence_history),
                        )
                    else:
                        # Standard Bayesian Likelihood Ratio evidence fusion
                        fused_pv = EvidenceFusion.fuse_properties(prior_pv, incoming_pv)

                    self.state.set_property(entity_id, prop_name, fused_pv)

                # Propagate dependency changes down the truth tree
                self.dependency_tracker.propagate_change(
                    self.state, entity_id, prop_name
                )

                # Persist updated belief state to Knowledge Graph
                try:
                    from backend.core.knowledge_graph import KnowledgeGraph
                    kg = KnowledgeGraph.get_instance()
                    node_data = kg.get_node(entity_id)
                    node_props = dict(node_data.get("properties", {})) if node_data else {}
                    
                    final_pv = self.state.get_property(entity_id, prop_name)
                    if final_pv:
                        node_props[prop_name] = final_pv.value
                        evidence_sources = [ev.source.name for ev in final_pv.evidence_history]
                        kg.add_node(
                            name=entity_id,
                            entity_type="CONCEPT",
                            node_id=entity_id,
                            properties=node_props,
                            confidence=final_pv.confidence,
                            belief_state="BELIEVED" if final_pv.confidence >= 0.5 else "HYPOTHESIS",
                            evidence=evidence_sources
                        )
                except Exception as exc:
                    logger.debug("Persisting belief engine state to KG failed: %s", exc)

        return detected_contradictions

    def why(self, entity_uuid: str, prop_name: str) -> str:
        """Provides human-readable trace explanation for the active belief state."""
        val = self.state.get_property(entity_uuid, prop_name)
        if val is None:
            return f"No active belief for {entity_uuid}.{prop_name}."

        lines = [
            f"Belief: {entity_uuid}.{prop_name} = '{val.value}'",
            f"Confidence: {val.confidence:.4f} (variance={val.variance:.2f})",
            f"Last updated: {val.timestamp}",
            "Contributing Evidence History:",
        ]
        if not val.evidence_history:
            lines.append(" - No explicit evidence recorded.")
        else:
            for i, ev in enumerate(val.evidence_history, 1):
                lines.append(
                    f" {i}. Value: '{ev.value}', Conf: {ev.confidence}, Source: {ev.source.name} ({ev.source.source_type}, reliability={ev.source.reliability})"
                )

        return "\n".join(lines)

    def why_not(self, entity_uuid: str, prop_name: str, target_value: Any) -> str:
        """Explains why the target value is refuted or not believed."""
        val = self.state.get_property(entity_uuid, prop_name)
        if val is None:
            return f"No active belief exists for {entity_uuid}.{prop_name}."

        if val.value == target_value:
            return f"Actually, Kattappa does believe {entity_uuid}.{prop_name} is '{target_value}' (conf={val.confidence:.4f})."

        return (
            f"Refuted: Active belief is '{val.value}' (conf={val.confidence:.4f}), which conflicts with target '{target_value}'.\n"
            f"The active evidence supporting '{val.value}' is stronger than any recorded evidence for '{target_value}'."
        )
