"""Tests for backend/core/cognitive_state_machine.py"""
from __future__ import annotations

import time
import pytest

from backend.core.cognitive_state_machine import (
    CognitiveCycle,
    CognitiveContext,
    CognitiveState,
    CognitiveStateMachine,
)
from backend.core.event_bus import EventBus, EventName


@pytest.fixture(autouse=True)
def clean():
    EventBus.reset()
    CognitiveStateMachine.reset_ledger()
    yield
    EventBus.reset()
    CognitiveStateMachine.reset_ledger()


# ---------------------------------------------------------------------------
# Happy path — full cycle
# ---------------------------------------------------------------------------

def test_full_cycle_direct_mode():
    """DIRECT mode: IDLE→OBSERVE→RECALL→PLAN→DECIDE→EXECUTE→REFLECT→LEARN→IDLE"""
    cycle = CognitiveStateMachine.begin("g1", "Deploy backend", mode="DIRECT")
    assert cycle.state == CognitiveState.IDLE

    cycle.observe({"entity": "project_kattappa"})
    assert cycle.state == CognitiveState.OBSERVE

    cycle.recall({"memories": ["past deploy", "port config"]})
    assert cycle.state == CognitiveState.RECALL

    cycle.plan({"blueprint_id": "bp_001", "steps": 3})
    assert cycle.state == CognitiveState.PLAN

    # DIRECT mode skips SIMULATE → directly to DECIDE
    cycle.decide({"candidate": "bp_001", "risk_level": "LOW"})
    assert cycle.state == CognitiveState.DECIDE

    # Low risk → auto-approve skips explicit APPROVE state
    cycle.execute({"status": "ok", "output": "deployed"})
    assert cycle.state == CognitiveState.EXECUTE

    cycle.reflect({"outcome": "success", "findings": []})
    assert cycle.state == CognitiveState.REFLECT

    cycle.learn({"insights": ["port 8000 confirmed working"]})
    assert cycle.state == CognitiveState.LEARN

    cycle.finish()
    assert cycle.state == CognitiveState.IDLE


def test_full_cycle_deep_analysis_with_simulate_and_approve():
    """DEEP_ANALYSIS mode: includes SIMULATE and APPROVE."""
    cycle = CognitiveStateMachine.begin("g2", "Refactor memory", mode="DEEP_ANALYSIS")
    (
        cycle
        .observe({"context": "memory subsystem"})
        .recall({"memories": []})
        .plan({"blueprint_id": "bp_002"})
        .simulate({"risk_level": "MEDIUM", "reversibility": 0.8})
        .decide({"candidate": "bp_002", "risk_level": "MEDIUM"})
        .approve(approved=True, approver="auto", reason="risk below threshold")
        .execute({"status": "ok"})
        .reflect({"outcome": "success"})
        .learn({"insights": []})
        .finish()
    )
    assert cycle.state == CognitiveState.IDLE
    assert cycle.context.completed_at > 0


def test_context_accumulates_across_states():
    cycle = CognitiveStateMachine.begin("g3", "Test goal")
    cycle.observe({"entity": "test_entity"})
    cycle.recall({"memories": ["mem1", "mem2"]})
    cycle.plan({"blueprint_id": "bp_test", "steps": 2})
    cycle.simulate({"risk_level": "LOW", "token_cost": 500})
    cycle.decide({"candidate": "bp_test", "risk_level": "LOW"})
    cycle.execute({"status": "ok", "result": 42})
    cycle.reflect({"outcome": "success", "findings": ["finding_a"]})
    cycle.learn({"insights": ["insight_1"]})
    cycle.finish()

    ctx = cycle.context
    assert ctx.world_context["entity"] == "test_entity"
    assert ctx.memory_context["memories"] == ["mem1", "mem2"]
    assert ctx.plan_blueprint["blueprint_id"] == "bp_test"
    assert ctx.simulation_report["token_cost"] == 500
    assert ctx.decision["candidate"] == "bp_test"
    assert ctx.execution_result["result"] == 42
    assert ctx.reflection_result["findings"] == ["finding_a"]
    assert ctx.learning_result["insights"] == ["insight_1"]


