"""REST API Router for Tool Hardening Controls (Program 11.5).
"""
from __future__ import annotations

from typing import Dict
from fastapi import APIRouter, HTTPException

from backend.core.execution.approval import HumanApprovalPipeline
from backend.core.execution.circuit_breaker import ToolCircuitBreaker

router = APIRouter(prefix="/tool", tags=["Tool Hardening Controls"])
_approval = HumanApprovalPipeline.get_instance()
_circuit = ToolCircuitBreaker.get_instance()


@router.post("/approve/{request_id}", summary="Grant manual approval for a gated tool request")
def approve_gated_request(request_id: str) -> Dict[str, str]:
    if request_id not in _approval.requests:
        raise HTTPException(status_code=404, detail="Request ID not found.")
    _approval.approve(request_id)
    return {"status": "ok", "message": f"Request {request_id} approved."}


@router.post("/reject/{request_id}", summary="Reject a gated tool request")
def reject_gated_request(request_id: str) -> Dict[str, str]:
    if request_id not in _approval.requests:
        raise HTTPException(status_code=404, detail="Request ID not found.")
    _approval.reject(request_id)
    return {"status": "ok", "message": f"Request {request_id} rejected."}


@router.get("/circuit_status", summary="Get status of tool circuit breakers")
def get_circuit_status() -> Dict[str, Dict[str, int]]:
    return {
        "failures": dict(_circuit.failures),
        "tripped": {k: int(v) for k, v in _circuit.tripped_at.items()},
    }
