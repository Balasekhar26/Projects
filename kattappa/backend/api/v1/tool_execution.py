"""REST API Router for Execution and Tool Framework (Program 11).
"""
from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.execution.tool_engine import ToolEngine

router = APIRouter(prefix="/tool", tags=["Tool Execution Engine"])
_engine = ToolEngine.get_instance()


class ExecuteToolRequest(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


@router.post("/execute", summary="Execute system tool invocation through framework gates")
def execute_system_tool(req: ExecuteToolRequest) -> Dict[str, Any]:
    """Runs target tool, applying capability routing, permission gates, timeouts, and schemas validation."""
    try:
        res = _engine.execute(req.name, req.arguments)

        return {
            "status": "ok" if res.status == "ok" else "error",
            "tool_name": res.tool_name,
            "data": res.data,
            "error": res.error,
            "latency": res.execution_time,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/audit", summary="Get tool execution audit logs history")
def get_tool_audit_history() -> Dict[str, Any]:
    """Retrieves list of audited tool runs history logs."""
    return {
        "status": "ok",
        "history": _engine.audit.get_history(),
    }
