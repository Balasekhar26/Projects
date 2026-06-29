"""Unit, integration, and property tests for Program 5E: Causal Reasoning Engine.
"""
from __future__ import annotations

import pytest

from backend.core.beliefs.causal_engine import (
    StructuralCausalModel,
    CausalVariable,
    RootCauseAnalyzer,
    CausalExplanationGenerator,
)


def test_scm_cycle_detection():
    """Verifies SCM prevents circular causal dependency graphs."""
    scm = StructuralCausalModel()

    # Add A
    scm.add_variable(CausalVariable("A", parents=[], equation=lambda p, u: u))
    # Add B -> A
    scm.add_variable(CausalVariable("B", parents=["A"], equation=lambda p, u: p["A"] or u))

    # Add A -> B (cycle)
    with pytest.raises(ValueError):
        scm.add_variable(CausalVariable("A", parents=["B"], equation=lambda p, u: p["B"]))


def test_observation_vs_intervention():
    """Property/Unit test verifying that Observation != Intervention for the same SCM.

    Model: Rain (R) -> Umbrella (U)
    P(R=True) = 0.3
    U = R or Noise
    """
    scm = StructuralCausalModel()

    # Rain (R) - Prior 0.3
    scm.add_variable(CausalVariable("R", parents=[], equation=lambda p, u: u), exogenous_prior=0.3)

    # Umbrella (U) - Depends on R
    scm.add_variable(
        CausalVariable("U", parents=["R"], equation=lambda p, u: p["R"] or u),
        exogenous_prior=0.1,
    )

    # 1. Observation: If we observe Umbrella = True, rain probability should increase (correlation)
    # P(R=True | U=True)
    # Exogenous variables: U_R, U_U
    # U_R has prior 0.3, U_U has prior 0.1
    # Possibilities for (U_R, U_U) that make U=True:
    # (True, True)   - Prob = 0.3 * 0.1 = 0.03 (R=True)
    # (True, False)  - Prob = 0.3 * 0.9 = 0.27 (R=True)
    # (False, True)  - Prob = 0.7 * 0.1 = 0.07 (R=False)
    # Total U=True prob = 0.37
    # P(R=True | U=True) = (0.03 + 0.27) / 0.37 = 0.30 / 0.37 = 0.8108
    p_rain_obs = scm.counterfactual(evidence={"U": True}, intervention={}, target="R")
    assert pytest.approx(p_rain_obs, abs=1e-4) == 0.8108

    # 2. Intervention: If we intervene do(Umbrella = True), rain probability should NOT change (stays at prior 0.3)
    p_rain_interv = scm.counterfactual(evidence={}, intervention={"U": True}, target="R")
    assert pytest.approx(p_rain_interv, abs=1e-4) == 0.3000

    # Verify Observation != Intervention
    assert p_rain_obs != p_rain_interv


def test_counterfactual_reasoning():
    """Verifies Judea Pearl's 3-step process on a system failure trace.

    Model: Temperature (T) -> Server Crash (C)
    T = U_T (prior 0.4)
    C = T or U_C (prior 0.1)
    Scenario: Observed Crash (C=True) and Temperature was High (T=True).
    Query: Would the crash still have occurred if T had been Low (T=False)?
    """
    scm = StructuralCausalModel()

    scm.add_variable(CausalVariable("T", parents=[], equation=lambda p, u: u), exogenous_prior=0.4)
    scm.add_variable(
        CausalVariable("C", parents=["T"], equation=lambda p, u: p["T"] or u),
        exogenous_prior=0.1,
    )

    # Run counterfactual query: P(C = True | do(T = False), given evidence T = True, C = True)
    # Abduction: Given T=True, C=True -> U_T must be True.
    # U_C is independent: since T=True already explains C=True, U_C posterior remains at its prior 0.1.
    # Action: do(T = False) -> T is forced to False.
    # Prediction: C = T or U_C -> False or U_C -> U_C.
    # So P(C=True) = P(U_C=True) = 0.1.
    p_crash_cf = scm.counterfactual(evidence={"T": True, "C": True}, intervention={"T": False}, target="C")
    assert pytest.approx(p_crash_cf, abs=1e-5) == 0.1


def test_root_cause_analysis():
    """Verifies root cause analyzer ranks the true failure cause correctly."""
    scm = StructuralCausalModel()

    # A: Power Grid (prior 0.1 fail probability, i.e. 0.9 healthy)
    scm.add_variable(CausalVariable("Grid", parents=[], equation=lambda p, u: u), exogenous_prior=0.1)
    
    # B: Main Server (fails if Grid fails)
    scm.add_variable(
        CausalVariable("Server", parents=["Grid"], equation=lambda p, u: p["Grid"] or u),
        exogenous_prior=0.05,
    )

    # Observed failure: Server = True
    analyzer = RootCauseAnalyzer(scm)
    rankings = analyzer.analyze_root_cause({"Server": True})

    # The Grid should rank as a higher root cause than Server itself because
    # do(Grid = False) is highly likely to prevent Server crash (high prevention probability)
    assert len(rankings) > 0
    assert rankings[0][0] == "Grid"
    assert rankings[0][1] > 0.0


def test_causal_explanation_generator():
    """Checks explanation trace output format."""
    expl = CausalExplanationGenerator.explain_counterfactual(
        evidence={"A": True},
        intervention={"B": False},
        target="C",
        result=0.15,
    )
    assert "Counterfactual Analysis" in expl
    assert "A=True" in expl
    assert "do(B=False)" in expl
    assert "15.00%" in expl
