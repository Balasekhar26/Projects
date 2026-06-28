"""State Representation — Phase K21.2.

Implements the first-class PropertyValue container and State hierarchy
(ObservedState, BeliefState, PredictedState, HypotheticalState, HistoricalState).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PropertyValue:
    """Explicitly represents value uncertainty, metadata, and origin."""
    value: Any
    confidence: float
    source: str
    timestamp: float = field(default_factory=time.time)
    variance: float = 0.0

    def __post_init__(self):
        # Enforce bounds
        self.confidence = max(0.0, min(1.0, self.confidence))
        self.variance = max(0.0, self.variance)


@dataclass
class State:
    """Base class for first-class state representations in the World Model."""
    state_id: str
    branch_id: Optional[str]
    timestamp: float
    entity_states: Dict[str, Dict[str, PropertyValue]] = field(default_factory=dict)
    
    def get_property(self, entity_uuid: str, property_name: str) -> Optional[PropertyValue]:
        """Retrieve the PropertyValue for a specific entity and attribute."""
        return self.entity_states.get(entity_uuid, {}).get(property_name)

    def set_property(self, entity_uuid: str, property_name: str, prop_val: PropertyValue) -> None:
        """Set or overwrite a property value inside this state."""
        self.entity_states.setdefault(entity_uuid, {})[property_name] = prop_val


# -- State Subclasses --

@dataclass
class ObservedState(State):
    """Represents raw, objectively measured inputs from sensors or tool executions."""
    def __post_init__(self):
        # Observed states are historical anchors; can check validation invariants
        pass


@dataclass
class BeliefState(State):
    """Represents the system's current unified estimate of reality."""
    def __post_init__(self):
        pass


@dataclass
class PredictedState(State):
    """Represents forecasted outcomes on simulated future branches."""
    action_trigger_id: Optional[str] = None  # Reference to action generating this prediction
    
    def __post_init__(self):
        pass


@dataclass
class HypotheticalState(State):
    """Represents isolated counterfactual states ('What-if' sandboxes)."""
    modification_reason: Optional[str] = None
    
    def __post_init__(self):
        pass


@dataclass
class HistoricalState(State):
    """Represents frozen snapshots of past believed states for replays."""
    snapshot_version: str = "v1.0.0"
    
    def __post_init__(self):
        pass
