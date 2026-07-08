from fastapi import APIRouter, WebSocket, Header, HTTPException, Body
from typing import Any
from backend.api.v1.common import *

chat_router = APIRouter(tags=["Chat"])

@chat_router.post("/chat")
def chat(request: ChatRequest) -> dict[str, object]:
    # Check cluster capacity / handoff first
    delegated_payload = _cluster_delegated_chat_payload(request.message)
    if delegated_payload:
        state = delegated_payload.get("state")
        if isinstance(state, dict):
            _trigger_voice_response(state)
        return delegated_payload

    session = memory.get_or_create_primary_chat_session()
    clean_message = _strip_operator_prefix(request.message)

    user_message = memory.add_chat_message(session["id"], "user", clean_message)

    # Invoke the unified 9-layer graph pipeline
    state = _run_graph(
        request.message,
        chat_session_id=session["id"],
        current_chat_message_id=user_message["id"],
        memory_query=clean_message,
    )

    assistant_message = memory.add_chat_message(
        session["id"],
        "assistant",
        str(state.get("result") or ""),
        agent=str(state.get("selected_agent") or ""),
        risk=str(state.get("risk_level") or ""),
        metadata=_chat_state_metadata(state),
    )

    # Update Semantic Response Cache — only cache responses that did NOT require approval
    if not state.get("approval_required") and state.get("result"):
        from backend.core.adaptive_runtime import SemanticResponseCache
        SemanticResponseCache.set(
            clean_message,
            state.get("result") or "",
            state.get("selected_agent") or "general"
        )

    # Run dynamic history compression
    from backend.core.adaptive_runtime import MemoryCompressionEngine
    MemoryCompressionEngine.compress_history(session["id"])

    # Trigger async reflection & episodic storage (off-critical path)
    import threading
    from backend.core.reflection_engine import ReflectionEngine
    threading.Thread(
        target=ReflectionEngine.reflect_and_consolidate,
        args=(session["id"], clean_message, state.get("result") or "", state),
        daemon=True
    ).start()

    _trigger_voice_response(state)
    return {
        "response": state.get("result"),
        "state": state,
        "session": session,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "assistant_message_id": assistant_message["id"],
    }



