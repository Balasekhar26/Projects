"""Tests for Phase K21.5: Belief Revision."""
from __future__ import annotations

import time
import pytest
from backend.core.cos.belief_engine import BeliefEngine
from backend.core.cos.belief_revision import BeliefRevisionEngine, RevisionRecord
from backend.core.cos.state_representation import BeliefState, EvidenceSource, PropertyValue


def test_agm_expansion():
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)
    rev_engine = BeliefRevisionEngine(engine)

    src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)
    pv = PropertyValue(value="online", confidence=0.9, source=src, timestamp=100.0)

    # Execute expansion
    record = rev_engine.expand("host_cpu", "status", pv, "CPU online observation")
    
    assert record.operator == "EXPANSION"
    assert record.entity_uuid == "host_cpu"
    assert record.property_name == "status"
    assert record.new_value == "online"
    assert b_state.get_property("host_cpu", "status").value == "online"


def test_agm_revision_conflict():
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)
    rev_engine = BeliefRevisionEngine(engine)

    src = EvidenceSource(name="system", source_type="sensor", reliability=0.9)
    pv_prior = PropertyValue(value="online", confidence=0.95, source=src, timestamp=100.0)
    b_state.set_property("host_cpu", "status", pv_prior)

    # Conflicting observation with high confidence (triggering contradiction)
    pv_incoming = PropertyValue(value="offline", confidence=0.95, source=src, timestamp=105.0)

    # Execute revision
    record = rev_engine.revise("host_cpu", "status", pv_incoming, "ev_conflict", "Host offline update")
    
    assert record.operator == "REVISION"
    # Contradiction mitigation should decrease confidence to 0.50
    assert b_state.get_property("host_cpu", "status").confidence == 0.50


def test_agm_contraction_propagation():
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)
    rev_engine = BeliefRevisionEngine(engine)

    src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)
    
    # Establish parent and child states
    pv_parent = PropertyValue(value="active", confidence=0.9, source=src)
    pv_child = PropertyValue(value="running", confidence=0.85, source=src)
    b_state.set_property("host_cpu", "power", pv_parent)
    b_state.set_property("host_cpu", "load_balancer", pv_child)

    # Register dependency: load_balancer status depends on power status
    engine.dependency_tracker.register_dependency("host_cpu", "load_balancer", "host_cpu", "power")

    # Contract parent status: power belief is retracted
    record = rev_engine.contract("host_cpu", "power", "Retracting power source belief")
    
    assert record.operator == "CONTRACTION"
    assert record.entity_uuid == "host_cpu"
    assert record.property_name == "power"

    # Verify that parent confidence degraded to 0.0
    assert b_state.get_property("host_cpu", "power").confidence == 0.0
    # Verify that child load_balancer confidence decayed/bounded to 0.0 proportionally
    assert b_state.get_property("host_cpu", "load_balancer").confidence == 0.0