# ---------------------------------------------------------------------------
# Illegal transitions
# ---------------------------------------------------------------------------

def test_cannot_plan_without_recall():
    cycle = CognitiveStateMachine.begin("g4", "Bad goal")
    cycle.observe({})
    with pytest.raises(RuntimeError, match="Illegal transition"):
        cycle.plan({})


def test_cannot_execute_without_decide():
    cycle = CognitiveStateMachine.begin("g5", "Bad goal")
    cycle.observe({}).recall({}).plan({}).simulate({})
    with pytest.raises(RuntimeError, match="Illegal transition"):
        cycle.execute({})


def test_cannot_reflect_without_execute():
    cycle = CognitiveStateMachine.begin("g6", "Bad goal")
    cycle.observe({}).recall({}).plan({}).decide({})
    with pytest.raises(RuntimeError, match="Illegal transition"):
        cycle.reflect({})


def test_cannot_learn_without_reflect():
    cycle = CognitiveStateMachine.begin("g7", "Bad goal")
    cycle.observe({}).recall({}).plan({}).decide({}).execute({})
    with pytest.raises(RuntimeError, match="Illegal transition"):
        cycle.learn({})


def test_cannot_observe_from_non_idle():
    cycle = CognitiveStateMachine.begin("g8", "Bad goal")
    cycle.observe({})
    with pytest.raises(RuntimeError, match="Illegal transition"):
        cycle.observe({})  # already in OBSERVE


# ---------------------------------------------------------------------------
# Risk level propagation
# ---------------------------------------------------------------------------

def test_high_risk_simulation_elevates_risk():
    cycle = CognitiveStateMachine.begin("g9", "High-risk goal")
    cycle.observe({}).recall({}).plan({})
    cycle.simulate({"risk_level": "CRITICAL"})
    assert cycle.context.risk_level == "CRITICAL"


def test_decide_risk_level_overrides_simulation():
    cycle = CognitiveStateMachine.begin("g10", "Risk override")
    cycle.observe({}).recall({}).plan({}).simulate({"risk_level": "HIGH"})
    cycle.decide({"risk_level": "MEDIUM"})  # human decision lowers risk
    assert cycle.context.risk_level == "MEDIUM"


# ---------------------------------------------------------------------------
# Approval gate
# ---------------------------------------------------------------------------

def test_approve_records_approver():
    cycle = CognitiveStateMachine.begin("g11", "Approval test")
    (
        cycle
        .observe({}).recall({}).plan({}).simulate({})
        .decide({"risk_level": "HIGH"})
        .approve(approved=True, approver="human_operator", reason="reviewed OK")
    )
    assert cycle.context.approval_record["approved"] is True
    assert cycle.context.approval_record["approver"] == "human_operator"


def test_denied_approval_sets_blocked_status():
    cycle = CognitiveStateMachine.begin("g12", "Denied approval")
    (
        cycle
        .observe({}).recall({}).plan({}).simulate({})
        .decide({"risk_level": "CRITICAL"})
        .approve(approved=False, approver="human_operator", reason="too risky")
    )
    assert cycle.context.approval_record["approved"] is False
    assert cycle.context.execution_result["status"] == "blocked"


# ---------------------------------------------------------------------------
# EventBus integration
# ---------------------------------------------------------------------------

