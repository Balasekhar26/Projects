"""REST API Router for Context Management Platform (Program 9).
"""
from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.context.context_engine import ContextEngine

router = APIRouter(prefix="/context", tags=["Context Engine"])
_engine = ContextEngine.get_instance()


class AssembleContextRequest(BaseModel):
    session_id: str
    query: str
    bypass_cache: bool = Field(default=False, description="Ignore cache checks")


@router.post("/assemble", summary="Assemble context bundle for prompt construction")
def assemble_context_bundle(req: AssembleContextRequest) -> Dict[str, Any]:
    """Compiles working, episodic, and semantic memories into one provider-agnostic ContextBundle."""
    try:
        bundle = _engine.assemble_context(
            session_id=req.session_id,
            query=req.query,
            bypass_cache=req.bypass_cache,
        )

        prompt_payload = bundle.to_provider_prompt()

        return {
            "status": "ok",
            "session_id": bundle.session_id,
            "total_tokens": bundle.total_tokens,
            "prompt_payload": prompt_payload,
            "items_count": len(bundle.items),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/clear_cache", summary="Evict the LRU/TTL context retrieval cache")
def clear_context_cache() -> Dict[str, Any]:
    """Flushes all cached context bundles."""
    _engine.cache.clear()
    return {"status": "ok"}
