"""FastAPI Superbench Telemetry and Validation Router."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from backend.core.superbench_engine import SuperbenchEngine

superbench_router = APIRouter(prefix="/superbench", tags=["superbench"])


class TaskExecutionResponse(BaseModel):
    id: str
    task_id: str
    timestamp: float
    prompt: str
    intent: str
    activated_components: str
    tool_usage: str
    memory_usage: str
    planning_strategy: str
    confidence: float
    latency: float
    result: str
    failure_mode: Optional[str] = None
    root_cause: Optional[str] = None
    proposed_fix: Optional[str] = None
    lessons_learned: Optional[str] = None


@superbench_router.post("/generate")
def generate_tasks_api() -> Dict[str, Any]:
    """Populates 1000 benchmark tasks across 20 categories."""
    try:
        count = SuperbenchEngine.generate_benchmark_tasks()
        return {"status": "success", "message": f"Generated {count} superbench tasks successfully.", "count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@superbench_router.get("/tasks")
def list_tasks_api(category: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Lists generated benchmark tasks, optionally filtered by category."""
    try:
        tasks = SuperbenchEngine.list_tasks(category)
        return {"status": "success", "tasks": tasks, "count": len(tasks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@superbench_router.post("/run/{task_id}", response_model=TaskExecutionResponse)
def run_task_api(task_id: str) -> Dict[str, Any]:
    """Runs a single benchmark task and logs the results in telemetry database."""
    try:
        result = SuperbenchEngine.execute_task(task_id)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@superbench_router.get("/results")
def list_results_api() -> Dict[str, Any]:
    """Retrieves all historical benchmark results."""
    try:
        results = SuperbenchEngine.get_results()
        return {"status": "success", "results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@superbench_router.get("/stats")
def get_stats_api() -> Dict[str, Any]:
    """Retrieves aggregated validation metrics for React gauges."""
    try:
        stats = SuperbenchEngine.get_statistics()
        return {"status": "success", "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
