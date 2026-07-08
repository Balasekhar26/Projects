"""Tests for Phase K21.6: Truth Maintenance System (TMS)."""
from __future__ import annotations

import time
import pytest
from backend.core.cos.belief_engine import BeliefEngine
from backend.core.cos.belief_revision import BeliefRevisionEngine
from backend.core.cos.state_representation import BeliefState, BeliefStatus, EvidenceSource, PropertyValue
from backend.core.cos.tms import Justification, JustificationManager, TruthMaintenanceSystem


def test_expand_insert_only_constraint():
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)
    rev_engine = BeliefRevisionEngine(engine)

    src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)
    pv = PropertyValue(value="active", confidence=0.9, source=src)

    # First expand succeeds
    rev_engine.expand("host_cpu", "status", pv, "initial CPU status")

    # Second expand on the same property raises ValueError
    with pytest.raises(ValueError, match="already exists. Cannot expand"):
        rev_engine.expand("host_cpu", "status", pv, "duplicate CPU status")


def test_belief_status_transitions():
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)
    rev_engine = BeliefRevisionEngine(engine)

    src = EvidenceSource(name="system", source_type="sensor", reliability=0.9)
    pv = PropertyValue(value="online", confidence=0.95, source=src)

    # 1. Expand -> Status = BELIEVED
    rev_engine.expand("host_cpu", "status", pv)
    assert b_state.get_property("host_cpu", "status").status == BeliefStatus.BELIEVED

    # 2. Revise conflict -> Status = HYPOTHESIS
    pv_conflict = PropertyValue(value="offline", confidence=0.95, source=src)
    rev_engine.revise("host_cpu", "status", pv_conflict, "ev_conflict")
    assert b_state.get_property("host_cpu", "status").status == BeliefStatus.HYPOTHESIS

    # 3. Contract -> Status = RETRACTED
    rev_engine.contract("host_cpu", "status")
    assert b_state.get_property("host_cpu", "status").status == BeliefStatus.RETRACTED


def test_tms_propagation_justification_loss():
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)
    rev_engine = BeliefRevisionEngine(engine)

    src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)
    pv_parent = PropertyValue(value="active", confidence=0.9, source=src)
    pv_child = PropertyValue(value="running", confidence=0.85, source=src)

    # Set dependencies
    engine.dependency_tracker.register_dependency("host_cpu", "load_balancer", "host_cpu", "power")

    # Expand both
    rev_engine.expand("host_cpu", "power", pv_parent)
    rev_engine.expand("host_cpu", "load_balancer", pv_child)

    # Contract parent: power belief is retracted
    rev_engine.contract("host_cpu", "power", "Retracting power belief")

    # Verify parent is retracted
    assert b_state.get_property("host_cpu", "power").status == BeliefStatus.RETRACTED

    # Verify that child justification is OUT and status is UNKNOWN with confidence 0.0
    child_pv = b_state.get_property("host_cpu", "load_balancer")
    assert child_pv.status == BeliefStatus.UNKNOWN
    assert child_pv.confidence == 0.0
    assert rev_engine.tms.justification_manager.get_justification("host_cpu", "load_balancer").status == "OUT"


def test_tms_transaction_rollback():
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)
    rev_engine = BeliefRevisionEngine(engine)

    src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)
    pv = PropertyValue(value="online", confidence=0.9, source=src)

    # Expand initial state
    rev_engine.expand("host_cpu", "status", pv)

    # Start transaction
    tms = rev_engine.tms
    tms.begin(b_state)

    # Revise in transaction
    pv_new = PropertyValue(value="offline", confidence=0.95, source=src)
    rev_engine.revise("host_cpu", "status", pv_new, "ev_new")

    # Verify confidence dropped to 0.5 during transaction (due to contradiction mitigation)
    assert b_state.get_property("host_cpu", "status").confidence == 0.50
    assert b_state.get_property("host_cpu", "status").value == "online"

    # Rollback
    tms.rollback(b_state)

    # Verify original state was completely restored
    assert b_state.get_property("host_cpu", "status").value == "online"
    assert b_state.get_property("host_cpu", "status").confidence == 0.90
    assert b_state.get_property("host_cpu", "status").status == BeliefStatus.BELIEVED
