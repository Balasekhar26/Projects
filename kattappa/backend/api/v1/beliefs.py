"""Belief & TMS REST API — Program 5B.

Endpoints:
    POST /api/v1/beliefs/assertion       — Process a belief assertion candidate
    GET  /api/v1/beliefs/conflict        — List all open conflicts/contradictions
    GET  /api/v1/beliefs/explain/{id}    — Retrieve justification trace explanation
    GET  /api/v1/beliefs/history/{id}    — Retrieve belief state version history
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.beliefs.coordinator import BeliefCoordinator
from backend.core.provenance.coordinator import ProvenanceCoordinator
from backend.core.provenance.models import ProvenanceEvidenceItem

router = APIRouter(prefix="/beliefs", tags=["Beliefs"])


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class AssertionRequest(BaseModel):
    subject: str = Field(..., description="Subject claim node ID")
    predicate: str = Field(..., description="Property key being asserted")
    value: Any = Field(..., description="Value asserted")
    source_id: str = Field(..., description="ID of source asserting this")
    evidence_level: str = Field(..., description="EvidenceLevel name (e.g. LLM_REASONING, TEST_RESULT)")
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    rationale: str = Field("", description="Human-readable rationale")
    dependencies: List[str] = Field(default_factory=list, description="IDs of beliefs this depends on")
    valid_until: Optional[float] = Field(None, description="Optional temporal expiry timestamp")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/assertion", summary="Process a belief assertion")
def process_assertion(req: AssertionRequest) -> Dict[str, Any]:
    """Validates an assertion, checks for conflicts, builds dependencies, and propagates truth bounds."""
    try:
        # Create a fresh EvidenceItem for the assertion
        evidence = ProvenanceEvidenceItem.create(
            source_id=req.source_id,
            evidence_level=req.evidence_level,
            confidence=req.confidence,
            supports=True,
            context_citation=req.rationale,
        )

        coord = BeliefCoordinator.get_instance()
        belief = coord.process_assertion(
            subject=req.subject,
            predicate=req.predicate,
            value=req.value,
            evidence=evidence,
            rationale=req.rationale,
            dependencies=req.dependencies,
            valid_until=req.valid_until,
        )
        return {"status": "ok", "belief": belief.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/conflict", summary="List all open conflicts")
def list_conflicts() -> Dict[str, Any]:
    """Retrieves all contradictions currently registered and open in the TMS."""
    coord = BeliefCoordinator.get_instance()
    conflicts = coord.contradictions.get_open_conflicts()
    return {"status": "ok", "conflicts": [c.to_dict() for c in conflicts]}


@router.get("/explain/{belief_id}", summary="Get justification trace for a belief")
def explain_belief(belief_id: str) -> Dict[str, Any]:
    """Returns the complete justification tree explanation trace backing a belief."""
    coord = BeliefCoordinator.get_instance()
    explanation = coord.explanations.explain_belief(belief_id)
    return {"status": "ok", "belief_id": belief_id, "explanation": explanation}


@router.get("/history/{belief_id}", summary="Get version history of a belief")
def get_history(belief_id: str) -> Dict[str, Any]:
    """Returns the chronological version revisions recorded for a belief."""
    coord = BeliefCoordinator.get_instance()
    history = coord.store.get_belief_history(belief_id)
    return {"status": "ok", "belief_id": belief_id, "history": history}
