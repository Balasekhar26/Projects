"""World Model API Router — /world/* endpoints.

Provides CRUD access to the WorldModel causal knowledge graph:
entity management, relation management, belief state inspection,
causal log queries, and conflict management.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

world_router = APIRouter(tags=["World Model"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class WorldEntityRequest(BaseModel):
    name: str
    type: str = "other"
    status: str = ""
    attributes: dict[str, Any] = {}
    confidence: float = 0.7
    confidence_state: str = "INFERRED"


class WorldRelationRequest(BaseModel):
    src: str
    dst: str
    relation: str = "related"


class WorldQueryRequest(BaseModel):
    query: str
    limit: int = 10


class WorldConflictResolveRequest(BaseModel):
    resolution: str  # RESOLVED_NEW | RESOLVED_OLD | DISCARDED


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

@world_router.post("/world/entities")
def world_add_entity(req: WorldEntityRequest) -> dict[str, Any]:
    """Add or update an entity in the world knowledge graph."""
    from backend.core.world_model import WorldModel
    try:
        result = WorldModel.add_entity(
            req.name,
            req.type,
            status=req.status,
            attributes=req.attributes,
            confidence=req.confidence,
            confidence_state=req.confidence_state,
        )
        return {"entity": result}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@world_router.get("/world/entities")
def world_list_entities() -> dict[str, Any]:
    """List all entities in the world knowledge graph."""
    from backend.core.world_model import WorldModel
    entities = WorldModel.entities()
    return {"items": entities, "count": len(entities)}


@world_router.get("/world/entities/{name}")
def world_get_entity(name: str) -> dict[str, Any]:
    """Get a single entity by name."""
    from backend.core.world_model import WorldModel
    entity = WorldModel.get(name)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
    return {"entity": entity}


@world_router.delete("/world/entities/{name}")
def world_remove_entity(name: str) -> dict[str, Any]:
    """Remove an entity from the world graph."""
    from backend.core.world_model import WorldModel
    removed = WorldModel.remove(name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
    return {"removed": True, "name": name}


# ---------------------------------------------------------------------------
# Relations
# ---------------------------------------------------------------------------

@world_router.post("/world/relations")
def world_add_relation(req: WorldRelationRequest) -> dict[str, Any]:
    """Add a directional relation between two entities."""
    from backend.core.world_model import WorldModel
    try:
        WorldModel.add_relation(req.src, req.dst, req.relation)
        return {"added": True, "src": req.src, "dst": req.dst, "relation": req.relation}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@world_router.get("/world/relations")
def world_list_relations() -> dict[str, Any]:
    """List all relations in the world graph."""
    from backend.core.world_model import WorldModel
    relations = WorldModel.relations()
    return {"items": relations, "count": len(relations)}


@world_router.get("/world/entities/{name}/neighbors")
def world_get_neighbors(name: str, relation: str | None = None, direction: str = "out") -> dict[str, Any]:
    """Get neighboring entities via optional relation filter."""
    from backend.core.world_model import WorldModel
    neighbors = WorldModel.neighbors(name, relation, direction=direction)
    return {"entity": name, "neighbors": neighbors, "direction": direction}


# ---------------------------------------------------------------------------
# Belief states & causal log
# ---------------------------------------------------------------------------

@world_router.get("/world/entities/{name}/beliefs")
def world_get_belief_state(name: str) -> dict[str, Any]:
    """Get all belief states (attribute-level confidence records) for an entity."""
    from backend.core.world_model import WorldModel
    beliefs = WorldModel.get_belief_state(name)
    return {"entity": name, "beliefs": beliefs}


@world_router.get("/world/entities/{name}/causal-log")
def world_get_causal_log(name: str, limit: int = 20) -> dict[str, Any]:
    """Get the causal change history for an entity."""
    from backend.core.world_model import WorldModel
    log = WorldModel.get_causal_log(name, limit=limit)
    return {"entity": name, "log": log}


# ---------------------------------------------------------------------------
# Query (semantic search over entity names)
# ---------------------------------------------------------------------------

@world_router.post("/world/query")
def world_query(req: WorldQueryRequest) -> dict[str, Any]:
    """Query world entities relevant to a text string with 1-hop expansion."""
    from backend.core.world_model import WorldModel
    results = WorldModel.query_world_context(query_text=req.query, limit=req.limit)
    return {"results": results, "count": len(results)}


# ---------------------------------------------------------------------------
# Conflict management
# ---------------------------------------------------------------------------

@world_router.get("/world/conflicts")
def world_list_conflicts(resolution_state: str = "PENDING", limit: int = 50) -> dict[str, Any]:
    """List queued belief conflicts."""
    from backend.core.world_model import WorldModel
    conflicts = WorldModel.list_conflicts(resolution_state=resolution_state, limit=limit)
    return {"items": conflicts, "count": len(conflicts)}


@world_router.post("/world/conflicts/{conflict_id}/resolve")
def world_resolve_conflict(conflict_id: str, req: WorldConflictResolveRequest) -> dict[str, Any]:
    """Resolve a queued belief conflict."""
    from backend.core.world_model import WorldModel
    try:
        resolved = WorldModel.resolve_conflict(conflict_id, req.resolution)
        if not resolved:
            raise HTTPException(status_code=404, detail=f"Conflict '{conflict_id}' not found")
        return {"resolved": True, "conflict_id": conflict_id, "resolution": req.resolution}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@world_router.get("/world/status")
def world_status() -> dict[str, Any]:
    """World model health check: entity count, relation count, conflict count."""
    from backend.core.world_model import WorldModel
    entities = WorldModel.entities()
    relations = WorldModel.relations()
    conflicts = WorldModel.list_conflicts()
    return {
        "status": "ok",
        "entity_count": len(entities),
        "relation_count": len(relations),
        "pending_conflicts": len(conflicts),
    }
