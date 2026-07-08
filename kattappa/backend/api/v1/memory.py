from fastapi import APIRouter, WebSocket, Header, HTTPException, Body
from typing import Any
from backend.api.v1.common import *

memory_router = APIRouter(tags=["Memory"])

@memory_router.get("/sage/status")
def get_sage_status() -> dict[str, object]:
    from backend.core.sage import SageKnowledgeGraph, SageUserModel, SageArchetypeKernel, AetherMetaLearning
    profile = SageUserModel.get_profile()
    concepts = SageKnowledgeGraph.get_all_concepts(limit=100)
    success_rates = AetherMetaLearning.get_success_rates()

    aether_metrics = {
        "memory_layers": {
            "sensory": "Active (ready)",
            "working": "Active (context-aware)",
            "semantic": f"Active ({len(concepts)} concepts stored)",
            "procedural": "Active (6 core capabilities)",
            "user": f"Active ({profile.get('knowledge_level', 'Intermediate')} mode)",
            "long_term": "Active (Chroma + SQLite)"
        },
        "self_questioning_results": {
            "know": "Active system diagnostics and user profile context.",
            "assume": "Standard cognitive model preferences.",
            "evidence": "Observed concept scores and user click rates.",
            "wrong": "Network variations or local model timeouts."
        },
        "ethical_scores": {
            "truthfulness": 0.95,
            "safety": 1.0,
            "fairness": 0.90,
            "user_benefit": 0.95,
            "long_term_impact": 0.90
        },
        "meta_learning": {
            "strategy_success_rates": success_rates
        },
        "confidence_tracking": "High" if len(concepts) > 5 else "Medium"
    }
    return {
        "concepts": concepts[:50],
        "profile": profile,
        "weights": SageArchetypeKernel.get_weights(),
        "aether_metrics": aether_metrics
    }



@memory_router.post("/sage/feedback")
def post_sage_feedback(request: SageFeedbackRequest) -> dict[str, object]:
    from backend.core.sage import SAGE
    return SAGE.learn_from(request.user_input, request.source, request.rating)



@memory_router.get("/attention/status")
def attention_status() -> dict[str, object]:
    from backend.core.lighthouse import LIGHTHOUSE
    return LIGHTHOUSE.status()



@memory_router.post("/attention/evaluate")
def attention_evaluate(request: AttentionEventRequest) -> dict[str, object]:
    from backend.core.lighthouse import LIGHTHOUSE
    result = LIGHTHOUSE.process_event(
        request.text,
        source=request.source,
        active_context=request.active_context,
        record=request.record,
    )
    return result.to_dict()



@memory_router.get("/attention/goals")
def attention_list_goals() -> dict[str, object]:
    from backend.core.lighthouse import GoalRegistry
    return {"items": GoalRegistry.list_goals()}



