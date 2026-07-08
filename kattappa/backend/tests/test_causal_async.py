"""Unit tests for asynchronous extensions of the Causal Reasoning and Simulation Engines.
"""
from __future__ import annotations

import asyncio
import pytest

from backend.core.beliefs.causal_engine import (
    StructuralCausalModel,
    CausalVariable,
    RootCauseAnalyzer,
)
from backend.core.simulation.world_simulator import (
    WorldSimulator,
    Scenario,
    SimulationState,
)
from backend.core.beliefs.belief_store import BeliefStore


def test_counterfactual_async():
    """Verifies that counterfactual queries can run asynchronously off the main thread."""
    scm = StructuralCausalModel()
    scm.add_variable(CausalVariable("T", parents=[], equation=lambda p, u: u), exogenous_prior=0.4)
    scm.add_variable(
        CausalVariable("C", parents=["T"], equation=lambda p, u: p["T"] or u),
        exogenous_prior=0.1,
    )

    async def run():
        return await scm.counterfactual_async(
            evidence={"T": True, "C": True},
            intervention={"T": False},
            target="C"
        )

    res = asyncio.run(run())
    assert pytest.approx(res, abs=1e-5) == 0.1


def test_root_cause_analysis_async():
    """Verifies that Root Cause Analysis can run asynchronously off the main thread."""
    scm = StructuralCausalModel()
    scm.add_variable(CausalVariable("Grid", parents=[], equation=lambda p, u: u), exogenous_prior=0.1)
    scm.add_variable(
        CausalVariable("Server", parents=["Grid"], equation=lambda p, u: p["Grid"] or u),
        exogenous_prior=0.05,
    )

    analyzer = RootCauseAnalyzer(scm)

    async def run():
        return await analyzer.analyze_root_cause_async({"Server": True})

    rankings = asyncio.run(run())
    assert len(rankings) > 0
    assert rankings[0][0] == "Grid"


def test_world_simulator_run_simulation_async(tmp_path):
    """Verifies that world simulator run_simulation_async computes states asynchronously."""
    # Setup simple BeliefStore with temporary file
    db_path = tmp_path / "beliefs.db"
    store = BeliefStore(db_path)

    scm = StructuralCausalModel()
    scm.add_variable(CausalVariable("Grid", parents=[], equation=lambda p, u: u), exogenous_prior=0.1)
    scm.add_variable(
        CausalVariable("Server", parents=["Grid"], equation=lambda p, u: p["Grid"] or u),
        exogenous_prior=0.05,
    )

    sim = WorldSimulator(store, scm)
    scenario = Scenario(
        scenario_id="sc_test",
        name="Grid failure",
        interventions={"Grid": True},
        target_goal_node="Server",
    )


    async def run():
        return await sim.run_simulation_async(scenario)

    state, prob = asyncio.run(run())
    assert state.variables["Grid"] is True
    assert prob > 0.90
