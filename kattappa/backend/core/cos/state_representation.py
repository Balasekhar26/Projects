"""State Representation — Phase K21.2.5.

Implements the first-class PropertyValue container and State hierarchy
(ObservedState, BeliefState, PredictedState, HypotheticalState, HistoricalState),
upgraded with State lineage, immutable snapshot semantics, state delta calculators,
property history tracking, structured evidence sources, and confidence math.
"""

from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class BeliefStatus(Enum):
    """Finer-grained statuses for belief state assertions."""

    BELIEVED = "BELIEVED"
    HYPOTHESIS = "HYPOTHESIS"
    RETRACTED = "RETRACTED"
    REFUTED = "REFUTED"
    UNKNOWN = "UNKNOWN"


@dataclass
class EvidenceSource:
    """Represents the origin, reliability, and type of an observation statement."""

    name: str
    source_type: str  # E.g. 'sensor', 'user', 'llm', 'simulation'
    reliability: float = 1.0

    def __post_init__(self):
        self.reliability = max(0.0, min(1.0, self.reliability))


@dataclass
class Evidence:
    """A single piece of supporting or refuting evidence for a property state."""

    evidence_id: str
    value: Any
    confidence: float
    source: EvidenceSource
    timestamp: float
    correlation_id: Optional[str] = None
    half_life: float = 3600.0
    freshness_score: float = 1.0

    def get_freshness(self, current_time: float) -> float:
        """Returns the decayed confidence value based on elapsed time and half life."""
        elapsed = max(0.0, current_time - self.timestamp)
        decay_constant = math.log(2.0) / max(1.0, self.half_life)
        return self.confidence * math.exp(-decay_constant * elapsed)


@dataclass
class PropertyValue:
    """Explicitly represents value uncertainty, metadata, and origin."""

    value: Any
    confidence: float
    source: EvidenceSource
    timestamp: float = field(default_factory=time.time)
    variance: float = 0.0
    history: List[PropertyValue] = field(default_factory=list, repr=False)
    evidence_history: List[Evidence] = field(default_factory=list, repr=False)
    status: BeliefStatus = BeliefStatus.UNKNOWN
    version: int = 1
    revision_number: int = 0

    def __post_init__(self):
        # Enforce bounds
        self.confidence = max(0.0, min(1.0, self.confidence))
        self.variance = max(0.0, self.variance)

    def clone(self) -> PropertyValue:
        """Returns a cloned copy of the PropertyValue."""
        cloned_history = [h.clone() for h in self.history]
        cloned_evidence = [copy.deepcopy(e) for e in self.evidence_history]
        return PropertyValue(
            value=copy.deepcopy(self.value),
            confidence=self.confidence,
            source=copy.deepcopy(self.source),
            timestamp=self.timestamp,
            variance=self.variance,
            history=cloned_history,
            evidence_history=cloned_evidence,
            status=self.status,
            version=self.version,
            revision_number=self.revision_number,
        )

    def decay(self, lambda_val: float, time_elapsed: float) -> PropertyValue:
        """Applies exponential confidence decay and returns a new decayed copy."""
        decayed_confidence = self.confidence * math.exp(
            -lambda_val * max(0.0, time_elapsed)
        )
        new_val = self.clone()
        new_val.confidence = decayed_confidence
        return new_val

    def combine(self, other: PropertyValue) -> PropertyValue:
        """Fuses other PropertyValue using source-reliability weighted Bayesian update."""
        alpha = other.source.reliability
        combined_confidence = self.confidence + alpha * (
            other.confidence - self.confidence
        )

        # Build fresh Evidence entry
        new_ev = Evidence(
            evidence_id=f"ev_{int(time.time() * 1000)}",
            value=other.value,
            confidence=other.confidence,
            source=copy.deepcopy(other.source),
            timestamp=other.timestamp,
        )

        new_val = PropertyValue(
            value=copy.deepcopy(other.value),
            confidence=combined_confidence,
            source=copy.deepcopy(other.source),
            timestamp=other.timestamp,
            variance=(self.variance + other.variance) / 2.0,
            history=[self.clone()] + [h.clone() for h in self.history],
            evidence_history=[new_ev]
            + [copy.deepcopy(e) for e in self.evidence_history],
        )
        return new_val


@dataclass
class State:
    """Base class for first-class state representations in the World Model."""

    state_id: str
    branch_id: Optional[str]
    timestamp: float
    parent_state_id: Optional[str] = None
    entity_states: Dict[str, Dict[str, PropertyValue]] = field(default_factory=dict)

    def get_property(
        self, entity_uuid: str, property_name: str
    ) -> Optional[PropertyValue]:
        """Retrieve the PropertyValue for a specific entity and attribute."""
        return self.entity_states.get(entity_uuid, {}).get(property_name)

    def set_property(
        self, entity_uuid: str, property_name: str, prop_val: PropertyValue
    ) -> None:
        """Set or overwrite a property value inside this state."""
        self.entity_states.setdefault(entity_uuid, {})[property_name] = prop_val

    def clone(self) -> State:
        """Performs a deep-cloned copy of the State instance."""
        cloned_entities = {}
        for entity_id, props in self.entity_states.items():
            cloned_entities[entity_id] = {k: v.clone() for k, v in props.items()}

        # Re-instantiate exact subclass type dynamically
        return self.__class__(
            state_id=self.state_id,
            branch_id=self.branch_id,
            timestamp=self.timestamp,
            parent_state_id=self.parent_state_id,
            entity_states=cloned_entities,
        )

    def calculate_delta(
        self, other: State
    ) -> Dict[str, Dict[str, Tuple[PropertyValue, PropertyValue]]]:
        """Returns property delta differences between this state (parent) and other state."""
        delta: Dict[str, Dict[str, Tuple[PropertyValue, PropertyValue]]] = {}

        # Examine all keys present in either state
        all_entities = set(self.entity_states.keys()) | set(other.entity_states.keys())

        for entity_id in all_entities:
            self_props = self.entity_states.get(entity_id, {})
            other_props = other.entity_states.get(entity_id, {})

            all_props = set(self_props.keys()) | set(other_props.keys())
            for prop_name in all_props:
                v_self = self_props.get(prop_name)
                v_other = other_props.get(prop_name)

                # Check for modification or additions
                if (
                    v_self is None
                    or v_other is None
                    or v_self.value != v_other.value
                    or v_self.confidence != v_other.confidence
                ):
                    delta.setdefault(entity_id, {})[prop_name] = (v_self, v_other)

        return delta


# -- State Subclasses --


@dataclass
class ObservedState(State):
    """Represents raw, objectively measured inputs from sensors or tool executions."""

    pass


@dataclass
class BeliefState(State):
    """Represents the system's current unified estimate of reality."""

    pass


@dataclass
class PredictedState(State):
    """Represents forecasted outcomes on simulated future branches."""

    action_trigger_id: Optional[str] = (
        None  # Reference to action generating this prediction
    )


@dataclass
class HypotheticalState(State):
    """Represents isolated counterfactual states ('What-if' sandboxes)."""

    modification_reason: Optional[str] = None


@dataclass
class HistoricalState(State):
    """Represents frozen snapshots of past believed states for replays."""

    snapshot_version: str = "v1.0.0"