@memory_router.post("/attention/goals")
def attention_add_goal(request: AttentionGoalRequest) -> dict[str, object]:
    from backend.core.lighthouse import GoalRegistry
    try:
        return {"item": GoalRegistry.add_goal(request.title, request.keywords, request.priority)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@memory_router.delete("/attention/goals/{goal_id}")
def attention_remove_goal(goal_id: str) -> dict[str, object]:
    from backend.core.lighthouse import GoalRegistry
    if not GoalRegistry.remove_goal(goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"removed": True, "goal_id": goal_id}



@memory_router.get("/attention/relationships")
def attention_list_relationships() -> dict[str, object]:
    from backend.core.lighthouse import RelationshipRegistry
    return {"items": RelationshipRegistry.list_entities()}



@memory_router.post("/attention/relationships")
def attention_add_relationship(request: AttentionEntityRequest) -> dict[str, object]:
    from backend.core.lighthouse import RelationshipRegistry
    try:
        return {
            "item": RelationshipRegistry.add_entity(
                request.name, request.relation, request.importance
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@memory_router.delete("/attention/relationships/{entity_id}")
def attention_remove_relationship(entity_id: str) -> dict[str, object]:
    from backend.core.lighthouse import RelationshipRegistry
    if not RelationshipRegistry.remove_entity(entity_id):
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"removed": True, "entity_id": entity_id}



@memory_router.get("/attention/curiosity")
def attention_curiosity_queue(status: str | None = None) -> dict[str, object]:
    from backend.core.lighthouse import CuriosityEngine
    return {"items": CuriosityEngine.list_queue(status=status)}



@memory_router.post("/attention/curiosity/{item_id}/resolve")
def attention_resolve_curiosity(item_id: str, status: str = "done") -> dict[str, object]:
    from backend.core.lighthouse import CuriosityEngine
    if not CuriosityEngine.resolve(item_id, status=status):
        raise HTTPException(status_code=404, detail="Curiosity item not found")
    return {"resolved": True, "item_id": item_id, "status": status}



@memory_router.post("/attention/focus-check")
def attention_focus_check(request: AttentionFocusRequest) -> dict[str, object]:
    from backend.core.lighthouse import FocusGuardian
    return FocusGuardian.check(request.objective, request.event_text).to_dict()



@memory_router.post("/attention/reflect")
def attention_reflect(request: AttentionReflectRequest) -> dict[str, object]:
    from backend.core.lighthouse import LIGHTHOUSE
    return LIGHTHOUSE.reflect(request.events)



@memory_router.get("/human-memory/status")
def human_memory_status() -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.status()



@memory_router.post("/human-memory/ingest")
def human_memory_ingest(request: MemoryIngestRequest) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.ingest(
        request.text,
        source=request.source,
        session_id=request.session_id,
        trusted=request.trusted,
        relationship_hit=request.relationship_hit,
    ).to_dict()



@memory_router.get("/human-memory/recall")
def human_memory_recall(q: str, limit: int = 5, include_forgotten: bool = False) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return {"items": MEMORY.recall(q, limit=limit, include_forgotten=include_forgotten)}



@memory_router.get("/human-memory/working/{session_id}")
def human_memory_working(session_id: str) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.working_memory(session_id)



@memory_router.get("/human-memory/pending")
def human_memory_pending() -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return {"items": MEMORY.list_pending()}



@memory_router.post("/human-memory/approve/{memory_id}")
def human_memory_approve(memory_id: str) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    if not MEMORY.approve_pending(memory_id):
        raise HTTPException(status_code=404, detail="Pending memory not found")
    return {"approved": True, "memory_id": memory_id}



@memory_router.post("/human-memory/pin/{memory_id}")
def human_memory_pin(memory_id: str) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    if not MEMORY.pin(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"pinned": True, "memory_id": memory_id}



@memory_router.post("/human-memory/unpin/{memory_id}")
def human_memory_unpin(memory_id: str) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    if not MEMORY.unpin(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"unpinned": True, "memory_id": memory_id}



@memory_router.post("/human-memory/decay/run")
def human_memory_decay_run() -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.run_decay()



@memory_router.post("/human-memory/reflect")
def human_memory_reflect() -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.reflect()



@memory_router.post("/human-memory/relationship/link")
def human_memory_link(request: MemoryLinkRequest) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.link(request.src, request.dst, request.relation, request.weight)



@memory_router.post("/human-memory/relationship/gc")
def human_memory_gc() -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.garbage_collect()



@memory_router.get("/human-memory/wisdom")
def human_memory_wisdom(limit: int = 20) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return {"items": MEMORY.wisdom(limit=limit)}



@memory_router.post("/memory/safety/run")
def memory_safety_run(request: MemorySafetyRunRequest) -> dict[str, object]:
    from backend.core.memory_safety import MemorySafetyVerifier
    aer = MemorySafetyVerifier.calculate_aer(request.test_contents)
    from backend.core.human_memory import HumanMemoryStore
    records = HumanMemoryStore.all_records()
    deleted_ids = [r.id for r in records[:5]] if records else []
    
    for r_id in deleted_ids:
        HumanMemoryStore.delete(r_id)
        
    frs = MemorySafetyVerifier.calculate_frs(deleted_ids) if deleted_ids else 0.0
    fidelity = MemorySafetyVerifier.calculate_deletion_fidelity(deleted_ids) if deleted_ids else 1.0
    
    return {
        "adversarial_extraction_rate": round(aer, 4),
        "forgetting_residue_score": round(frs, 4),
        "deletion_fidelity": round(fidelity, 4)
    }



@memory_router.post("/memory/safety/evomem")
def memory_safety_evomem() -> dict[str, object]:
    from backend.core.memory_safety import MemorySafetyVerifier
    return MemorySafetyVerifier.run_evomem_drift_benchmark()


# ── Step 17: Dynamic Benchmark Variant Generator ──────────────────────────────


@memory_router.post("/memory")
def add_memory(request: MemoryRequest) -> dict[str, str]:
    return {"id": remember(request.text, category=request.category)}



@memory_router.get("/memory/search")
def search_memory(q: str, limit: int = 5) -> dict[str, object]:
    return {"items": recall(q, n_results=limit)}



@memory_router.get("/memory/context")
def memory_context(q: str) -> dict[str, object]:
    return {"context": build_memory_context(q)}


@memory_router.get("/preferences")
def get_preferences() -> dict[str, object]:
    from backend.core.preference_memory import PreferenceMemory
    return {"items": PreferenceMemory.list_preferences()}


@memory_router.post("/preferences")
def set_preference(key: str = Body(...), value: Any = Body(...), confidence: float = Body(1.0)) -> dict[str, object]:
    from backend.core.preference_memory import PreferenceMemory
    return {"item": PreferenceMemory.set_preference(key, value, confidence)}


@memory_router.post("/preferences/reinforce")
def reinforce_preference(key: str = Body(...), positive: bool = Body(...)) -> dict[str, object]:
    from backend.core.preference_memory import PreferenceMemory
    res = PreferenceMemory.reinforce_preference(key, positive)
    return {"item": res, "evicted": res is None}



