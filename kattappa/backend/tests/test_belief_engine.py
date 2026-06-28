"""Tests for Phase K21.3: Belief Engine."""
from __future__ import annotations

import time
import pytest
from backend.core.cos.belief_engine import BeliefEngine, EvidenceFusion
from backend.core.cos.state_representation import BeliefState, EvidenceSource, ObservedState, PropertyValue


def test_evidence_fusion_strengthening():
    src_1 = EvidenceSource(name="camera", source_type="sensor", reliability=0.8)
    src_2 = EvidenceSource(name="lidar", source_type="sensor", reliability=0.9)

    pv_1 = PropertyValue(value="open", confidence=0.7, source=src_1, timestamp=10.0)
    pv_2 = PropertyValue(value="open", confidence=0.8, source=src_2, timestamp=12.0)

    # When values are identical, confidence should be strengthened by log-odds addition
    fused = EvidenceFusion.fuse_properties(pv_1, pv_2)
    assert fused.value == "open"
    assert fused.confidence > 0.8  # Fusing two supporting evidences increases belief confidence
    assert len(fused.history) == 1
    assert fused.history[0].confidence == 0.7


def test_contradiction_detection_and_mitigation():
    # Setup state
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)

    src_user = EvidenceSource(name="user", source_type="user", reliability=0.9)
    src_tool = EvidenceSource(name="tool", source_type="sensor", reliability=0.8)

    pv_prior = PropertyValue(value="online", confidence=0.9, source=src_user, timestamp=100.0)
    b_state.set_property("system_host", "status", pv_prior)

    # Incoming contradicting observation with high confidence
    obs = ObservedState(state_id="obs_1", branch_id="main", timestamp=105.0)
    pv_obs = PropertyValue(value="offline", confidence=0.95, source=src_tool, timestamp=105.0)
    obs.set_property("system_host", "status", pv_obs)

    conflicts = engine.process_observation(obs)
    assert len(conflicts) == 1
    assert conflicts[0].property_name == "status"
    assert conflicts[0].prior_value == "online"
    assert conflicts[0].incoming_value == "offline"

    # BeliefEngine mitigation should degrade confidence to 0.50 (uncertainty)
    fused = b_state.get_property("system_host", "status")
    assert fused.confidence == 0.50


def test_truth_dependency_propagation():
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)

    src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)
    
    # Set parent and child states
    pv_parent = PropertyValue(value="active", confidence=0.9, source=src)
    pv_child = PropertyValue(value="running", confidence=0.85, source=src)

    b_state.set_property("host_cpu", "power", pv_parent)
    b_state.set_property("host_cpu", "load_balancer", pv_child)

    # Register dependency: load_balancer status depends on power status
    engine.dependency_tracker.register_dependency(
        child_uuid="host_cpu",
        child_prop="load_balancer",
        parent_uuid="host_cpu",
        parent_prop="power"
    )

    # Degrading parent power state
    obs = ObservedState(state_id="obs_1", branch_id="main", timestamp=105.0)
    pv_degraded_parent = PropertyValue(value="active", confidence=0.01, source=src)
    obs.set_property("host_cpu", "power", pv_degraded_parent)

    engine.process_observation(obs)

    # Verify that child load_balancer confidence decayed proportionally
    child_fused = b_state.get_property("host_cpu", "load_balancer")
    # Expected child confidence bounded by parent fused confidence (approx 0.08333333333333336)
    assert pytest.approx(child_fused.confidence, 0.001) == 0.0833