@chat_router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"type": "system", "content": "Kattappa AI OS connected."})
    while True:
        raw_msg = await websocket.receive_text()

        try:
            data = json.loads(raw_msg)
            if isinstance(data, dict):
                msg_type = data.get("type")
                if msg_type == "typing":
                    from backend.core.adaptive_runtime import PredictiveModelLoader
                    PredictiveModelLoader.predict_and_warm(data.get("text", ""))
                    continue
                elif msg_type == "message":
                    user_message = data.get("text", "")
                else:
                    user_message = raw_msg
            else:
                user_message = raw_msg
        except Exception:
            user_message = raw_msg

        # Check fast path first
        fast_payload = handle_fast_path(user_message)
        if fast_payload:
            state = fast_payload["state"]
            session = fast_payload["session"]
            await websocket.send_json({"type": "progress", "content": "fast-path: executing fast command..."})
            for line in state.get("logs", []):
                await websocket.send_json({"type": "progress", "content": line})
            _trigger_voice_response(state)
            await websocket.send_json(
                {
                    "type": "assistant",
                    "content": fast_payload.get("response") or "",
                    "approval_required": state.get("approval_required", False),
                    "approval_id": state.get("approval_id"),
                    "risk_level": state.get("risk_level", "low"),
                    "selected_agent": state.get("selected_agent"),
                    "routing": None,
                    "operator_plan": None,
                    "related_messages": [],
                    "session_id": session.get("id"),
                    "assistant_message_id": fast_payload.get("assistant_message_id"),
                    "assistant_message": fast_payload.get("assistant_message"),
                }
            )
            continue

        session = memory.get_or_create_primary_chat_session()
        clean_message = _strip_operator_prefix(user_message)

        # 1. Check RBIL (Level 0)
        from backend.core.rbil import RBIL, MetricsTracker
        rbil_res = RBIL.process(clean_message, session_id=session["id"])
        if rbil_res:
            stored_user_message = memory.add_chat_message(session["id"], "user", clean_message)
            assistant_message = memory.add_chat_message(
                session["id"],
                "assistant",
                rbil_res["result"],
                agent=rbil_res["selected_agent"],
                risk="low",
                metadata=json.dumps({"approval_id": None, "related_message_ids": [], "rbil_hit": True})
            )
            _ws_rbil_related = memory.search_chat_messages(
                clean_message,
                limit=5,
                session_id=session["id"],
                exclude_message_id=stored_user_message["id"],
            )
            state = {
                "user_input": user_message,
                "memory_query": clean_message,
                "chat_session_id": session["id"],
                "current_chat_message_id": stored_user_message["id"],
                "selected_agent": rbil_res["selected_agent"],
                "risk_level": "low",
                "approval_required": False,
                "approval_id": None,
                "result": rbil_res["result"],
                "logs": rbil_res["logs"],
                "tool_request": None,
                "operator_plan": None,
                "related_messages": _ws_rbil_related,
            }
            await websocket.send_json({"type": "progress", "content": f"rbil: match found ({rbil_res['selected_agent']})"})
            _trigger_voice_response(state)
            await websocket.send_json(
                {
                    "type": "assistant",
                    "content": rbil_res["result"],
                    "approval_required": False,
                    "approval_id": None,
                    "risk_level": "low",
                    "selected_agent": state["selected_agent"],
                    "routing": None,
                    "operator_plan": None,
                    "related_messages": state["related_messages"],
                    "session_id": session["id"],
                    "assistant_message_id": assistant_message["id"],
                    "assistant_message": assistant_message,
                }
            )
            from backend.core.adaptive_runtime import MemoryCompressionEngine
            MemoryCompressionEngine.compress_history(session["id"])
            continue

        # 2. Check Semantic Response Cache — but only for safe messages.
        # Risky messages must always run the full pipeline so the safety gate fires.
        from backend.core.safety import classify_risk as _ws_classify_risk
        _ws_risk = _ws_classify_risk(clean_message)
        _ws_cache_safe = not _ws_risk.approval_required and not _ws_risk.blocked

        from backend.core.adaptive_runtime import SemanticResponseCache
        cached_res, cached_agent = (SemanticResponseCache.get(clean_message) if _ws_cache_safe else (None, None))
        if cached_res:
            stored_user_message = memory.add_chat_message(session["id"], "user", clean_message)
            # Populate related_messages even on cache hits
            _ws_cache_related = memory.search_chat_messages(
                clean_message,
                limit=5,
                session_id=session["id"],
                exclude_message_id=stored_user_message["id"],
            )
            assistant_message = memory.add_chat_message(
                session["id"],
                "assistant",
                cached_res,
                agent=cached_agent or "semantic_cache",
                risk="low",
                metadata=json.dumps({"approval_id": None, "related_message_ids": [], "cache_hit": True})
            )
            state = {
                "user_input": user_message,
                "memory_query": clean_message,
                "chat_session_id": session["id"],
                "current_chat_message_id": stored_user_message["id"],
                "selected_agent": cached_agent or "semantic_cache",
                "risk_level": "low",
                "approval_required": False,
                "approval_id": None,
                "result": cached_res,
                "logs": ["cache: semantic cache hit (websocket)"],
                "tool_request": None,
                "operator_plan": None,
                "related_messages": _ws_cache_related,
            }
            await websocket.send_json({"type": "progress", "content": "cache: semantic cache hit"})
            _trigger_voice_response(state)
            await websocket.send_json(
                {
                    "type": "assistant",
                    "content": cached_res,
                    "approval_required": False,
                    "approval_id": None,
                    "risk_level": "low",
                    "selected_agent": state["selected_agent"],
                    "routing": None,
                    "operator_plan": None,
                    "related_messages": _ws_cache_related,
                    "session_id": session["id"],
                    "assistant_message_id": assistant_message["id"],
                    "assistant_message": assistant_message,
                }
            )
            from backend.core.adaptive_runtime import MemoryCompressionEngine
            MemoryCompressionEngine.compress_history(session["id"])
            continue

        # 3. Check Cluster Capacity / Handoff
        await websocket.send_json(
            {"type": "progress", "content": "Checking local capacity..."}
        )
        delegated_payload = _cluster_delegated_chat_payload(user_message)
        if delegated_payload:
            state = delegated_payload["state"]
            session = delegated_payload["session"]
            for line in state.get("logs", []):
                await websocket.send_json({"type": "progress", "content": line})
            _trigger_voice_response(state)
            await websocket.send_json(
                {
                    "type": "assistant",
                    "content": delegated_payload.get("response") or "",
                    "approval_required": state.get("approval_required", False),
                    "approval_id": state.get("approval_id"),
                    "risk_level": state.get("risk_level", "unknown"),
                    "selected_agent": state.get("selected_agent"),
                    "routing": (
                        state.get("tool_request", {}).get("agent_routing")
                        if state.get("tool_request")
                        else None
                    ),
                    "operator_plan": state.get("operator_plan"),
                    "related_messages": state.get("related_messages", []),
                    "session_id": session.get("id"),
                    "assistant_message_id": delegated_payload.get("assistant_message_id"),
                    "assistant_message": delegated_payload.get("assistant_message"),
                }
            )
            continue

        # 2. Check Direct Model Escalation (Level 1/2)
        escalation_level = RBIL.classify_escalation_level(clean_message)
        if escalation_level in (1, 2):
            stored_user_message = memory.add_chat_message(session["id"], "user", clean_message)
            role = "fast" if escalation_level == 1 else "general"
            await websocket.send_json(
                {"type": "progress", "content": f"rbil: escalating query to Level {escalation_level} model..."}
            )
            from backend.core.model_router import ask_model
            t0 = time.perf_counter()
            prompt_with_context = _build_direct_model_prompt(clean_message, session["id"], stored_user_message["id"])
            result_text = ask_model(prompt_with_context, role=role)
            duration = time.perf_counter() - t0

            MetricsTracker.record_hit("rule", time_saved=1.5, tokens_saved=200)

            assistant_message = memory.add_chat_message(
                session["id"],
                "assistant",
                result_text,
                agent=f"direct_model_level_{escalation_level}",
                risk="low",
                metadata=json.dumps({"approval_id": None, "related_message_ids": [], "direct_model": True})
            )
            _ws_direct_related = memory.search_chat_messages(
                clean_message,
                limit=5,
                session_id=session["id"],
                exclude_message_id=stored_user_message["id"],
            )
            state = {
                "user_input": user_message,
                "memory_query": clean_message,
                "chat_session_id": session["id"],
                "current_chat_message_id": stored_user_message["id"],
                "selected_agent": f"direct_model_level_{escalation_level}",
                "risk_level": "low",
                "approval_required": False,
                "approval_id": None,
                "result": result_text,
                "logs": [f"rbil: escalated to Level {escalation_level} direct model, took {duration:.2f}s"],
                "tool_request": None,
                "operator_plan": None,
                "related_messages": _ws_direct_related,
            }
            # Cache response
            from backend.core.adaptive_runtime import SemanticResponseCache
            SemanticResponseCache.set(clean_message, result_text, f"direct_model_level_{escalation_level}")

            _trigger_voice_response(state)
            await websocket.send_json(
                {
                    "type": "assistant",
                    "content": result_text,
                    "approval_required": False,
                    "approval_id": None,
                    "risk_level": "low",
                    "selected_agent": state["selected_agent"],
                    "routing": None,
                    "operator_plan": None,
                    "related_messages": _ws_direct_related,
                    "session_id": session["id"],
                    "assistant_message_id": assistant_message["id"],
                    "assistant_message": assistant_message,
                }
            )
            from backend.core.adaptive_runtime import MemoryCompressionEngine
            MemoryCompressionEngine.compress_history(session["id"])
            continue

        # Record escalation to Level 4 (full graph)
        MetricsTracker.record_escalation()

        stored_user_message = memory.add_chat_message(session["id"], "user", clean_message)

        # Start prefetching memory background task
        from backend.core.adaptive_runtime import MemoryPrefetcher
        MemoryPrefetcher.prefetch(stored_user_message["id"], clean_message, session["id"])

        await websocket.send_json(
            {"type": "progress", "content": "Planning and routing..."}
        )
        state = _run_graph(
            user_message,
            chat_session_id=session["id"],
            current_chat_message_id=stored_user_message["id"],
            memory_query=clean_message,
        )
        assistant_message = memory.add_chat_message(
            session["id"],
            "assistant",
            str(state.get("result") or ""),
            agent=str(state.get("selected_agent") or ""),
            risk=str(state.get("risk_level") or ""),
            metadata=_chat_state_metadata(state),
        )

        # Update Semantic Response Cache — only cache non-approval responses
        if not state.get("approval_required"):
            SemanticResponseCache.set(clean_message, state.get("result") or "", state.get("selected_agent") or "general")

        # Run dialogue history compression
        from backend.core.adaptive_runtime import MemoryCompressionEngine
        MemoryCompressionEngine.compress_history(session["id"])

        for line in state.get("logs", []):
            await websocket.send_json({"type": "progress", "content": line})
        _trigger_voice_response(state)
        await websocket.send_json(
            {
                "type": "assistant",
                "content": state.get("result") or "",
                "approval_required": state.get("approval_required", False),
                "approval_id": state.get("approval_id"),
                "risk_level": state.get("risk_level", "unknown"),
                "selected_agent": state.get("selected_agent"),
                "routing": (
                    state.get("tool_request", {}).get("agent_routing")
                    if state.get("tool_request")
                    else None
                ),
                "operator_plan": state.get("operator_plan"),
                "related_messages": state.get("related_messages", []),
                "session_id": session["id"],
                "assistant_message_id": assistant_message["id"],
                "assistant_message": assistant_message,
            }
        )


