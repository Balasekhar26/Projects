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
    
    # Establish properties with explicit timestamps to avoid time.time() non-determinism
    b_state.set_property("node_A", "val", PropertyValue(value="active", confidence=0.9, source=src, timestamp=100.0))
    b_state.set_property("node_B", "val", PropertyValue(value="active", confidence=0.9, source=src, timestamp=100.0))
    b_state.set_property("node_C", "val", PropertyValue(value="active", confidence=0.9, source=src, timestamp=100.0))

    # Dependency path: A -> B -> C -> A (Circular dependency loop)
    engine.dependency_tracker.register_dependency("node_B", "val", "node_A", "val")
    engine.dependency_tracker.register_dependency("node_C", "val", "node_B", "val")
    engine.dependency_tracker.register_dependency("node_A", "val", "node_C", "val")

    # Degrade A: ObservedState changes node_A confidence to 0.3
    obs = ObservedState(state_id="obs_1", branch_id="main", timestamp=105.0)
    obs.set_property("node_A", "val", PropertyValue(value="active", confidence=0.3, source=src, timestamp=105.0))

    # Execute - should terminate safely without stack overflow recursion errors
    engine.process_observation(obs)

    # Verify convergence: the min-confidence bound was recursively applied.
    # The exact fused value depends on Bayesian log-odds fusion with freshness decay.
    # With explicit timestamps (elapsed=5s, decay_lambda=0.01): decayed_prior = 0.9 * exp(-0.05) ≈ 0.8561
    # All three nodes should converge to the same bounded confidence.
    result_a = b_state.get_property("node_A", "val").confidence
    result_b = b_state.get_property("node_B", "val").confidence
    result_c = b_state.get_property("node_C", "val").confidence

    # All nodes should converge to the same value (cycle-safe propagation)
    assert result_a == pytest.approx(result_b, abs=0.001)
    assert result_b == pytest.approx(result_c, abs=0.001)
    # The fused confidence should be between the degraded (0.3) and original (0.9) values
    assert 0.3 < result_a < 0.9


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


def test_two_node_cycle_a_b_a():
    """Verify 2-node cycle A -> B -> A converges deterministically."""
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)
    src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)

    b_state.set_property("A", "v", PropertyValue(value="on", confidence=0.9, source=src, timestamp=100.0))
    b_state.set_property("B", "v", PropertyValue(value="on", confidence=0.9, source=src, timestamp=100.0))

    engine.dependency_tracker.register_dependency("B", "v", "A", "v")
    engine.dependency_tracker.register_dependency("A", "v", "B", "v")

    obs = ObservedState(state_id="o1", branch_id="main", timestamp=105.0)
    obs.set_property("A", "v", PropertyValue(value="on", confidence=0.2, source=src, timestamp=105.0))
    engine.process_observation(obs)

    val_a = b_state.get_property("A", "v").confidence
    val_b = b_state.get_property("B", "v").confidence
    assert val_a == pytest.approx(val_b, abs=0.001)


def test_cycle_registration_permutations():
    """Verify all 6 registration order permutations of 3-node cycle yield identical results."""
    import itertools
    edges = [
        ("node_B", "val", "node_A", "val"),
        ("node_C", "val", "node_B", "val"),
        ("node_A", "val", "node_C", "val"),
    ]
    results = []

    for perm in itertools.permutations(edges):
        b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
        engine = BeliefEngine(b_state)
        src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)

        b_state.set_property("node_A", "val", PropertyValue(value="active", confidence=0.9, source=src, timestamp=100.0))
        b_state.set_property("node_B", "val", PropertyValue(value="active", confidence=0.9, source=src, timestamp=100.0))
        b_state.set_property("node_C", "val", PropertyValue(value="active", confidence=0.9, source=src, timestamp=100.0))

        for child_u, child_p, parent_u, parent_p in perm:
            engine.dependency_tracker.register_dependency(child_u, child_p, parent_u, parent_p)

        obs = ObservedState(state_id="obs_1", branch_id="main", timestamp=105.0)
        obs.set_property("node_A", "val", PropertyValue(value="active", confidence=0.3, source=src, timestamp=105.0))
        engine.process_observation(obs)

        res_a = b_state.get_property("node_A", "val").confidence
        res_b = b_state.get_property("node_B", "val").confidence
        res_c = b_state.get_property("node_C", "val").confidence
        results.append((res_a, res_b, res_c))

    # All permutations must yield identical results
    first = results[0]
    for r in results[1:]:
        assert r[0] == pytest.approx(first[0], abs=1e-5)
        assert r[1] == pytest.approx(first[1], abs=1e-5)
        assert r[2] == pytest.approx(first[2], abs=1e-5)


