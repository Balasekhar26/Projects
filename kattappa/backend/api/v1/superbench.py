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
    run_id: str
    trace_id: str
    workspace_id: str
    memory_mode: str
    memory_backend: str
    started_at: float
    completed_at: Optional[float] = None
    status: str
    failure_category: Optional[str] = None
    exception_fingerprint: Optional[str] = None
    resource_snapshot: Dict[str, Any]
    warnings: List[str]
    retry_eligible: bool
    recovery_action: Optional[str] = None
    duration: float
    response: Optional[str] = None


class TaskExecutionRequest(BaseModel):
    memory_mode: str = "isolated"
    production_authorized: bool = False
    vector_enabled: bool = True
    simulate_vector_failure: bool = False


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
def run_task_api(task_id: str, request: TaskExecutionRequest | None = None) -> Dict[str, Any]:
    """Runs a single benchmark task and logs the results in telemetry database."""
    try:
        options = request or TaskExecutionRequest()
        result = SuperbenchEngine.execute_task(task_id, **options.model_dump())
        return result
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@superbench_router.get("/runs/{run_id}", response_model=TaskExecutionResponse)
def get_run_api(run_id: str) -> Dict[str, Any]:
    result = SuperbenchEngine.get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Superbench run not found")
    return result


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
