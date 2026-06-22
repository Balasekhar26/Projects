from __future__ import annotations

import json

from backend.core.consensus_engine import (
    AgentOutput,
    Constraint,
    ConstraintType,
    ConsensusEngine,
    ConsensusStatus,
    Recommendation,
    Veto,
    decide_from_dicts,
)


# ---------------------------------------------------------------------------
# Approval + weighted ranking (Rule 2)
# ---------------------------------------------------------------------------

def test_approves_and_selects_highest_weighted_recommendation():
    outputs = [
        AgentOutput(
            agent="Engineer",
            confidence=0.9,
            recommendations=(Recommendation("Engineer", "Use a star topology", weight=0.8),),
        ),
        AgentOutput(
            agent="Scientist",
            confidence=0.5,
            recommendations=(Recommendation("Scientist", "Use a mesh topology", weight=0.9),),
        ),
    ]
    decision = ConsensusEngine.decide(outputs)
    assert decision.status is ConsensusStatus.APPROVED
    # Engineer: 0.8*0.9=0.72 beats Scientist: 0.9*0.5=0.45.
    assert decision.selected.message == "Use a star topology"
    assert decision.ranked_recommendations[0].score > decision.ranked_recommendations[1].score


def test_selection_does_not_blend():
    outputs = [
        AgentOutput("A", 1.0, recommendations=(Recommendation("A", "Plan A", 0.9),)),
        AgentOutput("B", 1.0, recommendations=(Recommendation("B", "Plan B", 0.8),)),
    ]
    decision = ConsensusEngine.decide(outputs)
    # Exactly one coherent plan is chosen; it is one of the inputs, not a merge.
    assert decision.selected.message in {"Plan A", "Plan B"}
    assert decision.selected.message == "Plan A"


def test_feasible_with_no_recommendations_is_approved_without_selection():
    outputs = [
        AgentOutput("Engineer", 0.8, constraints=(
            Constraint("Engineer", ConstraintType.HARD, "Must fit 2-layer PCB", key="layers", required_value=2),
        )),
    ]
    decision = ConsensusEngine.decide(outputs)
    assert decision.status is ConsensusStatus.APPROVED
    assert decision.selected is None


# ---------------------------------------------------------------------------
# Vetoes (Rules 3 & 4)
# ---------------------------------------------------------------------------

def test_security_veto_rejects():
    outputs = [
        AgentOutput("Engineer", 0.9, recommendations=(Recommendation("Engineer", "Ship it", 0.9),)),
        AgentOutput("Security", 1.0, veto=Veto("Security", passed=False, reason="No encryption")),
    ]
    decision = ConsensusEngine.decide(outputs)
    assert decision.status is ConsensusStatus.REJECTED
    assert decision.rejected_by == "Security"
    assert decision.selected is None


def test_physics_veto_rejects():
    outputs = [
        AgentOutput("Engineer", 0.9, recommendations=(Recommendation("Engineer", "Perpetual motion drive", 1.0),)),
        AgentOutput("Scientist", 1.0, veto=Veto("Scientist", passed=False, reason="Energy in < energy out")),
    ]
    decision = ConsensusEngine.decide(outputs)
    assert decision.status is ConsensusStatus.REJECTED
    assert decision.rejected_by == "Scientist"


def test_all_vetoes_pass_does_not_reject():
    outputs = [
        AgentOutput("Engineer", 0.9, recommendations=(Recommendation("Engineer", "Ship it", 0.9),)),
        AgentOutput("Security", 1.0, veto=Veto("Security", passed=True)),
    ]
    decision = ConsensusEngine.decide(outputs)
    assert decision.status is ConsensusStatus.APPROVED
    assert decision.selected.message == "Ship it"


def test_veto_takes_precedence_over_recommendations():
    outputs = [
        AgentOutput("Engineer", 1.0, recommendations=(Recommendation("Engineer", "Strong plan", 1.0),)),
        AgentOutput("Security", 1.0, veto=Veto("Security", passed=False, reason="unsafe")),
    ]
    decision = ConsensusEngine.decide(outputs)
    assert decision.status is ConsensusStatus.REJECTED


