from __future__ import annotations

import json

from backend.core.consensus_engine import (
    AgentOutput,
    Constraint,
    ConstraintType,
    ConsensusEngine,
    ConsensusStatus,
    CriticFinding,
    Decision,
    DecisionContext,
    EvidenceType,
    FindingCategory,
    Recommendation,
    Veto,
    decide_from_dicts,
)


# ---------------------------------------------------------------------------
# Multi-agent voting + weighted scoring
# ---------------------------------------------------------------------------

def test_approve_majority_by_mass():
    outputs = [
        AgentOutput("Engineer", Decision.APPROVE, source_id="m1",
                    recommendations=(Recommendation("Engineer", "Ship v2", 0.9),)),
        AgentOutput("Scientist", Decision.APPROVE, source_id="m2"),
        AgentOutput("Poet", Decision.REJECT, source_id="m3"),
    ]
    d = ConsensusEngine.decide(outputs)
    assert d.status is ConsensusStatus.APPROVED
    assert d.approve_mass > d.reject_mass
    assert d.selected.message == "Ship v2"


def test_abstain_is_not_counted():
    outputs = [
        AgentOutput("Scientist", Decision.ABSTAIN, source_id="m1"),
        AgentOutput("Poet", Decision.ABSTAIN, source_id="m2"),
        AgentOutput("Engineer", Decision.REJECT, source_id="m3"),
    ]
    d = ConsensusEngine.decide(outputs)
    assert "Scientist" in d.abstained and "Poet" in d.abstained
    assert d.status is ConsensusStatus.REJECTED
    assert d.reject_mass > 0 and d.approve_mass == 0


def test_evidence_multiplier_beats_pure_reasoning():
    # Tool-verified REJECT should outweigh a same-authority reasoning APPROVE.
    outputs = [
        AgentOutput("Engineer", Decision.APPROVE, source_id="m1",
                    evidence=(EvidenceType.REASONING,)),
        AgentOutput("Scientist", Decision.REJECT, source_id="m2",
                    evidence=(EvidenceType.TOOL_VERIFIED,)),
    ]
    d = ConsensusEngine.decide(outputs)
    assert d.reject_mass > d.approve_mass
    assert d.status is ConsensusStatus.REJECTED


# ---------------------------------------------------------------------------
# Independent-source rule
# ---------------------------------------------------------------------------

def test_same_source_counts_once():
    # Three APPROVE votes from the SAME model vs one REJECT from another model.
    outputs = [
        AgentOutput("Engineer", Decision.APPROVE, source_id="ollama-A", evidence=(EvidenceType.REASONING,)),
        AgentOutput("Planner", Decision.APPROVE, source_id="ollama-A", evidence=(EvidenceType.REASONING,)),
        AgentOutput("Builder", Decision.APPROVE, source_id="ollama-A", evidence=(EvidenceType.REASONING,)),
        AgentOutput("Scientist", Decision.REJECT, source_id="sim-B", evidence=(EvidenceType.SIMULATION,)),
    ]
    d = ConsensusEngine.decide(outputs)
    # Only 2 independent sources, not 4.
    assert d.independent_sources == 2
    # The single model contributes one source's mass (its strongest = Engineer 5*0.5=2.5),
    # not 3x; the independent simulation (Scientist 5*0.9=4.5) outweighs it.
    assert d.approve_mass == 2.5
    assert d.reject_mass == 4.5
    assert d.status is ConsensusStatus.REJECTED


# ---------------------------------------------------------------------------
# Conflict detection (Stages 1 & 2)
# ---------------------------------------------------------------------------

def test_hard_conflict_no_voting():
    outputs = [
        AgentOutput("Security", Decision.APPROVE, constraints=(
            Constraint("Security", ConstraintType.HARD, "Encryption required", key="enc", required_value=True),)),
        AgentOutput("Scientist", Decision.APPROVE, constraints=(
            Constraint("Scientist", ConstraintType.HARD, "Encryption impossible", key="enc", required_value=False),)),
    ]
    d = ConsensusEngine.decide(outputs)
    assert d.status is ConsensusStatus.NO_FEASIBLE_SOLUTION
    assert d.requires_human_approval is True


def test_validator_veto_rejects_without_vote():
    outputs = [
        AgentOutput("Engineer", Decision.APPROVE, source_id="m1",
                    recommendations=(Recommendation("Engineer", "Deploy", 1.0),)),
        AgentOutput("Security", veto=Veto("Security", passed=False, reason="open port")),
    ]
    d = ConsensusEngine.decide(outputs)
    assert d.status is ConsensusStatus.REJECTED
    assert d.rejected_by == "Security"
    assert d.requires_human_approval is True


# ---------------------------------------------------------------------------
# Critic findings: block -> rework (capped), never veto
# ---------------------------------------------------------------------------

