"""Unit and integration tests for Phase K21 Belief Revision Engine."""

from __future__ import annotations

import os
import tempfile
import time
import pytest

from backend.core.cos.state_representation import BeliefStatus
from backend.core.beliefs.belief import Belief
from backend.core.beliefs.coordinator import BeliefCoordinator
from backend.core.provenance.models import ProvenanceEvidenceItem
from backend.core.trust_evidence import EvidenceLevel


@pytest.fixture
def k21_test_env():
    """Provides an isolated database-backed BeliefCoordinator."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    coord = BeliefCoordinator.reset_instance(db_path=db_path)
    yield coord

    # Clean up
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


class TestBeliefRevisionK21:
    def test_source_weighting_mapping(self, k21_test_env):
        coord = k21_test_env

        # 1. peer_reviewed_paper -> REAL_WORLD
        ev_paper = ProvenanceEvidenceItem.create(
            source_id="academic_peer_reviewed_paper_01",
            evidence_level=EvidenceLevel.OPINION, # initialized low
            confidence=0.9
        )
        b_paper = coord.process_assertion("cpu_temp_paper", "idle", 35.0, ev_paper)
        # Verify that TrustEngine calculated confidence based on REAL_WORLD (high) rather than OPINION (low)
        assert b_paper.confidence > 0.80

        # 2. forum_post -> OPINION
        ev_forum = ProvenanceEvidenceItem.create(
            source_id="reddit_forum_post_xyz",
            evidence_level=EvidenceLevel.REAL_WORLD, # initialized high
            confidence=0.9
        )
        b_forum = coord.process_assertion("cpu_temp_forum", "idle", 35.0, ev_forum)
        # Score should be much lower (OPINION = 0.0 base normalized)
        assert b_forum.confidence < 0.50

    def test_temporal_coexistence(self, k21_test_env):
        coord = k21_test_env

        # First claim with temporal_scope = 2020
        ev_2020 = ProvenanceEvidenceItem.create(
            source_id="sensor_01",
            evidence_level=EvidenceLevel.REAL_WORLD,
            confidence=0.9,
            metadata={"temporal_scope": "2020"}
        )
        b_2020 = coord.process_assertion("company_01", "ceo", "Balu", ev_2020)

        # Contradicting claim with temporal_scope = 2026
        ev_2026 = ProvenanceEvidenceItem.create(
            source_id="sensor_01",
            evidence_level=EvidenceLevel.REAL_WORLD,
            confidence=0.9,
            metadata={"temporal_scope": "2026"}
        )
        b_2026 = coord.process_assertion("company_01", "ceo", "Antigravity", ev_2026)

        # Both beliefs must co-exist actively without conflicts
        conflicts = coord.contradictions.get_open_conflicts()
        assert len(conflicts) == 0

        # Retrieve both beliefs
        beliefs = coord.store.get_beliefs_for_claim("company_01", "ceo")
        assert len(beliefs) == 2
        assert any(b.claim_value == "Balu" for b in beliefs)
        assert any(b.claim_value == "Antigravity" for b in beliefs)

    def test_gradual_confidence_updates(self, k21_test_env):
        coord = k21_test_env

        ev = ProvenanceEvidenceItem.create(
            source_id="sensor_01",
            evidence_level=EvidenceLevel.REAL_WORLD,
            confidence=0.8
        )
        
        # 1. Save initial belief
        b1 = coord.process_assertion("room_1", "temp", 22.0, ev)
        initial_conf = b1.confidence

        # 2. Assertion of same value updates gradually
        # target confidence = 0.5, current = 1.0 (REAL_WORLD normalized is 1.0)
        # new = current * 0.7 + target * 0.3
        b2 = coord.process_assertion("room_1", "temp", 22.0, ev, learning_rate=0.3)
        
        assert b2.version == 2
        assert b2.confidence == pytest.approx(initial_conf * 0.7 + b1.confidence * 0.3, rel=1e-2)

    def test_contradiction_decay_and_history(self, k21_test_env):
        coord = k21_test_env

        ev_weak = ProvenanceEvidenceItem.create(
            source_id="reddit_forum_post",
            evidence_level=EvidenceLevel.OPINION,
            confidence=0.4
        )
        ev_strong = ProvenanceEvidenceItem.create(
            source_id="academic_peer_reviewed_paper",
            evidence_level=EvidenceLevel.REAL_WORLD,
            confidence=0.9
        )

        # 1. Assert weak belief
        b1 = coord.process_assertion("host_1", "load", "low", ev_weak)
        weak_initial_conf = b1.confidence

        # 2. Assert conflicting strong belief
        b2 = coord.process_assertion("host_1", "load", "high", ev_strong)

        # Prior weak belief should be updated to REFUTED and decayed by 50%
        prior_updated = coord.store.get_belief(b1.belief_id)
        assert prior_updated.truth_status == BeliefStatus.REFUTED
        assert prior_updated.confidence == pytest.approx(weak_initial_conf * 0.5)

        # Historical preservation check: check history database
        history = coord.store.get_belief_history(b1.belief_id)
        assert len(history) >= 2
        # First entry: original active belief
        assert history[0]["truth_status"] in ("BELIEVED", "HYPOTHESIS")
        # Second entry: refuted revision
        assert history[1]["truth_status"] == "REFUTED"
