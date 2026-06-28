"""Tests for Phase K21.2.5: State Stabilization."""
from __future__ import annotations

import time
import pytest
from backend.core.cos.state_representation import (
    BeliefState,
    EvidenceSource,
    ObservedState,
    PropertyValue,
    State,
)


def test_evidence_source_clamping():
    src = EvidenceSource(name="camera_sensor", source_type="sensor", reliability=1.5)
    assert src.reliability == 1.0

    src_low = EvidenceSource(name="unreliable_agent", source_type="llm", reliability=-0.5)
    assert src_low.reliability == 0.0


def test_property_decay_math():
    src = EvidenceSource(name="battery_sensor", source_type="sensor", reliability=1.0)
    pv = PropertyValue(value=85, confidence=1.0, source=src, timestamp=100.0)

    # Decay over 10 seconds with lambda = 0.1
    decayed = pv.decay(lambda_val=0.1, time_elapsed=10.0)
    
    # Expected: 1.0 * exp(-0.1 * 10) = e^-1 approx 0.367879
    assert pytest.approx(decayed.confidence, 0.0001) == 0.367879
    # Original should remain unchanged (immutability)
    assert pv.confidence == 1.0


def test_property_combination():
    src_self = EvidenceSource(name="prior_estimate", source_type="simulation", reliability=0.5)
    src_new = EvidenceSource(name="user_input", source_type="user", reliability=0.8)

    pv_self = PropertyValue(value="offline", confidence=0.5, source=src_self, timestamp=10.0)
    pv_new = PropertyValue(value="online", confidence=1.0, source=src_new, timestamp=15.0)

    # Bayesian weighted combine
    # C_new = C_self + reliability_new * (C_new - C_self)
    # C_new = 0.5 + 0.8 * (1.0 - 0.5) = 0.5 + 0.4 = 0.9
    combined = pv_self.combine(pv_new)
    
    assert combined.value == "online"
    assert pytest.approx(combined.confidence, 0.0001) == 0.9
    assert len(combined.history) == 1
    assert combined.history[0].value == "offline"


def test_state_immutable_cloning_and_lineage():
    src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)
    state = ObservedState(
        state_id="state_v1",
        branch_id="main",
        timestamp=100.0,
        parent_state_id=None
    )
    pv = PropertyValue(value="idle", confidence=1.0, source=src, timestamp=100.0)
    state.set_property("entity_cpu", "status", pv)

    # Clone state and update property on clone
    cloned = state.clone()
    cloned.state_id = "state_v2"
    cloned.parent_state_id = "state_v1"

    pv_new = PropertyValue(value="busy", confidence=1.0, source=src, timestamp=105.0)
    cloned.set_property("entity_cpu", "status", pv_new)

    # Verify immutability of parent state
    assert state.get_property("entity_cpu", "status").value == "idle"
    assert cloned.get_property("entity_cpu", "status").value == "busy"
    assert cloned.parent_state_id == "state_v1"


def test_state_delta_calculation():
    src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)
    s_parent = ObservedState(state_id="s1", branch_id="main", timestamp=100.0)
    s_child = ObservedState(state_id="s2", branch_id="main", timestamp=105.0)

    pv_idle = PropertyValue(value="idle", confidence=1.0, source=src, timestamp=100.0)
    pv_busy = PropertyValue(value="busy", confidence=0.8, source=src, timestamp=105.0)

    s_parent.set_property("entity_cpu", "status", pv_idle)
    s_parent.set_property("entity_ram", "usage", PropertyValue(value=50, confidence=1.0, source=src))

    s_child.set_property("entity_cpu", "status", pv_busy)
    s_child.set_property("entity_ram", "usage", PropertyValue(value=50, confidence=1.0, source=src))

    # Calculate delta: only cpu status has changed
    delta = s_parent.calculate_delta(s_child)
    assert "entity_cpu" in delta
    assert "status" in delta["entity_cpu"]
    assert "entity_ram" not in delta

    v_parent, v_child = delta["entity_cpu"]["status"]
    assert v_parent.value == "idle"
    assert v_child.value == "busy"
    assert v_child.confidence == 0.8
