"""REST API Router for Reflection Engine (Program 6).
"""
from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.reflection.models import ExecutionRecord
from backend.core.reflection.reflection_engine import ReflectionEngine

router = APIRouter(prefix="/reflection", tags=["Reflection Engine"])
_engine = ReflectionEngine.get_instance()


class ExecutionRecordRequest(BaseModel):
    session_id: str
    plan_id: str
    status: str
    total_duration: float
    task_durations: Dict[str, float] = Field(default_factory=dict)
    retries: Dict[str, int] = Field(default_factory=dict)
    failures: List[Dict[str, Any]] = Field(default_factory=list)
    variables_snapshot: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)


@router.post("/review", summary="Submit finished ExecutionRecord and get review report")
def process_record_reflection(req: ExecutionRecordRequest) -> Dict[str, Any]:
    """Processes finished execution record telemetry and compiles reviews, failure classifications, and scores."""
    try:
        record = ExecutionRecord(
            session_id=req.session_id,
            plan_id=req.plan_id,
            status=req.status,
            total_duration=req.total_duration,
            task_durations=req.task_durations,
            retries=req.retries,
            failures=req.failures,
            variables_snapshot=req.variables_snapshot,
            outputs=req.outputs,
        )

        review = _engine.process_execution(record)

        return {
            "status": "ok",
            "session_id": review.session_id,
            "review": {
                "success_rate": review.success_rate,
                "avg_latency": review.avg_latency,
                "total_retries": review.total_retries,
                "failure_category": review.failure_category,
                "bottleneck_nodes": review.bottleneck_nodes,
                "parallelization_score": review.parallelization_score,
                "quality_score": review.quality_score,
            }
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/candidates/{session_id}", summary="Get learning candidates for a session")
def get_learning_candidates(session_id: str) -> Dict[str, Any]:
    """Retrieves compiled learning recommendations and updates candidates for a target session."""
    candidates = _engine.get_candidates(session_id)
    return {
        "status": "ok",
        "session_id": session_id,
        "candidates": [
            {
                "candidate_id": c.candidate_id,
                "target_type": c.target_type,
                "explanation": c.explanation,
                "proposed_update": c.proposed_update,
                "confidence": c.confidence,
                "priority": c.priority,
                "status": c.status,
            }
            for c in candidates
        ]
    }


@router.get("/history", summary="Get completed execution reviews history")
def get_reviews_history() -> Dict[str, Any]:
    """Returns lists of completed session execution reviews."""
    reviews = _engine.get_all_reviews()
    return {
        "status": "ok",
        "history": [
            {
                "session_id": r.session_id,
                "success_rate": r.success_rate,
                "avg_latency": r.avg_latency,
                "total_retries": r.total_retries,
                "failure_category": r.failure_category,
                "quality_score": r.quality_score,
            }
            for r in reviews
        ]
    }
