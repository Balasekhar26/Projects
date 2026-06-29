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


# ---------------------------------------------------------------------------
# Bayesian Belief Engine Endpoints (Program 5C)
# ---------------------------------------------------------------------------

class EvidenceUpdateRequest(BaseModel):
    node_id: str = Field(..., description="Belief ID to apply evidence to")
    value: bool = Field(..., description="Observed truth value")


@router.post("/bayesian/evidence", summary="Set evidence state for a belief variable")
def set_bayesian_evidence(req: EvidenceUpdateRequest) -> Dict[str, Any]:
    """Sets observed evidence state for a belief node in the Bayesian engine."""
    from backend.core.beliefs.bayesian_coordinator import BayesianBeliefCoordinator
    coord = BeliefCoordinator.get_instance()
    bayesian_coord = BayesianBeliefCoordinator(coord.store)
    bayesian_coord.build_network_from_store()
    bayesian_coord.engine.set_evidence(req.node_id, req.value)
    return {"status": "ok", "evidence": bayesian_coord.engine.evidence}


@router.post("/bayesian/clear", summary="Clear all active evidence")
def clear_bayesian_evidence() -> Dict[str, Any]:
    """Clears all active evidence states registered in the Bayesian network."""
    from backend.core.beliefs.bayesian_coordinator import BayesianBeliefCoordinator
    coord = BeliefCoordinator.get_instance()
    bayesian_coord = BayesianBeliefCoordinator(coord.store)
    bayesian_coord.engine.clear_evidence()
    return {"status": "ok"}


@router.get("/bayesian/posterior/{belief_id}", summary="Get posterior probability of a belief")
def get_bayesian_posterior(belief_id: str) -> Dict[str, Any]:
    """Computes the posterior probability of the target belief given current evidence states."""
    from backend.core.beliefs.bayesian_coordinator import BayesianBeliefCoordinator
    coord = BeliefCoordinator.get_instance()
    bayesian_coord = BayesianBeliefCoordinator(coord.store)
    posterior = bayesian_coord.calculate_posterior(belief_id)
    return {"status": "ok", "belief_id": belief_id, "posterior": posterior}


@router.get("/bayesian/explain/{belief_id}", summary="Explain probability shift of a belief")
def explain_probability_shift(belief_id: str) -> Dict[str, Any]:
    """Explains how current evidence shifted the probability of the target belief."""
    from backend.core.beliefs.bayesian_coordinator import BayesianBeliefCoordinator
    coord = BeliefCoordinator.get_instance()
    bayesian_coord = BayesianBeliefCoordinator(coord.store)
    bayesian_coord.build_network_from_store()
    explanation = bayesian_coord.engine.explain_probability_shift(belief_id)
    return {"status": "ok", "belief_id": belief_id, "explanation": explanation}

