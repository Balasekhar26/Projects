"""Tests for Phase K21.2: State Representation."""
from __future__ import annotations

import time
import pytest
from backend.core.cos.state_representation import (
    BeliefState,
    EvidenceSource,
    HistoricalState,
    HypotheticalState,
    ObservedState,
    PredictedState,
    PropertyValue,
)


def test_property_value_clamping():
    src = EvidenceSource(name="test", source_type="sensor")
    # Verify confidence clamping bounds
    pv_high = PropertyValue(value="online", confidence=1.5, source=src)
    assert pv_high.confidence == 1.0

    pv_low = PropertyValue(value="offline", confidence=-0.3, source=src)
    assert pv_low.confidence == 0.0

    pv_valid = PropertyValue(value=80, confidence=0.82, source=src, variance=2.5)
    assert pv_valid.confidence == 0.82
    assert pv_valid.variance == 2.5
    assert pv_valid.timestamp > 0


def test_state_set_and_get():
    # Create a state
    state = BeliefState(state_id="state_1", branch_id="main", timestamp=100.0)
    src = EvidenceSource(name="system", source_type="sensor")
    
    # Define property value
    pv = PropertyValue(value="3.5GHz", confidence=0.9, source=src, timestamp=100.0)
    
    # Set property
    state.set_property("entity_cpu", "frequency", pv)
    
    # Get property
    retrieved = state.get_property("entity_cpu", "frequency")
    assert retrieved is not None
    assert retrieved.value == "3.5GHz"
    assert retrieved.confidence == 0.9
    assert retrieved.source.name == "system"
    assert retrieved.timestamp == 100.0

    # Get non-existent
    assert state.get_property("entity_cpu", "cores") is None
    assert state.get_property("non_existent", "frequency") is None


def test_state_subclasses():
    # Observed State
    obs = ObservedState(state_id="obs_1", branch_id=None, timestamp=50.0)
    assert obs.branch_id is None
    
    # Predicted State with trigger
    pred = PredictedState(
        state_id="pred_1", 
        branch_id="branch_a", 
        timestamp=60.0,
        action_trigger_id="action_compile"
    )
    assert pred.branch_id == "branch_a"
    assert pred.action_trigger_id == "action_compile"

    # Hypothetical State with reason
    hyp = HypotheticalState(
        state_id="hyp_1",
        branch_id="branch_b",
        timestamp=70.0,
        modification_reason="Suppose CPU fails"
    )
    assert hyp.modification_reason == "Suppose CPU fails"

    # Historical State with version
    hist = HistoricalState(
        state_id="hist_1",
        branch_id=None,
        timestamp=10.0,
        snapshot_version="v2.0.0"
    )
    assert hist.snapshot_version == "v2.0.0"