def _resolve_action_success(success: bool | None, failure: bool | None) -> bool:
    if success is None and failure is None:
        raise HTTPException(status_code=400, detail="success or failure is required")
    resolved = bool(success) if success is not None else not bool(failure)
    if failure is not None and bool(failure) != (not resolved):
        raise HTTPException(
            status_code=400,
            detail="failure must be the inverse of success",
        )
    return resolved



@chat_router.post("/chat-sessions")
def create_chat_session(request: ChatSessionRequest) -> dict[str, object]:
    return {"item": memory.create_chat_session(request.title)}



@chat_router.get("/chat-sessions")
def chat_sessions(limit: int = 50) -> dict[str, object]:
    return {"items": memory.list_chat_sessions(limit=limit)}



@chat_router.get("/chat-sessions/{session_id}")
def get_chat_session(session_id: str) -> dict[str, object]:
    item = memory.get_chat_session(session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"item": item, "messages": memory.list_chat_messages(session_id)}



@chat_router.post("/chat-sessions/{session_id}/messages")
def add_chat_session_message(
    session_id: str, request: ChatMessageRequest
) -> dict[str, object]:
    try:
        item = memory.add_chat_message(
            session_id=session_id,
            role=request.role,
            content=request.content,
            agent=request.agent,
            risk=request.risk,
            metadata=request.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}



@chat_router.post("/chat-messages/{message_id}/rating")
def rate_chat_message(
    message_id: str, request: ChatMessageRatingRequest
) -> dict[str, object]:
    try:
        item = memory.rate_chat_message(message_id, request.rating)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Chat message not found")
    return {"item": item}



