"""Provenance Engine REST API — Program 5A.

Endpoints:
    GET  /api/v1/provenance/source/{source_id} — Get source reputation and info
    POST /api/v1/provenance/source             — Register or update a source
    GET  /api/v1/provenance/entity/{entity_id} — Get full citation chain and evidence for a KG node/edge
    POST /api/v1/provenance/evidence           — Add manual evidence for an entity
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.provenance.coordinator import ProvenanceCoordinator

router = APIRouter(prefix="/provenance", tags=["Provenance"])


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class RegisterSourceRequest(BaseModel):
    source_id: str = Field(..., description="Unique ID of the source")
    name: str = Field(..., description="Display/Source name")
    source_type: str = Field(..., description="Type of the source (e.g. model, web, user, tool)")
    base_reputation: float = Field(0.3, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AddEvidenceRequest(BaseModel):
    target_id: str = Field(..., description="Target node_id or edge_id in the Knowledge Graph")
    source_id: str = Field(..., description="Source ID providing the evidence")
    evidence_level: str = Field(..., description="Level of evidence (e.g. LLM_REASONING, TEST_RESULT, REAL_WORLD)")
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    verification_state: str = Field("UNVERIFIED", description="UNVERIFIED, CORROBORATED, or CONTRADICTED")
    context_citation: str = Field("", description="Optional citation context/URL/message_id")
    supports: bool = Field(True, description="True if evidence supports the claim, False if refutes")
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/source/{source_id}", summary="Get source info and reputation")
def get_source(source_id: str) -> Dict[str, Any]:
    """Retrieves metadata and trust statistics for a registered source."""
    prov = ProvenanceCoordinator.get_instance()
    src = prov.sources.get_source(source_id)
    if not src:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    return {"status": "ok", "source": src.to_dict()}


@router.post("/source", summary="Register or update a source")
def register_source(req: RegisterSourceRequest) -> Dict[str, Any]:
    """Registers or updates information source details in the registry."""
    try:
        prov = ProvenanceCoordinator.get_instance()
        src = prov.sources.register_source(
            source_id=req.source_id,
            name=req.name,
            source_type=req.source_type,
            base_reputation=req.base_reputation,
            metadata=req.metadata,
        )
        return {"status": "ok", "source": src.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/entity/{entity_id}", summary="Get evidence and citation chain for a KG entity")
def get_entity_provenance(entity_id: str) -> Dict[str, Any]:
    """Returns the complete list of evidence items and a formatted Markdown citation chain for a node or edge."""
    prov = ProvenanceCoordinator.get_instance()
    evidence_list = prov.kg.get_evidence_for_target(entity_id)
    markdown_citation = prov.citations.generate_markdown_citation_chain(entity_id)
    return {
        "status": "ok",
        "target_id": entity_id,
        "evidence": [ev.to_dict() for ev in evidence_list],
        "citation_chain": markdown_citation,
    }


@router.post("/evidence", summary="Add manual evidence for a KG entity")
def add_evidence(req: AddEvidenceRequest) -> Dict[str, Any]:
    """Adds a new evidence record supporting or refuting a target KG node/edge."""
    try:
        prov = ProvenanceCoordinator.get_instance()
        ev = prov.add_manual_evidence(
            target_id=req.target_id,
            source_id=req.source_id,
            evidence_level=req.evidence_level,
            confidence=req.confidence,
            verification_state=req.verification_state,
            context_citation=req.context_citation,
            supports=req.supports,
            metadata=req.metadata,
        )
        return {"status": "ok", "evidence": ev.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
