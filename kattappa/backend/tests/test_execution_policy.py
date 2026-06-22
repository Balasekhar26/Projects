from __future__ import annotations

import json

import pytest

from backend.core.execution_policy import (
    ActionPolicy,
    DEFAULT_POLICY_ENGINE,
    PolicyEngine,
    PolicyOutcome,
    load_policies,
)


@pytest.fixture
def engine() -> PolicyEngine:
    return PolicyEngine()


# ---------------------------------------------------------------------------
# Policy evaluation
# ---------------------------------------------------------------------------

def test_safe_actions_auto_execute(engine):
    for action in ("READ_FILE", "SEARCH_MEMORY", "LIST_DIR"):
        assert engine.evaluate(action).outcome is PolicyOutcome.AUTO_EXECUTE


def test_mutating_actions_require_human(engine):
    for action in ("CREATE_FILE", "DELETE_FILE", "GIT_COMMIT", "RUN_SHELL", "DEPLOY"):
        assert engine.evaluate(action).outcome is PolicyOutcome.REQUIRE_HUMAN


def test_dangerous_actions_blocked(engine):
    for action in ("FORMAT_DRIVE", "TRANSFER_MONEY", "DISABLE_SECURITY"):
        assert engine.evaluate(action).outcome is PolicyOutcome.BLOCKED


def test_unknown_action_denied_by_default(engine):
    decision = engine.evaluate("LAUNCH_MISSILES")
    assert decision.outcome is PolicyOutcome.REQUIRE_HUMAN
    assert decision.matched is False
    assert "deny by default" in decision.reason


def test_action_key_is_case_insensitive(engine):
    assert engine.evaluate("read_file").outcome is PolicyOutcome.AUTO_EXECUTE
    assert engine.evaluate("Run_Shell").outcome is PolicyOutcome.REQUIRE_HUMAN


# ---------------------------------------------------------------------------
# Gate (policy x consensus)
# ---------------------------------------------------------------------------

def test_auto_action_with_approval_can_auto_execute(engine):
    gate = engine.gate("READ_FILE", consensus_approved=True, consensus_requires_human=False)
    assert gate.can_auto_execute is True


def test_auto_action_blocked_when_consensus_requires_human(engine):
    gate = engine.gate("READ_FILE", consensus_approved=True, consensus_requires_human=True)
    assert gate.can_auto_execute is False
    assert gate.requires_human is True


def test_auto_action_blocked_when_consensus_not_approved(engine):
    gate = engine.gate("READ_FILE", consensus_approved=False)
    assert gate.can_auto_execute is False
    assert gate.requires_human is True


def test_human_action_never_auto_even_with_approval(engine):
    gate = engine.gate("GIT_COMMIT", consensus_approved=True, consensus_requires_human=False)
    assert gate.can_auto_execute is False
    assert gate.requires_human is True


def test_blocked_action_cannot_execute_at_all(engine):
    gate = engine.gate("FORMAT_DRIVE", consensus_approved=True, consensus_requires_human=False)
    assert gate.blocked is True
    assert gate.can_auto_execute is False
    assert gate.requires_human is False  # blocked outright, not human-waivable here


# ---------------------------------------------------------------------------
# Consensus integration
# ---------------------------------------------------------------------------

def test_gate_with_consensus_code_change_blocks_auto(engine):
    from backend.core.consensus_engine import (
        AgentOutput, ConsensusEngine, Decision, DecisionContext, Recommendation,
    )
    decision = ConsensusEngine.decide(
        [AgentOutput("Engineer", Decision.APPROVE, source_id="m1",
                     recommendations=(Recommendation("Engineer", "Edit auth.py", 1.0),))],
        DecisionContext(code_change=True),
    )
    # Consensus approved but flagged human approval (code change).
    gate = engine.gate_with_consensus("WRITE_FILE", decision)
    assert gate.can_auto_execute is False
    assert gate.requires_human is True


def test_gate_with_consensus_clean_auto():
    from backend.core.consensus_engine import (
        AgentOutput, ConsensusEngine, Decision, Recommendation,
    )
    decision = ConsensusEngine.decide(
        [AgentOutput("Engineer", Decision.APPROVE, source_id="m1",
                     recommendations=(Recommendation("Engineer", "look it up", 1.0),))],
    )
    gate = DEFAULT_POLICY_ENGINE.gate_with_consensus("SEARCH_MEMORY", decision)
    assert gate.can_auto_execute is True


# ---------------------------------------------------------------------------
# Safety: the engine decides, it never executes
# ---------------------------------------------------------------------------

def test_engine_exposes_no_execute_method():
    for forbidden in ("execute", "run", "apply", "perform", "do"):
        assert not hasattr(PolicyEngine, forbidden)


# ---------------------------------------------------------------------------
# Custom policies / overrides / serialisation
# ---------------------------------------------------------------------------

def test_register_overrides_policy(engine):
    engine.register(ActionPolicy("READ_FILE", auto_execute=False, require_human=True))
    assert engine.evaluate("READ_FILE").outcome is PolicyOutcome.REQUIRE_HUMAN


def test_load_policies_from_mapping():
    eng = load_policies({"CUSTOM_ACTION": {"auto_execute": True}})
    assert eng.evaluate("CUSTOM_ACTION").outcome is PolicyOutcome.AUTO_EXECUTE
    # Defaults still present.
    assert eng.evaluate("DELETE_FILE").outcome is PolicyOutcome.REQUIRE_HUMAN


def test_serialisation(engine):
    payload = json.dumps(engine.to_dict())
    data = json.loads(payload)
    assert any(p["action"] == "READ_FILE" for p in data["policies"])
    gate = engine.gate("READ_FILE")
    json.dumps(gate.to_dict())
