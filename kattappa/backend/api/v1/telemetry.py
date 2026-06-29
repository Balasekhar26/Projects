from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
from backend.core.ledger.telemetry.metrics_collector import MetricsCollector
from backend.core.ledger.telemetry.telemetry_service import TelemetryService
from backend.core.cos.kernel import KERNEL

telemetry_router = APIRouter(tags=["Telemetry"])

GLOBAL_COLLECTOR = MetricsCollector()
GLOBAL_TELEMETRY = TelemetryService(GLOBAL_COLLECTOR)


class RecordMetricRequest(BaseModel):
    metric_name: str
    value: float


@telemetry_router.get("/telemetry/report")
def get_telemetry_report() -> Dict[str, Any]:
    """Generates the rolling operational metrics report."""
    return GLOBAL_TELEMETRY.generate_report()


@telemetry_router.post("/telemetry/record")
def record_metric(request: RecordMetricRequest) -> Dict[str, Any]:
    """Records a live operational metric."""
    GLOBAL_COLLECTOR.record(request.metric_name, request.value)
    return {"status": "success", "metric": request.metric_name, "value": request.value}


@telemetry_router.get("/telemetry/events")
def get_ledger_events() -> List[Dict[str, Any]]:
    """Retrieves all events stored in the global execution ledger."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    events = KERNEL.ledger.query({})
    return [e.to_dict() for e in events]


@telemetry_router.get("/telemetry/events/{event_id}/ancestors")
def get_event_ancestors(event_id: str) -> List[Dict[str, Any]]:
    """Retrieves all ancestors of the target event."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    events = KERNEL.ledger.ancestors(event_id)
    return [e.to_dict() for e in events]


@telemetry_router.get("/telemetry/events/{event_id}/descendants")
def get_event_descendants(event_id: str) -> List[Dict[str, Any]]:
    """Retrieves all descendants of the target event."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    events = KERNEL.ledger.descendants(event_id)
    return [e.to_dict() for e in events]
