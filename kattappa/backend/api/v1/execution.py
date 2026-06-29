"""REST API Router for Stateful Execution Engine (Program 5G-6).
"""
from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.core.execution.execution_engine import ExecutionEngine
from backend.core.execution.execution_state import ExecutionState

router = APIRouter(prefix="/execution", tags=["Execution Engine"])
_engine = ExecutionEngine()


class StartExecutionRequest(BaseModel):
    plan_id: str
    steps: List[Dict[str, Any]] = Field(..., description="Linear plan steps sequence")
    initial_variables: Dict[str, Any] = Field(default_factory=dict, description="Initial context variables")
    max_retries: int = Field(default=2, description="Max retries per step")


class SessionActionRequest(BaseModel):
    session_id: str


class RecoverExecutionRequest(BaseModel):
    session_id: str
    steps: List[Dict[str, Any]] = Field(..., description="Linear plan steps sequence to reconstruct graph")


@router.post("/start", summary="Start plan execution session")
def start_plan_execution(req: StartExecutionRequest) -> Dict[str, Any]:
    """Compiles steps to plan graph, validates, schedules, and triggers runtime execution."""
    try:
        from backend.core.planning.plan_graph import PlanCompiler
        from backend.core.planning.task import Plan, Operator

        steps = []
        for step in req.steps:
            steps.append(Operator(
                operator_id=step["operator_id"],
                name=step["name"],
                parameters=step.get("parameters", {}),
                preconditions=step.get("preconditions", {}),
                effects=step.get("effects", {}),
            ))

        plan = Plan(
            plan_id=req.plan_id,
            goal_id="unknown_goal",
            steps=steps,
        )

        graph = PlanCompiler.compile_plan_to_graph(plan)
        session_id = _engine.start_execution(graph, req.initial_variables, req.max_retries)
        session = _engine.sessions[session_id]

        return {
            "status": "ok",
            "session_id": session_id,
            "execution_status": session.status.value,
            "completed_nodes": list(session.completed_nodes),
            "failed_nodes": list(session.failed_nodes),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/pause", summary="Pause execution session")
def pause_plan_execution(req: SessionActionRequest) -> Dict[str, Any]:
    """Pauses active execution and saves state to durable checkpoint."""
    if req.session_id not in _engine.sessions:
        raise HTTPException(status_code=404, detail=f"Session '{req.session_id}' not found.")
    _engine.pause_execution(req.session_id)
    return {"status": "ok", "session_id": req.session_id, "execution_status": _engine.sessions[req.session_id].status.value}


@router.post("/resume", summary="Resume paused execution session")
def resume_plan_execution(req: RecoverExecutionRequest) -> Dict[str, Any]:
    """Resumes a paused execution using reconstructed graph structure."""
    if req.session_id not in _engine.sessions:
        raise HTTPException(status_code=404, detail=f"Session '{req.session_id}' not found.")

    try:
        from backend.core.planning.plan_graph import PlanCompiler
        from backend.core.planning.task import Plan, Operator

        steps = []
        for step in req.steps:
            steps.append(Operator(
                operator_id=step["operator_id"],
                name=step["name"],
                parameters=step.get("parameters", {}),
                preconditions=step.get("preconditions", {}),
                effects=step.get("effects", {}),
            ))

        plan = Plan(plan_id="plan_id", goal_id="unknown_goal", steps=steps)
        graph = PlanCompiler.compile_plan_to_graph(plan)

        _engine.resume_execution(req.session_id, graph)
        return {"status": "ok", "session_id": req.session_id, "execution_status": _engine.sessions[req.session_id].status.value}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/cancel", summary="Cancel execution session")
def cancel_plan_execution(req: SessionActionRequest) -> Dict[str, Any]:
    """Cancels active execution sessions and cleans checkpoints."""
    if req.session_id not in _engine.sessions:
        raise HTTPException(status_code=404, detail=f"Session '{req.session_id}' not found.")
    _engine.cancel_execution(req.session_id)
    return {"status": "ok", "session_id": req.session_id, "execution_status": _engine.sessions[req.session_id].status.value}


@router.post("/recover", summary="Recover execution from checkpoint")
def recover_plan_execution(req: RecoverExecutionRequest) -> Dict[str, Any]:
    """Hydrates checkpoint variables and resumes execution from saved state files."""
    try:
        from backend.core.planning.plan_graph import PlanCompiler
        from backend.core.planning.task import Plan, Operator

        steps = []
        for step in req.steps:
            steps.append(Operator(
                operator_id=step["operator_id"],
                name=step["name"],
                parameters=step.get("parameters", {}),
                preconditions=step.get("preconditions", {}),
                effects=step.get("effects", {}),
            ))

        plan = Plan(plan_id="plan_id", goal_id="unknown_goal", steps=steps)
        graph = PlanCompiler.compile_plan_to_graph(plan)

        session_id = _engine.trigger_recovery(req.session_id, graph)
        if not session_id:
            raise HTTPException(status_code=404, detail=f"No checkpoints found for session '{req.session_id}'")

        session = _engine.sessions[session_id]
        return {
            "status": "ok",
            "session_id": session_id,
            "execution_status": session.status.value,
            "completed_nodes": list(session.completed_nodes),
            "failed_nodes": list(session.failed_nodes),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status/{session_id}", summary="Get session execution details")
def get_execution_status(session_id: str) -> Dict[str, Any]:
    """Retrieves session state, timings, completed nodes list, and variables state."""
    session = _engine.sessions.get(session_id)
    context = _engine.contexts.get(session_id)

    if not session or not context:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    return {
        "status": "ok",
        "session_id": session_id,
        "execution_status": session.status.value,
        "progress": session.progress,
        "completed_nodes": list(session.completed_nodes),
        "failed_nodes": list(session.failed_nodes),
        "variables": context.variables,
        "outputs": context.outputs,
    }
