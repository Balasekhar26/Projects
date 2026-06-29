"""MCE REST API — Program 3.

Endpoints:
    POST /api/v1/mce/run       — trigger an immediate consolidation cycle
    GET  /api/v1/mce/status    — scheduler state and last cycle report
    GET  /api/v1/mce/duplicates — current duplicate cluster report
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.mce.consolidation_engine import MCEConsolidationEngine
from backend.core.mce.duplicate_detector import MCEDuplicateDetector
from backend.core.mce.scheduler import MCEScheduler

router = APIRouter(prefix="/mce", tags=["MCE"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    importance_floor: float = Field(0.65, ge=0.0, le=1.0, description="Minimum score for semantic promotion")
    archive_after_days: float = Field(30.0, ge=1.0, description="Days before archiving stale episodes")
    episode_limit: int = Field(2000, ge=1, le=10000, description="Max episodes to process per cycle")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/run", summary="Trigger immediate consolidation cycle")
def run_consolidation(req: RunRequest = RunRequest()) -> Dict[str, Any]:
    """Runs the full 6-stage MCE pipeline synchronously and returns a report."""
    try:
        report = MCEConsolidationEngine.run_cycle(
            importance_floor=req.importance_floor,
            archive_after_days=req.archive_after_days,
            episode_limit=req.episode_limit,
        )
        return {"status": "ok", "report": report.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status", summary="Scheduler state and last cycle report")
def get_status() -> Dict[str, Any]:
    """Returns the MCEScheduler's current state."""
    scheduler = MCEScheduler.get_instance()
    return {"status": "ok", "scheduler": scheduler.get_status()}


@router.get("/duplicates", summary="Duplicate cluster report")
def get_duplicates(limit: int = 500, jaccard_threshold: float = 0.85) -> Dict[str, Any]:
    """Scans episodic memory and returns the current duplicate analysis."""
    try:
        report = MCEDuplicateDetector.detect(
            jaccard_threshold=jaccard_threshold,
            limit=limit,
        )
        return {
            "status": "ok",
            "exact_dupe_count": report.exact_dupe_count,
            "near_dupe_count": report.near_dupe_count,
            "unique_count": report.unique_count,
            "near_duplicate_clusters": report.near_duplicate_clusters,
            "exact_duplicate_ids": report.exact_duplicate_ids,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
