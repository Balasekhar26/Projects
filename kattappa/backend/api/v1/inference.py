"""REST API Router for Inference Platform (Program 10).
"""
from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.inference.models import InferenceRequest
from backend.core.inference.inference_engine import InferenceEngine

router = APIRouter(prefix="/inference", tags=["Inference Engine"])
_engine = InferenceEngine.get_instance()


class ExecuteInferenceRequest(BaseModel):
    prompt: str
    system_instruction: str = Field(default="")
    required_capabilities: List[str] = Field(default_factory=list)
    max_cost: float = Field(default=0.5, description="Max cost cap in USD")
    temperature: float = Field(default=0.7)
    bypass_cache: bool = Field(default=False)


@router.post("/execute", summary="Execute LLM inference through routing and fallback chain")
def execute_inference_endpoint(req: ExecuteInferenceRequest) -> Dict[str, Any]:
    """Routes request to optimal model, executing with full failover backup chaining."""
    try:
        request = InferenceRequest(
            prompt=req.prompt,
            system_instruction=req.system_instruction,
            required_capabilities=req.required_capabilities,
            max_cost=req.max_cost,
            temperature=req.temperature,
        )

        response = _engine.execute_inference(request, bypass_cache=req.bypass_cache)

        return {
            "status": "ok",
            "text": response.text_content,
            "model_used": response.model_used,
            "cost": response.cost,
            "latency": response.latency,
            "token_usage": response.token_usage,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cost", summary="Get accumulated token costs metrics summary")
def get_inference_cost_summary() -> Dict[str, Any]:
    """Retrieves accumulated token counts and financial charges audit logs."""
    return {
        "status": "ok",
        "summary": _engine.cost_mgr.get_summary(),
    }
