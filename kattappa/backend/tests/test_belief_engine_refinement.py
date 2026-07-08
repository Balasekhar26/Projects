"""Tests for Phase K21.3.5: Belief Engine Refinement."""
from __future__ import annotations

import time
import pytest
from backend.core.cos.belief_engine import BeliefEngine, EvidenceFusion
from backend.core.cos.state_representation import BeliefState, EvidenceSource, ObservedState, PropertyValue


def test_bayesian_likelihood_ratio_saturation():
    src = EvidenceSource(name="camera", source_type="sensor", reliability=0.8)
    pv_prior = PropertyValue(value="open", confidence=0.5, source=src, timestamp=10.0)

    # 1. First supporting observation (value="open", confidence=0.9)
    pv_incoming = PropertyValue(value="open", confidence=0.9, source=src, timestamp=11.0)
    fused_1 = EvidenceFusion.fuse_properties(pv_prior, pv_incoming)
    assert fused_1.confidence > 0.5

    # 2. Add multiple supporting observations. They should approach 1.0 asymptotically
    # without overflowing or artificially exploding
    curr = fused_1
    for _ in range(5):
        curr = EvidenceFusion.fuse_properties(curr, pv_incoming)
    assert curr.confidence < 1.0
    assert curr.confidence > 0.95


def test_recursive_dependency_propagation_and_cycles():
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)

    src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)
    
    # Establish properties
    b_state.set_property("node_A", "val", PropertyValue(value="active", confidence=0.9, source=src))
    b_state.set_property("node_B", "val", PropertyValue(value="active", confidence=0.9, source=src))
    b_state.set_property("node_C", "val", PropertyValue(value="active", confidence=0.9, source=src))

    # Dependency path: A -> B -> C -> A (Circular dependency loop)
    engine.dependency_tracker.register_dependency("node_B", "val", "node_A", "val")
    engine.dependency_tracker.register_dependency("node_C", "val", "node_B", "val")
    engine.dependency_tracker.register_dependency("node_A", "val", "node_C", "val")

    # Degrade A: ObservedState changes node_A confidence to 0.3
    obs = ObservedState(state_id="obs_1", branch_id="main", timestamp=105.0)
    obs.set_property("node_A", "val", PropertyValue(value="active", confidence=0.3, source=src))

    # Execute - should terminate safely without stack overflow recursion errors
    engine.process_observation(obs)

    # Verify min-confidence bound was recursively applied
    assert pytest.approx(b_state.get_property("node_A", "val").confidence, 0.001) == 0.794
    assert pytest.approx(b_state.get_property("node_B", "val").confidence, 0.001) == 0.794
    assert pytest.approx(b_state.get_property("node_C", "val").confidence, 0.001) == 0.794


def test_explainability_apis():
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)

    src = EvidenceSource(name="camera", source_type="sensor", reliability=0.9)
    pv = PropertyValue(value="closed", confidence=0.95, source=src, timestamp=100.0)

    # Trigger process observation to populate evidence history logs
    obs = ObservedState(state_id="obs_1", branch_id="main", timestamp=100.0)
    obs.set_property("door_sensor", "status", pv)

    engine.process_observation(obs)

    # 1. Verify why()
    why_explanation = engine.why("door_sensor", "status")
    assert "door_sensor.status = 'closed'" in why_explanation
    assert "Contributing Evidence History" in why_explanation
    assert "camera" in why_explanation

    # 2. Verify why_not()
    why_not_explanation = engine.why_not("door_sensor", "status", "open")
    assert "Refuted" in why_not_explanation
    assert "conflicts with target 'open'" in why_not_explanation