def test_cognitive_state_changed_events_emitted():
    state_changes: list[str] = []

    def capture(e):
        state_changes.append(e.payload.get("to_state", ""))

    EventBus.subscribe(EventName.COGNITIVE_STATE_CHANGED, capture)

    cycle = CognitiveStateMachine.begin("g13", "Event test")
    cycle.observe({}).recall({}).plan({}).decide({}).execute({}).reflect({}).learn({}).finish()

    # Give async handlers a moment
    time.sleep(0.1)

    assert "OBSERVE" in state_changes
    assert "RECALL" in state_changes
    assert "PLAN" in state_changes
    assert "EXECUTE" in state_changes
    assert "REFLECT" in state_changes
    assert "LEARN" in state_changes
    assert "IDLE" in state_changes


def test_planner_started_event_emitted():
    events: list = []
    EventBus.subscribe(EventName.PLANNER_STARTED, events.append)
    cycle = CognitiveStateMachine.begin("g14", "Planner event test")
    cycle.observe({}).recall({}).plan({"blueprint_id": "bp_ev"})
    time.sleep(0.1)
    assert len(events) >= 1
    assert events[0].payload.get("goal_id") == "g14"


def test_reflection_completed_event_emitted():
    events: list = []
    EventBus.subscribe(EventName.REFLECTION_COMPLETED, events.append)
    cycle = CognitiveStateMachine.begin("g15", "Reflect event test")
    (
        cycle.observe({}).recall({}).plan({}).decide({})
        .execute({}).reflect({"outcome": "success"})
    )
    time.sleep(0.1)
    assert len(events) >= 1
    assert events[0].payload.get("outcome") == "success"


def test_world_model_updated_event_on_learn():
    events: list = []
    EventBus.subscribe(EventName.WORLD_MODEL_UPDATED, events.append)
    cycle = CognitiveStateMachine.begin("g16", "Learn event test")
    (
        cycle.observe({}).recall({}).plan({}).decide({})
        .execute({}).reflect({}).learn({"insights": ["insight_wm"]})
    )
    time.sleep(0.1)
    assert len(events) >= 1
    assert "insight_wm" in events[0].payload.get("insights", [])


# ---------------------------------------------------------------------------
# Ledger persistence
# ---------------------------------------------------------------------------

def test_ledger_records_transitions():
    cycle = CognitiveStateMachine.begin("g17", "Ledger test")
    cycle.observe({}).recall({}).plan({}).decide({}).execute({}).reflect({}).learn({}).finish()
    time.sleep(0.05)

    records = CognitiveStateMachine.ledger_query(goal_id="g17")
    assert len(records) >= 7  # at least 7 transitions (IDLE→OBSERVE→RECALL→...→IDLE)
    states = [r["to_state"] for r in records]
    assert "OBSERVE" in states
    assert "IDLE" in states


def test_ledger_query_by_cycle_id():
    cycle = CognitiveStateMachine.begin("g18", "Cycle ledger test")
    cycle_id = cycle.context.cycle_id
    cycle.observe({}).recall({}).plan({}).decide({}).execute({}).reflect({}).learn({}).finish()
    time.sleep(0.05)

    records = CognitiveStateMachine.ledger_query(cycle_id=cycle_id)
    assert len(records) >= 7
    for r in records:
        assert r["cycle_id"] == cycle_id


# ---------------------------------------------------------------------------
# Transition history
# ---------------------------------------------------------------------------

def test_transition_history():
    cycle = CognitiveStateMachine.begin("g19", "History test")
    cycle.observe({}).recall({}).plan({}).decide({}).execute({}).reflect({}).learn({}).finish()
    history = cycle.transition_history()
    assert len(history) == 8
    assert history[0]["from"] == "IDLE"
    assert history[0]["to"] == "OBSERVE"
    assert history[-1]["to"] == "IDLE"


def test_summary():
    cycle = CognitiveStateMachine.begin("g20", "Summary test", goal_description="desc", mode="HIGH_ASSURANCE")
    summary = cycle.summary()
    assert summary["goal_id"] == "g20"
    assert summary["mode"] == "HIGH_ASSURANCE"
    assert summary["current_state"] == "IDLE"
    assert "cycle_id" in summary
