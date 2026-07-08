"""REST API Router for Cognitive Integration Layer (Program 8).
"""
from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.integration.orchestrator import CognitiveOrchestrator
from backend.core.integration.tracing import CognitiveTracer

router = APIRouter(prefix="/integration", tags=["Cognitive Integration"])
_orchestrator = CognitiveOrchestrator.get_instance()
_tracer = CognitiveTracer.get_instance()


class StepRequest(BaseModel):
    operator_id: str
    name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    preconditions: Dict[str, Any] = Field(default_factory=dict)
    effects: Dict[str, Any] = Field(default_factory=dict)


class RunLoopRequest(BaseModel):
    plan_id: str
    steps: List[StepRequest]
    initial_variables: Dict[str, Any] = Field(default_factory=dict)
    max_retries: int = Field(default=1, description="Max retries per step")


@router.post("/run", summary="Trigger complete end-to-end cognitive loop run")
def run_cognitive_loop_action(req: RunLoopRequest) -> Dict[str, Any]:
    """Compiles a plan, runs execution, processes reflection, applies learning candidates, and updates memory."""
    try:
        from backend.core.planning.task import Operator

        steps = []
        for step in req.steps:
            steps.append(Operator(
                operator_id=step.operator_id,
                name=step.name,
                parameters=step.parameters,
                preconditions=step.preconditions,
                effects=step.effects,
            ))

        result = _orchestrator.run_cognitive_loop(
            plan_id=req.plan_id,
            steps=steps,
            initial_variables=req.initial_variables,
            max_retries=req.max_retries,
        )

        return {
            "status": "ok",
            "result": result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/traces/{trace_id}", summary="Get distributed spans and telemetry timeline for trace ID")
def get_cognitive_trace_details(trace_id: str) -> Dict[str, Any]:
    """Returns trace span history log sequence for audit and telemetry visualization."""
    history = _tracer.get_trace_history(trace_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"Trace ID '{trace_id}' not found.")
    return {
        "status": "ok",
        "trace_id": trace_id,
        "spans": history,
    }
