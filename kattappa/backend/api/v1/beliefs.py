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


# ---------------------------------------------------------------------------
# Probabilistic Reasoning Engine Endpoints (Program 5D)
# ---------------------------------------------------------------------------

class DecisionTreeRequest(BaseModel):
    tree: Dict[str, Any] = Field(..., description="Nested JSON representation of the decision tree")
    risk_threshold: Optional[float] = Field(0.0, description="Threshold utility for risk assessment")


def parse_decision_tree(data: Dict[str, Any]) -> Any:
    """Helper to parse raw JSON dictionary into DecisionTreeNode instances."""
    from backend.core.beliefs.probabilistic_reasoning import UtilityNode, ChanceNode, DecisionNode
    node_type = data.get("type")
    node_id = data.get("node_id", "node")

    if node_type == "utility":
        return UtilityNode(node_id=node_id, utility=float(data["utility"]))

    elif node_type == "chance":
        outcomes = []
        for out in data.get("outcomes", []):
            prob = float(out["probability"])
            child = parse_decision_tree(out["child"])
            name = out.get("name", "")
            outcomes.append((prob, child, name))
        return ChanceNode(node_id=node_id, outcomes=outcomes)

    elif node_type == "decision":
        choices = []
        for ch in data.get("choices", []):
            child = parse_decision_tree(ch["child"])
            name = ch.get("name", "")
            choices.append((child, name))
        return DecisionNode(node_id=node_id, choices=choices)

    raise ValueError(f"Unknown node type: {node_type}")


@router.post("/probabilistic/evaluate", summary="Evaluate a decision tree")
def evaluate_decision_tree(req: DecisionTreeRequest) -> Dict[str, Any]:
    """Recursively evaluates a decision tree, returning the optimal choices and expected utilities."""
    try:
        from backend.core.beliefs.probabilistic_reasoning import ProbabilisticReasoningEngine, DecisionExplanationGenerator
        root = parse_decision_tree(req.tree)
        engine = ProbabilisticReasoningEngine()
        explainer = DecisionExplanationGenerator()

        expected_utility, best_choice = engine.evaluate_decision_tree(root)
        explanation = explainer.generate_explanation(root, threshold=req.risk_threshold or 0.0)

        return {
            "status": "ok",
            "expected_utility": expected_utility,
            "best_choice": best_choice,
            "explanation": explanation,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/probabilistic/risk", summary="Assess risk on a decision tree")
def assess_risk(req: DecisionTreeRequest) -> Dict[str, Any]:
    """Calculates path risk (probability that utility falls below threshold) for a decision tree."""
    try:
        from backend.core.beliefs.probabilistic_reasoning import ProbabilisticReasoningEngine
        root = parse_decision_tree(req.tree)
        risk = ProbabilisticReasoningEngine.assess_risk(root, req.risk_threshold or 0.0)
        return {
            "status": "ok",
            "risk_probability": risk,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Causal Reasoning Engine Endpoints (Program 5E)
# ---------------------------------------------------------------------------

class CounterfactualRequest(BaseModel):
    scm: Dict[str, Any] = Field(..., description="Structural Causal Model schema")
    evidence: Dict[str, bool] = Field(..., description="Observed evidence mapping")
    intervention: Dict[str, bool] = Field(..., description="do-calculus intervention values")
    target: str = Field(..., description="Target node to predict counterfactually")


class RootCauseRequest(BaseModel):
    scm: Dict[str, Any] = Field(..., description="Structural Causal Model schema")
    failure_evidence: Dict[str, bool] = Field(..., description="Failure observations mapping")


def parse_scm(data: Dict[str, Any]) -> Any:
    """Helper to parse JSON dictionary into StructuralCausalModel instances."""
    from backend.core.beliefs.causal_engine import StructuralCausalModel, CausalVariable
    scm = StructuralCausalModel()
    variables_data = data.get("variables", {})

    pending = list(variables_data.keys())
    added = set()

    for _ in range(len(pending) * 2):
        if not pending:
            break
        name = pending.pop(0)
        vdata = variables_data[name]
        parents = vdata.get("parents", [])

        if all(p in added for p in parents):
            eq_str = vdata.get("equation", "U")
            if eq_str == "U":
                eq = lambda p, u: u
            elif eq_str in ("A or U", "parents or U"):
                eq = lambda p, u: any(p.values()) or u
            elif eq_str in ("A and U", "parents and U"):
                eq = lambda p, u: all(p.values()) and u
            elif eq_str.startswith("not") and eq_str.endswith("and U"):
                parent_name = eq_str.split()[1]
                eq = lambda p, u, pn=parent_name: (not p.get(pn, False)) and u
            else:
                eq = lambda p, u: any(p.values()) or u

            var = CausalVariable(name=name, parents=parents, equation=eq)
            scm.add_variable(var, exogenous_prior=float(vdata.get("exogenous_prior", 0.5)))
            added.add(name)
        else:
            pending.append(name)

    return scm


@router.post("/causal/counterfactual", summary="Evaluate a counterfactual query")
def evaluate_counterfactual(req: CounterfactualRequest) -> Dict[str, Any]:
    """Answers counterfactual queries by running Pearl's three-step abduction-action-prediction process."""
    try:
        from backend.core.beliefs.causal_engine import CausalExplanationGenerator
        scm = parse_scm(req.scm)
        result = scm.counterfactual(req.evidence, req.intervention, req.target)
        explanation = CausalExplanationGenerator.explain_counterfactual(
            req.evidence, req.intervention, req.target, result
        )
        return {
            "status": "ok",
            "counterfactual_probability": result,
            "explanation": explanation,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/causal/root-cause", summary="Perform root cause analysis")
def analyze_root_cause(req: RootCauseRequest) -> Dict[str, Any]:
    """Identifies and ranks candidate causal variables for observed system failures."""
    try:
        from backend.core.beliefs.causal_engine import RootCauseAnalyzer
        scm = parse_scm(req.scm)
        analyzer = RootCauseAnalyzer(scm)
        rankings = analyzer.analyze_root_cause(req.failure_evidence)
        return {
            "status": "ok",
            "root_cause_rankings": [{"variable": name, "prevention_probability": score} for name, score in rankings],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



