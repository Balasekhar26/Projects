"""Cognitive API Router — /cognitive/* endpoints.

Exposes the CognitiveStateMachine, EventBus, and ReasoningKernel
as observable REST endpoints. Provides a full cognitive cycle trigger,
real-time state inspection, Blackboard snapshots, EventBus history,
and reasoning traces.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

cognitive_router = APIRouter(tags=["Cognitive"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CognitiveCycleRequest(BaseModel):
    goal_id: str
    goal_title: str
    goal_description: str = ""
    session_id: str = "primary"
    mode: str = "DEEP_ANALYSIS"       # DIRECT | DEEP_ANALYSIS | HIGH_ASSURANCE


class ReasoningRequest(BaseModel):
    goal_title: str
    goal_description: str = ""
    session_id: str = "primary"
    required_capabilities: list[str] | None = None


# ---------------------------------------------------------------------------
# Cognitive cycle trigger
# ---------------------------------------------------------------------------

@cognitive_router.post("/cognitive/cycle/begin")
def cognitive_cycle_begin(req: CognitiveCycleRequest) -> dict[str, Any]:
    """Open a new cognitive cycle for a goal.

    Returns the cycle ID and initial IDLE state.
    Does NOT auto-advance — use individual state endpoints to progress.
    """
    from backend.core.cognitive_state_machine import CognitiveStateMachine
    cycle = CognitiveStateMachine.begin(
        goal_id=req.goal_id,
        goal_title=req.goal_title,
        goal_description=req.goal_description,
        session_id=req.session_id,
        mode=req.mode,
    )
    return {"cycle_id": cycle.context.cycle_id, "state": cycle.state.value, "summary": cycle.summary()}


@cognitive_router.post("/cognitive/cycle/run")
def cognitive_cycle_run(req: CognitiveCycleRequest) -> dict[str, Any]:
    """Run a complete autonomous cognitive cycle end-to-end.

    Executes: OBSERVE → RECALL → PLAN → DECIDE → EXECUTE → REFLECT → LEARN → IDLE
    using the ReasoningEngine for OBSERVE + memory retrieval for RECALL.
    Returns full cycle summary with all accumulated context.
    """
    from backend.core.cognitive_state_machine import CognitiveStateMachine
    from backend.core.reasoning_engine import ReasoningEngine

    cycle = CognitiveStateMachine.begin(
        goal_id=req.goal_id,
        goal_title=req.goal_title,
        goal_description=req.goal_description,
        session_id=req.session_id,
        mode=req.mode,
    )

    # OBSERVE: run ReasoningKernel to populate world context
    try:
        trace = ReasoningEngine.reason(
            req.goal_title,
            req.goal_description,
            session_id=req.session_id,
        )
        world_context = {
            "domain": trace.domain,
            "intent": trace.intent,
            "world_context": trace.world_context,
            "reasoning_status": trace.status,
        }
        memory_context = {
            "memory_recall": trace.memory_context,
            "evidence": trace.evidence,
        }
        plan_blueprint = {
            "assumptions": trace.assumptions,
            "risks": trace.risks,
            "capability_gaps": trace.capability_gaps,
            "reasoning_trace_id": trace.trace_id,
        }
    except Exception as exc:
        world_context = {"error": str(exc)}
        memory_context = {}
        plan_blueprint = {}
        trace = None

    # Determine risk from reasoning
    risks = (trace.risks if trace else [])
    risk_level = "LOW"
    if any(r.get("severity") == "critical" for r in risks):
        risk_level = "CRITICAL"
    elif any(r.get("severity") == "high" for r in risks):
        risk_level = "HIGH"
    elif any(r.get("severity") == "medium" for r in risks):
        risk_level = "MEDIUM"

    # Run the cycle
    (
        cycle
        .observe(world_context)
        .recall(memory_context)
        .plan(plan_blueprint)
    )

    if req.mode != "DIRECT":
        cycle.simulate({"risk_level": risk_level, "mode": req.mode})

    cycle.decide({"risk_level": risk_level, "auto": True})

    if risk_level in ("HIGH", "CRITICAL") or req.mode == "HIGH_ASSURANCE":
        cycle.approve(
            approved=True,  # auto-approve at API level; human can override via UI
            approver="api_auto",
            reason=f"Risk={risk_level}, mode={req.mode}",
        )

    (
        cycle
        .execute({"status": "dispatched", "dispatched_at": time.time()})
        .reflect({"outcome": "dispatched", "trace_id": trace.trace_id if trace else ""})
        .learn({"insights": [f"Goal '{req.goal_title}' dispatched via cognitive cycle"]})
        .finish()
    )

    return {
        "cycle_id": cycle.context.cycle_id,
        "final_state": cycle.state.value,
        "transitions": len(cycle.transition_history()),
        "summary": cycle.summary(),
        "reasoning_status": trace.status if trace else "unavailable",
        "capability_gaps": trace.capability_gaps if trace else [],
        "risks": risks,
    }


# ---------------------------------------------------------------------------
# State inspection
# ---------------------------------------------------------------------------

@cognitive_router.get("/cognitive/state")
def cognitive_state() -> dict[str, Any]:
    """Return EventBus recent cognitive state change events."""
    from backend.core.event_bus import EventBus, EventName
    events = EventBus.history(EventName.COGNITIVE_STATE_CHANGED, limit=10)
    return {
        "recent_transitions": [e.to_dict() for e in events],
        "event_bus_stats": EventBus.stats(),
    }


@cognitive_router.get("/cognitive/events")
def cognitive_events(event_name: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Return recent EventBus events, optionally filtered by event name."""
    from backend.core.event_bus import EventBus
    events = EventBus.history(event_name, limit=limit)
    return {
        "events": [e.to_dict() for e in events],
        "count": len(events),
        "filter": event_name,
    }


