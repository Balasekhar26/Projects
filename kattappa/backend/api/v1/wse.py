"""WSE REST API — Program 4.

Endpoints:
    POST /api/v1/wse/observe     — Record a new observation
    POST /api/v1/wse/transition  — Record a new state transition
    POST /api/v1/wse/emit        — Publish a raw LedgerEvent
    GET  /api/v1/wse/timeline    — Query timeline events
    GET  /api/v1/wse/history/{id}— Retrieve transition history of an entity
    GET  /api/v1/wse/diff        — Query world state diff between two points
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.ledger.models.enums import EventType
from backend.core.ledger.models.event import LedgerEvent
from backend.core.wse.coordinator import WSECoordinator

router = APIRouter(prefix="/wse", tags=["WSE"])


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class ObserveRequest(BaseModel):
    source: str = Field(..., description="Observation source/subsystem")
    subject: str = Field(..., description="Subject of the observation")
    predicate: str = Field(..., description="Attribute observed")
    value: Any = Field(..., description="Observed value")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Observation confidence")
    session_id: str = Field("", description="Optional session ID")
    goal_id: str = Field("", description="Optional goal ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional metadata")


class TransitionRequest(BaseModel):
    entity_id: str = Field(..., description="ID of the entity")
    entity_type: str = Field(..., description="Type of the entity (e.g. goal, task)")
    from_state: Dict[str, Any] = Field(..., description="State before transition")
    to_state: Dict[str, Any] = Field(..., description="State after transition")
    trigger_event_id: str = Field("", description="ID of the triggering event")
    actor: str = Field("system", description="Entity or user that caused the transition")
    session_id: str = Field("", description="Optional session ID")
    goal_id: str = Field("", description="Optional goal ID")
    reason: str = Field("", description="Reason for transition")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional metadata")


class EmitRequest(BaseModel):
    event_id: str = Field(..., description="Unique event ID")
    parent_event_ids: List[str] = Field(default_factory=list)
    goal_id: str = Field("", description="Optional goal ID")
    session_id: str = Field("", description="Optional session ID")
    correlation_id: str = Field("", description="Optional correlation ID")
    timestamp_utc: Optional[float] = Field(None, description="UTC timestamp (defaults to current time)")
    actor: str = Field("system", description="Actor triggering the event")
    subsystem: str = Field("system", description="Originating subsystem")
    event_type: str = Field(..., description="Name of the EventType enum member")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event payload")
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    status: str = Field("PENDING")
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/observe", summary="Record a new observation")
def record_observation(req: ObserveRequest) -> Dict[str, Any]:
    """Records an observation event and persists it to the ledger."""
    try:
        wse = WSECoordinator.get_instance()
        obs = wse.record_observation(
            source=req.source,
            subject=req.subject,
            predicate=req.predicate,
            value=req.value,
            confidence=req.confidence,
            session_id=req.session_id,
            goal_id=req.goal_id,
            metadata=req.metadata,
        )
        return {"status": "ok", "observation": obs.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/transition", summary="Record a state transition")
def record_transition(req: TransitionRequest) -> Dict[str, Any]:
    """Records an entity state transition and persists it to the ledger."""
    try:
        wse = WSECoordinator.get_instance()
        trans = wse.record_transition(
            entity_id=req.entity_id,
            entity_type=req.entity_type,
            from_state=req.from_state,
            to_state=req.to_state,
            trigger_event_id=req.trigger_event_id,
            actor=req.actor,
            session_id=req.session_id,
            goal_id=req.goal_id,
            reason=req.reason,
            metadata=req.metadata,
        )
        return {"status": "ok", "transition": trans.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/emit", summary="Publish a raw LedgerEvent")
def emit_event(req: EmitRequest) -> Dict[str, Any]:
    """Publishes an arbitrary LedgerEvent to the WSEEventBus."""
    import time
    try:
        # Coerce event_type string to EventType
        try:
            etype = EventType(req.event_type)
        except ValueError:
            # Fallback to lookup by name or raise
            try:
                etype = EventType[req.event_type]
            except KeyError:
                raise HTTPException(status_code=400, detail=f"Invalid event_type: {req.event_type}")

        event = LedgerEvent(
            event_id=req.event_id,
            parent_event_ids=req.parent_event_ids,
            goal_id=req.goal_id,
            session_id=req.session_id,
            correlation_id=req.correlation_id,
            timestamp_utc=req.timestamp_utc or time.time(),
            actor=req.actor,
            subsystem=req.subsystem,
            event_type=etype,
            payload=req.payload,
            confidence=req.confidence,
            status=req.status,
            metadata=req.metadata,
        )
        wse = WSECoordinator.get_instance()
        wse.emit(event)
        return {"status": "ok", "event_id": event.event_id}
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/timeline", summary="Query timeline events")
def get_timeline(
    t_start: float = Query(..., description="Start UTC timestamp"),
    t_end: float = Query(..., description="End UTC timestamp"),
    event_type: Optional[str] = Query(None, description="Filter by EventType string"),
) -> Dict[str, Any]:
    """Retrieves all timeline events within the specified time window."""
    try:
        etype = None
        if event_type:
            try:
                etype = EventType(event_type)
            except ValueError:
                try:
                    etype = EventType[event_type]
                except KeyError:
                    raise HTTPException(status_code=400, detail=f"Invalid event_type: {event_type}")

        wse = WSECoordinator.get_instance()
        events = wse.timeline.between(t_start, t_end, event_type=etype)
        return {"status": "ok", "events": [e.to_dict() for e in events]}
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history/{entity_id}", summary="Retrieve transition history of an entity")
def get_entity_history(entity_id: str) -> Dict[str, Any]:
    """Returns the state transition history of a specific entity."""
    try:
        wse = WSECoordinator.get_instance()
        history = wse.timeline.history_of(entity_id)
        return {"status": "ok", "history": [t.to_dict() for t in history]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/diff", summary="Query world state diff between two points")
def get_world_diff(
    t1: float = Query(..., description="First UTC timestamp"),
    t2: float = Query(..., description="Second UTC timestamp"),
) -> Dict[str, Any]:
    """Computes the difference in world state between t1 and t2."""
    try:
        wse = WSECoordinator.get_instance()
        report = wse.diff(t1, t2)
        return {"status": "ok", "diff": report.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