def test_cycle_with_outgoing_and_incoming_dependencies():
    """Verify cycle with incoming node IN -> A -> B -> A -> OUT correctly bounds OUT."""
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)
    src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)

    b_state.set_property("IN", "v", PropertyValue(value="active", confidence=0.4, source=src, timestamp=100.0))
    b_state.set_property("A", "v", PropertyValue(value="active", confidence=0.9, source=src, timestamp=100.0))
    b_state.set_property("B", "v", PropertyValue(value="active", confidence=0.9, source=src, timestamp=100.0))
    b_state.set_property("OUT", "v", PropertyValue(value="active", confidence=0.95, source=src, timestamp=100.0))

    # IN -> A -> B -> A and B -> OUT
    engine.dependency_tracker.register_dependency("A", "v", "IN", "v")
    engine.dependency_tracker.register_dependency("B", "v", "A", "v")
    engine.dependency_tracker.register_dependency("A", "v", "B", "v")
    engine.dependency_tracker.register_dependency("OUT", "v", "B", "v")

    # Propagate from IN (conf=0.4)
    engine.dependency_tracker.propagate_change(b_state, "IN", "v")

    # OUT must be bounded down to 0.4 via the cycle
    assert b_state.get_property("OUT", "v").confidence <= 0.4


def test_two_connected_cycles():
    """Verify Cycle 1 (A<->B) connected to Cycle 2 (C<->D) propagates correctly."""
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)
    src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)

    b_state.set_property("A", "v", PropertyValue(value="active", confidence=0.9, source=src, timestamp=100.0))
    b_state.set_property("B", "v", PropertyValue(value="active", confidence=0.9, source=src, timestamp=100.0))
    b_state.set_property("C", "v", PropertyValue(value="active", confidence=0.9, source=src, timestamp=100.0))
    b_state.set_property("D", "v", PropertyValue(value="active", confidence=0.9, source=src, timestamp=100.0))

    # Cycle 1: A <-> B, B -> C, Cycle 2: C <-> D
    engine.dependency_tracker.register_dependency("B", "v", "A", "v")
    engine.dependency_tracker.register_dependency("A", "v", "B", "v")
    engine.dependency_tracker.register_dependency("C", "v", "B", "v")
    engine.dependency_tracker.register_dependency("D", "v", "C", "v")
    engine.dependency_tracker.register_dependency("C", "v", "D", "v")

    # Degrade A to 0.2
    obs = ObservedState(state_id="o1", branch_id="main", timestamp=105.0)
    obs.set_property("A", "v", PropertyValue(value="active", confidence=0.2, source=src, timestamp=105.0))
    engine.process_observation(obs)

    # All nodes in both cycles should be bounded
    val_d = b_state.get_property("D", "v").confidence
    assert val_d < 0.9


def test_repeated_propagation_idempotency():
    """Verify calling propagate_change multiple times is idempotent."""
    b_state = BeliefState(state_id="b1", branch_id="main", timestamp=100.0)
    engine = BeliefEngine(b_state)
    src = EvidenceSource(name="system", source_type="sensor", reliability=1.0)

    b_state.set_property("A", "v", PropertyValue(value="active", confidence=0.2, source=src, timestamp=100.0))
    b_state.set_property("B", "v", PropertyValue(value="active", confidence=0.8, source=src, timestamp=100.0))
    engine.dependency_tracker.register_dependency("B", "v", "A", "v")
    engine.dependency_tracker.register_dependency("A", "v", "B", "v")

    engine.dependency_tracker.propagate_change(b_state, "A", "v")
    first_pass_a = b_state.get_property("A", "v").confidence
    first_pass_b = b_state.get_property("B", "v").confidence

    engine.dependency_tracker.propagate_change(b_state, "A", "v")
    second_pass_a = b_state.get_property("A", "v").confidence
    second_pass_b = b_state.get_property("B", "v").confidence

    assert first_pass_a == second_pass_a
    assert first_pass_b == second_pass_b