# ---------------------------------------------------------------------------
# Hard constraint conflicts (Rule 1)
# ---------------------------------------------------------------------------

def test_hard_conflict_on_same_key_is_infeasible():
    outputs = [
        AgentOutput("Security", 1.0, constraints=(
            Constraint("Security", ConstraintType.HARD, "Encryption required", key="encryption", required_value=True),
        )),
        AgentOutput("Scientist", 1.0, constraints=(
            Constraint("Scientist", ConstraintType.HARD, "Encryption impossible within power budget",
                       key="encryption", required_value=False),
        )),
    ]
    decision = ConsensusEngine.decide(outputs)
    assert decision.status is ConsensusStatus.NO_FEASIBLE_SOLUTION
    assert len(decision.conflicts) == 1
    assert decision.selected is None
    # Alternatives are surfaced for the user to decide the tradeoff.
    assert isinstance(decision.alternatives, list)


def test_unsatisfiable_hard_constraint_is_infeasible():
    outputs = [
        AgentOutput("Scientist", 1.0, constraints=(
            Constraint("Scientist", ConstraintType.HARD, "Required power exceeds the battery",
                       key="power", satisfiable=False),
        )),
    ]
    decision = ConsensusEngine.decide(outputs)
    assert decision.status is ConsensusStatus.NO_FEASIBLE_SOLUTION


def test_compatible_hard_constraints_are_feasible():
    outputs = [
        AgentOutput("Security", 1.0, constraints=(
            Constraint("Security", ConstraintType.HARD, "Encryption required", key="encryption", required_value=True),
        )),
        AgentOutput("Engineer", 0.9, constraints=(
            Constraint("Engineer", ConstraintType.HARD, "Encryption supported", key="encryption", required_value=True),
        ), recommendations=(Recommendation("Engineer", "Add an AES block", 0.7),)),
    ]
    decision = ConsensusEngine.decide(outputs)
    assert decision.status is ConsensusStatus.APPROVED
    assert decision.selected.message == "Add an AES block"


# ---------------------------------------------------------------------------
# Soft constraints never block (Rule 2)
# ---------------------------------------------------------------------------

def test_soft_conflict_does_not_block():
    outputs = [
        AgentOutput("Scientist", 0.8, constraints=(
            Constraint("Scientist", ConstraintType.SOFT, "Battery life may decrease", key="battery", required_value=False),
        ), recommendations=(Recommendation("Scientist", "Accept lower battery life", 0.6),)),
        AgentOutput("Engineer", 0.7, constraints=(
            Constraint("Engineer", ConstraintType.SOFT, "Prefer max battery life", key="battery", required_value=True),
        )),
    ]
    decision = ConsensusEngine.decide(outputs)
    assert decision.status is ConsensusStatus.APPROVED
    assert len(decision.soft_constraints) == 2


# ---------------------------------------------------------------------------
# Determinism, parsing, serialisation
# ---------------------------------------------------------------------------

def test_decision_is_deterministic():
    outputs = [
        AgentOutput("A", 0.9, recommendations=(Recommendation("A", "x", 0.5),)),
        AgentOutput("B", 0.9, recommendations=(Recommendation("B", "y", 0.5),)),
    ]
    assert ConsensusEngine.decide(outputs).to_dict() == ConsensusEngine.decide(outputs).to_dict()


def test_decide_from_dicts_and_json():
    raw = [
        {"agent": "Engineer", "confidence": 0.9,
         "recommendations": [{"source": "Engineer", "message": "Use SPI", "weight": 0.8}]},
        {"agent": "Security", "veto": {"source": "Security", "passed": False, "reason": "exposed bus"}},
    ]
    decision = decide_from_dicts(raw)
    assert decision.status is ConsensusStatus.REJECTED
    assert decision.rejected_by == "Security"
    json.dumps(decision.to_dict())  # serialisable


def test_constraint_type_coercion():
    assert ConstraintType.coerce("hard") is ConstraintType.HARD
    c = Constraint.from_dict({"source": "X", "type": "soft", "message": "m"})
    assert c.type is ConstraintType.SOFT