@cognitive_router.get("/cognitive/events/ledger")
def cognitive_event_ledger(event_name: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Query the persistent event ledger (SQLite-backed)."""
    from backend.core.event_bus import EventBus
    records = EventBus.ledger_query(event_name=event_name, limit=limit)
    return {"records": records, "count": len(records)}


# ---------------------------------------------------------------------------
# Reasoning traces
# ---------------------------------------------------------------------------

@cognitive_router.post("/cognitive/reason")
def cognitive_reason(req: ReasoningRequest) -> dict[str, Any]:
    """Run the ReasoningKernel for a goal and return a full ReasoningTrace."""
    from backend.core.reasoning_engine import ReasoningEngine
    trace = ReasoningEngine.reason(
        req.goal_title,
        req.goal_description,
        session_id=req.session_id,
        required_capabilities=req.required_capabilities,
    )
    return {"trace": trace.to_dict()}


@cognitive_router.post("/cognitive/analyze")
def cognitive_analyze(req: ReasoningRequest) -> dict[str, Any]:
    """Run the fast heuristic analyze() on a goal (backward-compatible)."""
    from backend.core.reasoning_engine import ReasoningEngine
    result = ReasoningEngine.analyze(
        req.goal_title,
        req.goal_description,
        session_id=req.session_id,
    )
    return result


# ---------------------------------------------------------------------------
# Cognitive ledger
# ---------------------------------------------------------------------------

@cognitive_router.get("/cognitive/ledger")
def cognitive_ledger(goal_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Query the cognitive transition ledger."""
    from backend.core.cognitive_state_machine import CognitiveStateMachine
    records = CognitiveStateMachine.ledger_query(goal_id=goal_id, limit=limit)
    return {"records": records, "count": len(records)}


# ---------------------------------------------------------------------------
# EventBus stats
# ---------------------------------------------------------------------------

@cognitive_router.get("/cognitive/stats")
def cognitive_stats() -> dict[str, Any]:
    """Return comprehensive EventBus and cognitive system statistics."""
    from backend.core.event_bus import EventBus
    from backend.core.capability_graph import CapabilityGraph

    bus_stats = EventBus.stats()
    cap_status = CapabilityGraph.status()

    return {
        "event_bus": bus_stats,
        "capability_graph": cap_status,
        "timestamp": time.time(),
    }


# ---------------------------------------------------------------------------
# Capability graph inspection
# ---------------------------------------------------------------------------

@cognitive_router.get("/cognitive/capabilities")
def cognitive_capabilities() -> dict[str, Any]:
    """List all registered capabilities and their availability."""
    from backend.core.capability_graph import CapabilityGraph
    caps = CapabilityGraph.list_capabilities()
    return {"capabilities": caps, "count": len(caps), "status": CapabilityGraph.status()}


@cognitive_router.post("/cognitive/capabilities/assess")
def cognitive_assess_capabilities(goal: str, required: list[str]) -> dict[str, Any]:
    """Assess whether required capabilities are available for a goal."""
    from backend.core.capability_graph import CapabilityGraph
    return CapabilityGraph.assess(goal, required)
