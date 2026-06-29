"""Planning Stack Router (Program 5G-1).

Exposes REST endpoints for goal configuration, dependency paths, and status tracking.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.planning.goal import Goal, GoalRegistry

router = APIRouter(prefix="/planning", tags=["Planning"])

# Single in-memory GoalRegistry instance for the API router lifecycle
_registry = GoalRegistry()


class GoalConfig(BaseModel):
    goal_id: str = Field(..., description="Unique Goal ID")
    name: str = Field(..., description="Goal name")
    priority: Optional[str] = Field("Medium", description="Goal priority")
    deadline: Optional[float] = Field(None, description="Epoch deadline timestamp")
    importance: Optional[float] = Field(1.0, description="Goal importance weight")
    constraints: Optional[List[str]] = Field(None, description="Plan constraint flags")
    dependencies: Optional[List[str]] = Field(None, description="Goal parent dependencies")
    owner: Optional[str] = Field(None, description="Target execution owner agent")
    reward: Optional[float] = Field(100.0, description="Utility success payoff")
    failure_cost: Optional[float] = Field(-50.0, description="Utility failure cost penalty")


class UpdateGoalStatusRequest(BaseModel):
    status: str = Field(..., description="New status value (Pending, InProgress, Completed, Failed)")


@router.post("/goals", summary="Register a target goal")
def register_goal(req: GoalConfig) -> Dict[str, Any]:
    """Registers a goal in the planning registry, checking for cycles and dependency validity."""
    try:
        goal = Goal(
            goal_id=req.goal_id,
            name=req.name,
            priority=req.priority or "Medium",
            deadline=req.deadline,
            importance=req.importance or 1.0,
            constraints=req.constraints or [],
            dependencies=req.dependencies or [],
            owner=req.owner,
            reward=req.reward or 100.0,
            failure_cost=req.failure_cost or -50.0,
        )
        _registry.register_goal(goal)
        return {"status": "ok", "goal_id": goal.goal_id}
    except ValueError as val_exc:
        raise HTTPException(status_code=400, detail=str(val_exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/goals", summary="List registered goals")
def list_goals() -> Dict[str, Any]:
    """Lists all registered goals along with their current execution status."""
    goals = _registry.list_goals()
    return {
        "status": "ok",
        "goals": [
            {
                "goal_id": g.goal_id,
                "name": g.name,
                "priority": g.priority,
                "deadline": g.deadline,
                "importance": g.importance,
                "constraints": g.constraints,
                "dependencies": g.dependencies,
                "owner": g.owner,
                "status": g.status,
                "reward": g.reward,
                "failure_cost": g.failure_cost,
            }
            for g in goals
        ]
    }


@router.put("/goals/{goal_id}/status", summary="Update goal execution status")
def update_goal_status(goal_id: str, req: UpdateGoalStatusRequest) -> Dict[str, Any]:
    """Updates the status of a target registered goal."""
    try:
        _registry.update_goal_status(goal_id, req.status)
        return {"status": "ok", "goal_id": goal_id, "new_status": req.status}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Goal '{goal_id}' not found.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/goals/order", summary="Get topological planning order")
def get_planning_order() -> Dict[str, Any]:
    """Resolves goal dependencies and returns topologically sorted Goal IDs."""
    try:
        order = _registry.get_topological_order()
        return {"status": "ok", "topological_order": order}
    except ValueError as val_exc:
        raise HTTPException(status_code=400, detail=str(val_exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/goals/trace", summary="Get dependency visualizer trace")
def get_dependency_trace() -> Dict[str, Any]:
    """Returns a formatted markdown trace detailing goal dependencies and statuses."""
    try:
        trace = _registry.generate_dependency_trace()
        return {"status": "ok", "trace": trace}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
