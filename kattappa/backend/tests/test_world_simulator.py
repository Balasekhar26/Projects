"""Unit and integration tests for Program 5F: World Simulation Engine.
"""
from __future__ import annotations

import os
import tempfile
import pytest

from backend.core.beliefs.belief import Belief
from backend.core.beliefs.belief_store import BeliefStore
from backend.core.beliefs.causal_engine import StructuralCausalModel, CausalVariable
from backend.core.simulation.world_simulator import WorldSimulator, Scenario, ScenarioComparator


@pytest.fixture
def test_simulation_store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    store = BeliefStore(db_path=db_path)
    
    # Pre-populate store with basic facts
    # Subject: server_01, Predicate: online, Value: True, Conf: 0.8
    b1 = Belief.create("server_01", "online", True, 0.8)
    store.save_belief(b1)

    yield store

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


@pytest.fixture
def base_scm():
    scm = StructuralCausalModel()
    
    # A: Power Grid (prior 0.1 fail rate)
    scm.add_variable(CausalVariable("Grid", parents=[], equation=lambda p, u: u), exogenous_prior=0.1)
    
    # B: Server Online (depends on Grid, fails if Grid fails)
    scm.add_variable(
        CausalVariable("Server", parents=["Grid"], equation=lambda p, u: (not p["Grid"]) and u),
        exogenous_prior=0.9,
    )
    
    return scm


def test_world_cloning_and_simulation(test_simulation_store, base_scm):
    """Verifies that the current active belief store is cloned correctly and simulated."""
    simulator = WorldSimulator(test_simulation_store, base_scm)

    # Clone world state
    state = simulator.clone_current_world()
    assert "server_01.online" in state.variables
    assert state.variables["server_01.online"] is True
    assert state.confidences["server_01.online"] == 0.8

    # Define Scenario 1: Intervene do(Grid = True) (Force power failure)
    # Target Goal: Server
    sc_failure = Scenario(
        scenario_id="sc_fail",
        name="Grid Failure Scenario",
        interventions={"Grid": True},
        target_goal_node="Server",
    )

    pred_state, success_prob = simulator.run_simulation(sc_failure)

    # Success probability for Server Online given Grid Failure should be 0.0 (since CausalVariable checks not p["Grid"])
    assert success_prob == 0.0
    assert pred_state.variables["Server"] is False


def test_simulation_rollback_mechanics(test_simulation_store, base_scm):
    """Verifies that running simulations records history, and rollback removes them."""
    simulator = WorldSimulator(test_simulation_store, base_scm)

    sc = Scenario(
        scenario_id="sc_test",
        name="Test Scenario",
        interventions={"Grid": False},
        target_goal_node="Server",
    )

    # Run
    simulator.run_simulation(sc)
    assert len(simulator._history) == 1
    assert simulator._history[0][0] == "sc_test"

    # Rollback
    rolled_state = simulator.rollback_simulation("sc_test")
    assert rolled_state is not None
    assert len(simulator._history) == 0


def test_scenario_comparison_reports(test_simulation_store, base_scm):
    """Verifies that comparator calculates expected utility and recommends the optimal scenario."""
    simulator = WorldSimulator(test_simulation_store, base_scm)

    # Scenario A: Grid Failure
    sc_a = Scenario(
        scenario_id="sc_a",
        name="Grid Offline Intervention",
        interventions={"Grid": True},
        target_goal_node="Server",
        utility_map={True: 100.0, False: -50.0},
    )

    # Scenario B: Grid Safe
    sc_b = Scenario(
        scenario_id="sc_b",
        name="Grid Online Intervention",
        interventions={"Grid": False},
        target_goal_node="Server",
        utility_map={True: 100.0, False: -50.0},
    )

    state_a, prob_a = simulator.run_simulation(sc_a)
    state_b, prob_b = simulator.run_simulation(sc_b)

    report = ScenarioComparator.compare_scenarios([
        (sc_a, state_a, prob_a),
        (sc_b, state_b, prob_b),
    ])

    assert "World Simulation Comparison Report" in report
    assert "Grid Offline Intervention" in report
    assert "Grid Online Intervention" in report
    assert "Grid Online Intervention" in report.split("### Recommendation")[1], "B should be recommended over A"