def test_blocking_finding_triggers_rework_then_escalates():
    outputs = [
        AgentOutput("Engineer", Decision.APPROVE, source_id="m1"),
        AgentOutput("Critic", critic_findings=(
            CriticFinding("Critic", FindingCategory.BLOCKING, "race condition in sync"),)),
    ]
    first = ConsensusEngine.decide(outputs, DecisionContext(round_index=0, max_rounds=2))
    assert first.status is ConsensusStatus.ESCALATE
    assert first.rework_recommended is True
    assert first.requires_human_approval is False

    # After the cap, the same blocking finding escalates to a human.
    last = ConsensusEngine.decide(outputs, DecisionContext(round_index=1, max_rounds=2))
    assert last.status is ConsensusStatus.ESCALATE
    assert last.rework_recommended is False
    assert last.requires_human_approval is True


def test_advisory_finding_does_not_block():
    outputs = [
        AgentOutput("Engineer", Decision.APPROVE, source_id="m1",
                    recommendations=(Recommendation("Engineer", "Proceed", 0.8),)),
        AgentOutput("Critic", critic_findings=(
            CriticFinding("Critic", FindingCategory.ADVISORY, "consider logging"),)),
    ]
    d = ConsensusEngine.decide(outputs)
    assert d.status is ConsensusStatus.APPROVED
    assert len(d.advisory_findings) == 1


# ---------------------------------------------------------------------------
# Human approval gating
# ---------------------------------------------------------------------------

def test_low_margin_escalates_to_human():
    outputs = [
        AgentOutput("Engineer", Decision.APPROVE, source_id="m1", evidence=(EvidenceType.REASONING,)),
        AgentOutput("Scientist", Decision.REJECT, source_id="m2", evidence=(EvidenceType.REASONING,)),
    ]
    # Equal authority+evidence -> margin 0 -> escalate.
    d = ConsensusEngine.decide(outputs)
    assert d.status is ConsensusStatus.ESCALATE
    assert d.requires_human_approval is True


def test_production_project_requires_human_approval():
    outputs = [
        AgentOutput("Engineer", Decision.APPROVE, source_id="m1",
                    recommendations=(Recommendation("Engineer", "Refactor", 0.9),)),
    ]
    d = ConsensusEngine.decide(outputs, DecisionContext(project="DEWS"))
    assert d.status is ConsensusStatus.APPROVED
    assert d.requires_human_approval is True


# ---------------------------------------------------------------------------
# Never allow automatic code changes
# ---------------------------------------------------------------------------

def test_code_change_always_requires_human_and_never_auto_applies():
    outputs = [
        AgentOutput("Engineer", Decision.APPROVE, source_id="m1",
                    recommendations=(Recommendation("Engineer", "Edit auth.py", 1.0),)),
    ]
    d = ConsensusEngine.decide(outputs, DecisionContext(code_change=True))
    assert d.requires_human_approval is True
    assert d.is_actionable is False        # cannot act without a human
    assert d.auto_apply_allowed is False    # the engine never applies anything


def test_engine_exposes_no_apply_or_execute():
    # Decision-only: there is no method to apply/execute a change.
    for forbidden in ("apply", "execute", "commit", "run", "perform"):
        assert not hasattr(ConsensusEngine, forbidden)


# ---------------------------------------------------------------------------
# Dashboard, parsing, serialisation
# ---------------------------------------------------------------------------

def test_human_dashboard_structure():
    outputs = [
        AgentOutput("Engineer", Decision.APPROVE, source_id="m1",
                    recommendations=(Recommendation("Engineer", "Redesign memory", 0.9),)),
        AgentOutput("Security", Decision.REJECT, source_id="m2"),
        AgentOutput("Critic", critic_findings=(
            CriticFinding("Critic", FindingCategory.ADVISORY, "potential sync leak"),)),
    ]
    dash = ConsensusEngine.decide(outputs).human_dashboard()
    assert "Engineer" in dash["for"]
    assert "Security" in dash["against"]
    assert any("sync leak" in c for c in dash["critic"])
    assert len(dash["options"]) == 4


def test_decide_from_dicts_v2():
    raw = [
        {"agent": "Engineer", "decision": "approve", "confidence": 80, "source_id": "m1",
         "evidence": [{"source": "reasoning"}],
         "recommendations": [{"source": "Engineer", "description": "Use SPI", "weight": 0.8}]},
        {"agent": "Security", "decision": "reject", "source_id": "m2",
         "evidence": [{"source": "validator"}]},
    ]
    d = decide_from_dicts(raw, {"project": "Kairo"})
    json.dumps(d.to_dict())  # serialisable
    assert d.requires_human_approval is True  # production project


def test_evidence_and_decision_coercion():
    assert EvidenceType.coerce("validator") is EvidenceType.TOOL_VERIFIED
    assert Decision.coerce("approve") is Decision.APPROVE
    o = AgentOutput.from_dict({"agent": "X", "decision": "ABSTAIN", "evidence": ["simulation"]})
    assert o.evidence[0] is EvidenceType.SIMULATION
