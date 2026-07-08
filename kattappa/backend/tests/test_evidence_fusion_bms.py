"""Tests for Phase K21.4: Evidence Fusion."""
from __future__ import annotations

import time
import pytest
from backend.core.cos.belief_engine import BeliefEngine, EvidenceFusion
from backend.core.cos.state_representation import BeliefState, Evidence, EvidenceSource, ObservedState, PropertyValue


def test_correlation_discounting():
    src = EvidenceSource(name="camera_feed", source_type="sensor", reliability=0.8)
    pv_prior = PropertyValue(value="open", confidence=0.5, source=src, timestamp=10.0)

    # 1. First observation with correlation ID
    ev_1 = Evidence(evidence_id="e1", value="open", confidence=0.9, source=src, timestamp=10.0, correlation_id="cluster_A")
    pv_prior.evidence_history.append(ev_1)

    # 2. Second observation with SAME correlation ID
    # Since it is correlated, reliability should get discounted, resulting in lower confidence gain
    pv_correlated = PropertyValue(value="open", confidence=0.9, source=src, timestamp=11.0)
    ev_2 = Evidence(evidence_id="e2", value="open", confidence=0.9, source=src, timestamp=11.0, correlation_id="cluster_A")
    pv_correlated.evidence_history.append(ev_2)

    # Fuse and verify that the reliability discount is applied
    fused = EvidenceFusion.fuse_properties(pv_prior, pv_correlated)
    
    # 3. Repeat with DIFFERENT correlation ID (should not be discounted, resulting in higher confidence)
    pv_independent = PropertyValue(value="open", confidence=0.9, source=src, timestamp=11.0)
    ev_3 = Evidence(evidence_id="e3", value="open", confidence=0.9, source=src, timestamp=11.0, correlation_id="cluster_B")
    pv_independent.evidence_history.append(ev_3)
    
    fused_indep = EvidenceFusion.fuse_properties(pv_prior, pv_independent)
    
    # Independent evidence should yield strictly higher confidence than correlated/discounted evidence
    assert fused_indep.confidence > fused.confidence


def test_evidence_freshness_decay():
    src = EvidenceSource(name="sensor", source_type="sensor", reliability=0.8)
    pv_prior = PropertyValue(value="open", confidence=0.9, source=src, timestamp=100.0)

    # Fast incoming observation at 101s (almost no decay)
    pv_fast = PropertyValue(value="open", confidence=0.9, source=src, timestamp=101.0)
    fused_fast = EvidenceFusion.fuse_properties(pv_prior, pv_fast)

    # Stale observation at 500s (prior confidence decays significantly before fusion)
    pv_slow = PropertyValue(value="open", confidence=0.9, source=src, timestamp=500.0)
    fused_slow = EvidenceFusion.fuse_properties(pv_prior, pv_slow)

    # Decayed prior should yield lower combined posterior confidence
    assert fused_fast.confidence > fused_slow.confidence


def test_contradiction_lifecycle_status():
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)

    src_user = EvidenceSource(name="user", source_type="user", reliability=0.9)
    src_tool = EvidenceSource(name="tool", source_type="sensor", reliability=0.8)

    pv_prior = PropertyValue(value="online", confidence=0.9, source=src_user, timestamp=100.0)
    b_state.set_property("system_host", "status", pv_prior)

    obs = ObservedState(state_id="obs_1", branch_id="main", timestamp=105.0)
    pv_obs = PropertyValue(value="offline", confidence=0.95, source=src_tool, timestamp=105.0)
    obs.set_property("system_host", "status", pv_obs)

    conflicts = engine.process_observation(obs)
    assert len(conflicts) == 1
    # Check first-class Contradiction status defaults to OPEN
    assert conflicts[0].status == "OPEN"
