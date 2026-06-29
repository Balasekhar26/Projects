"""Unit and integration tests for Program 5C: Bayesian Belief Engine.
"""
from __future__ import annotations

import os
import tempfile
import pytest

from backend.core.beliefs.belief import Belief
from backend.core.beliefs.belief_store import BeliefStore
from backend.core.beliefs.bayesian_engine import BayesianBeliefEngine, BayesianNode, BayesianNetwork
from backend.core.beliefs.bayesian_coordinator import BayesianBeliefCoordinator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bayesian_test_store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    store = BeliefStore(db_path=db_path)

    yield store

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bayesian_network_construction_and_cycles():
    """Verifies node additions, cycle detection, and topological sorting in BayesianNetwork."""
    net = BayesianNetwork()

    # Prior Node (No Parents)
    n_a = BayesianNode(node_id="A", cpt={(): 0.6})

    net.add_node(n_a)

    # Child Node
    n_b = BayesianNode(
        node_id="B",
        parents=["A"],
        cpt={(True,): 0.9, (False,): 0.1},
    )
    net.add_node(n_b)

    # Verify Topological Order
    order = net.topological_sort()
    assert order == ["A", "B"], "Topological sort must order parents before children"

    # Attempt to introduce a cycle: A -> B and B -> A
    n_cycle = BayesianNode(
        node_id="A",
        parents=["B"],
        cpt={(True,): 0.9, (False,): 0.1},
    )
    with pytest.raises(ValueError):
        # Adding a node with parents that depend on it triggers cycle validation
        net.add_node(n_cycle)


def test_bayesian_exact_inference_chain():
    """Tests exact Variable Elimination/Enumeration over a standard diagnostic chain: A -> B -> C."""
    net = BayesianNetwork()

    # A: Alarm (prior: 0.1)
    net.add_node(BayesianNode(node_id="A", cpt={(): 0.1}))

    # B: Sensor (depends on A)
    # P(B=True | A=True) = 0.9
    # P(B=True | A=False) = 0.2
    net.add_node(BayesianNode(
        node_id="B",
        parents=["A"],
        cpt={(True,): 0.9, (False,): 0.2},
    ))

    # C: Output indicator (depends on B)
    # P(C=True | B=True) = 0.8
    # P(C=True | B=False) = 0.05
    net.add_node(BayesianNode(
        node_id="C",
        parents=["B"],
        cpt={(True,): 0.8, (False,): 0.05},
    ))

    # 1. Prior probabilities (no evidence)
    p_a_prior = net.query("A", {})
    assert pytest.approx(p_a_prior, abs=1e-5) == 0.1

    # 2. Downstream prediction / Causal inference: P(C | A = True)
    p_c_given_a = net.query("C", {"A": True})
    # P(B=True|A=True)*P(C=True|B=True) + P(B=False|A=True)*P(C=True|B=False)
    # = 0.9 * 0.8 + 0.1 * 0.05 = 0.72 + 0.005 = 0.725
    assert pytest.approx(p_c_given_a, abs=1e-5) == 0.725

    # 3. Diagnostic inference (explaining upwards): P(A | C = True)
    p_a_given_c = net.query("A", {"C": True})
    # P(C=True|A=True)*P(A=True) / P(C=True)
    # P(C=True|A=True) = 0.725
    # P(C=True|A=False) = P(B=True|A=False)*P(C=True|B=True) + P(B=False|A=False)*P(C=True|B=False)
    # = 0.2 * 0.8 + 0.8 * 0.05 = 0.16 + 0.04 = 0.20
    # P(C=True) = 0.725 * 0.1 + 0.20 * 0.9 = 0.0725 + 0.18 = 0.2525
    # P(A=True|C=True) = 0.0725 / 0.2525 = 0.2871
    assert pytest.approx(p_a_given_c, abs=1e-4) == 0.2871


def test_bayesian_explanation_engine():
    """Verifies that BayesianBeliefEngine correctly formats shift explanations."""
    engine = BayesianBeliefEngine()
    engine.network.add_node(BayesianNode(node_id="A", cpt={(): 0.3}))
    engine.network.add_node(BayesianNode(
        node_id="B",
        parents=["A"],
        cpt={(True,): 0.9, (False,): 0.1},
    ))

    # Apply evidence
    engine.set_evidence("B", True)
    explanation = engine.explain_probability_shift("A")
    assert "A" in explanation
    assert "Prior Probability" in explanation
    assert "Posterior Probability" in explanation
    assert "Shift" in explanation


def test_bayesian_belief_coordinator_store_integration(bayesian_test_store):
    """Verifies that the coordinator correctly imports beliefs and propagates posteriors from store."""
    store = bayesian_test_store
    coord = BayesianBeliefCoordinator(store)

    # 1. Save two dependent beliefs to the store
    # b1: Parent (Grid power)
    # b2: Child (Server online)
    b1 = Belief.create("grid_power", "available", True, 0.8)
    b2 = Belief.create("server_01", "online", True, 0.8)
    store.save_belief(b1)
    store.save_belief(b2)

    # Set up dependency b1 -> b2
    from backend.core.beliefs.belief import BeliefDependency
    store.add_dependency(BeliefDependency(b1.belief_id, b2.belief_id, "supports"))

    # 2. Build network and verify node count
    coord.build_network_from_store()
    assert b1.belief_id in coord.engine.network.nodes
    assert b2.belief_id in coord.engine.network.nodes

    # 3. Query posterior for child
    post = coord.calculate_posterior(b2.belief_id)
    assert post > 0.0
