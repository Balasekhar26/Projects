"""Integration and unit tests for Program 5B: Belief Management & Truth Maintenance Layer.
"""
from __future__ import annotations

import os
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from backend.core.cos.state_representation import BeliefStatus
from backend.core.beliefs.belief import Belief, Justification, BeliefDependency
from backend.core.beliefs.coordinator import BeliefCoordinator
from backend.core.provenance.models import ProvenanceEvidenceItem
from backend.core.trust_evidence import EvidenceLevel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def beliefs_test_env():
    """Provides an isolated database-backed BeliefCoordinator."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    coord = BeliefCoordinator.reset_instance(db_path=db_path)

    yield coord

    # Clean up test database
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_belief_store_crud_and_versioning(beliefs_test_env):
    """Verifies that beliefs are correctly saved, retrieved, and revisioned in the store."""
    coord = beliefs_test_env
    store = coord.store

    # Create dummy evidence item
    ev = ProvenanceEvidenceItem.create(
        source_id="src_user",
        evidence_level=EvidenceLevel.REAL_WORLD,
        confidence=1.0,
    )

    # 1. Process initial assertion
    b1 = coord.process_assertion(
        subject="host_01",
        predicate="status",
        value="active",
        evidence=ev,
        rationale="User reported active status",
    )
    assert b1.version == 1
    assert b1.claim_value == "active"
    assert b1.truth_status == BeliefStatus.BELIEVED

    # 2. Update same claim with same value (should increment version to 2)
    b2 = coord.process_assertion(
        subject="host_01",
        predicate="status",
        value="active",
        evidence=ev,
        rationale="Update from user",
    )
    assert b2.version == 2
    assert b2.claim_value == "active"

    # 3. Retrieve history log
    history = store.get_belief_history(b1.belief_id)
    assert len(history) == 2
    assert history[0]["claim_value"] == "active"
    assert history[1]["claim_value"] == "active"



def test_dependency_propagation(beliefs_test_env):
    """Tests downstream belief confidence boundary propagation inside the DAG."""
    coord = beliefs_test_env

    ev = ProvenanceEvidenceItem.create(
        source_id="src_system",
        evidence_level=EvidenceLevel.REAL_WORLD,
        confidence=1.0,
    )

    # Parent belief (power grid status) — High confidence (1.0)
    parent = coord.process_assertion("grid_power", "available", True, ev)

    # Child belief (server status) — initially depends on grid power
    child = coord.process_assertion(
        subject="server_01",
        predicate="online",
        value=True,
        evidence=ev,
        dependencies=[parent.belief_id],
    )

    # Initially, child is unconstrained (both at 1.0 confidence)
    assert child.confidence == 1.0

    # Degrade parent confidence to 0.4 (low confidence) manually
    parent_degraded = Belief(
        belief_id=parent.belief_id,
        claim_subject=parent.claim_subject,
        claim_predicate=parent.claim_predicate,
        claim_value=parent.claim_value,
        confidence=0.4,
        truth_status=BeliefStatus.HYPOTHESIS,
        source_ids=parent.source_ids,
        evidence_ids=parent.evidence_ids,
        created_at=parent.created_at,
        updated_at=time.time(),
        valid_from=parent.valid_from,
        valid_until=parent.valid_until,
        version=parent.version + 1,
        metadata=parent.metadata,
    )
    coord.store.save_belief(parent_degraded)
    coord.graph.propagate_confidence(parent_degraded)

    # Child confidence must be recursively bounded to min(child_conf, parent_conf) -> 0.4
    child_updated = coord.store.get_belief(child.belief_id)
    assert child_updated.confidence == 0.4
    assert child_updated.version > 1


def test_circular_dependency_prevention(beliefs_test_env):
    """Verifies that establishing a cyclic relationship triggers a ValueError."""
    coord = beliefs_test_env

    # Setup parent/child beliefs
    b1 = coord.store.save_belief(Belief.create("A", "x", 1, 0.8))
    b2 = coord.store.save_belief(Belief.create("B", "x", 2, 0.8))

    # A -> B (B depends on A)
    coord.graph.add_dependency("bel_A", "bel_B")
    
    # B -> A (A depends on B) -> Should fail with ValueError
    with pytest.raises(ValueError):
        coord.graph.add_dependency("bel_B", "bel_A")


def test_contradiction_detection_and_resolution(beliefs_test_env):
    """Verifies that claim collisions generate OPEN conflicts and resolve based on confidence."""
    coord = beliefs_test_env

    ev_weak = ProvenanceEvidenceItem.create(
        source_id="src_user",
        evidence_level=EvidenceLevel.OPINION,
        confidence=0.4,
    )
    ev_strong = ProvenanceEvidenceItem.create(
        source_id="src_sensor",
        evidence_level=EvidenceLevel.REAL_WORLD,
        confidence=0.95,
    )

    # 1. Assert initial weak belief
    coord.process_assertion("room_101", "occupied", True, ev_weak)

    # 2. Assert conflicting strong belief (different value, higher confidence)
    coord.process_assertion("room_101", "occupied", False, ev_strong)

    # 3. Retrieve open conflicts
    conflicts = coord.contradictions.get_open_conflicts()
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.subject == "room_101"
    assert c.predicate == "occupied"
    assert c.status == "OPEN"

    # Active belief should be resolved in favor of stronger one (False)
    active = coord.store.get_belief_by_claim("room_101", "occupied")
    assert active.claim_value is False
    assert active.truth_status == BeliefStatus.BELIEVED



def test_explanation_engine_trace(beliefs_test_env):
    """Tests compiling human-readable justifications and explanations."""
    coord = beliefs_test_env

    ev = ProvenanceEvidenceItem.create(
        source_id="src_tester",
        evidence_level=EvidenceLevel.TEST_RESULT,
        confidence=0.9,
    )

    b = coord.process_assertion(
        subject="assertion_01",
        predicate="passed",
        value=True,
        evidence=ev,
        rationale="Manual unit test executed successfully",
    )

    explanation = coord.explanations.explain_belief(b.belief_id)
    assert "assertion_01.passed = 'True'" in explanation
    assert "src_tester" in explanation
    assert "TEST_RESULT" in explanation

    why_not = coord.explanations.explain_why_not("assertion_01", "passed", False)
    assert "Refuted" in why_not
