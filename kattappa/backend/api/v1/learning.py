"""REST API Router for Learning & Memory Update Framework (Program 7).
"""
from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.learning.learning_engine import LearningEngine
from backend.core.reflection.models import LearningCandidate

router = APIRouter(prefix="/learning", tags=["Learning Framework"])
_engine = LearningEngine.get_instance()


class SubmitCandidateRequest(BaseModel):
    candidate_id: str
    target_type: str
    explanation: str
    proposed_update: Dict[str, Any]
    confidence: float = 1.0
    priority: str = "Medium"
    evidence_count: int = Field(default=1, description="Count of occurrences")


@router.post("/queue", summary="Queue a learning candidate for safety and confidence filters")
def submit_learning_candidate(req: SubmitCandidateRequest) -> Dict[str, Any]:
    """Submits candidate proposal, checking safety, confidence, and conflict rules."""
    try:
        candidate = LearningCandidate(
            candidate_id=req.candidate_id,
            target_type=req.target_type,
            explanation=req.explanation,
            proposed_update=req.proposed_update,
            confidence=req.confidence,
            priority=req.priority,
        )

        res = _engine.submit_candidate(candidate, req.evidence_count)

        return {
            "status": "ok",
            "candidate_id": res.candidate_id,
            "lifecycle_status": res.status,
            "confidence": res.confidence,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/approve/{candidate_id}", summary="Manually approve learning candidate")
def approve_learning_candidate(candidate_id: str) -> Dict[str, Any]:
    """Approves a pending candidate and applies consolidated changes to config variables."""
    success = _engine.approve_candidate(candidate_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Pending candidate '{candidate_id}' not found.")
    return {"status": "ok", "candidate_id": candidate_id}


@router.post("/reject/{candidate_id}", summary="Manually reject learning candidate")
def reject_learning_candidate(candidate_id: str) -> Dict[str, Any]:
    """Rejects and quenches a pending recommendation candidate."""
    success = _engine.reject_candidate(candidate_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Pending candidate '{candidate_id}' not found.")
    return {"status": "ok", "candidate_id": candidate_id}


@router.post("/rollback/{version_id}", summary="Rollback memory updates version")
def rollback_learning_version(version_id: str) -> Dict[str, Any]:
    """Rolls back applied consolidated changes to their previous values."""
    success = _engine.rollback_version(version_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found.")
    return {"status": "ok", "version_id": version_id}


@router.get("/status", summary="Get learning candidate queue status")
def get_learning_status() -> Dict[str, Any]:
    """Retrieves all candidates registered in the queue."""
    candidates = _engine.get_all_candidates()
    return {
        "status": "ok",
        "candidates": [
            {
                "candidate_id": c.candidate_id,
                "target_type": c.target_type,
                "lifecycle_status": c.status,
                "confidence": c.confidence,
                "priority": c.priority,
            }
            for c in candidates
        ]
    }


@router.get("/history", summary="Get learning consolidation history logs")
def get_learning_history() -> Dict[str, Any]:
    """Returns lists of learning audit logs and active policy configurations."""
    return {
        "status": "ok",
        "active_configuration": _engine.consolidator.active_config,
        "audit_logs": [
            {
                "entry_id": log.entry_id,
                "candidate_id": log.candidate_id,
                "target_type": log.target_type,
                "confidence": log.confidence,
                "timestamp": log.timestamp,
                "notes": log.notes,
            }
            for log in _engine.audit_log
        ]
    }
