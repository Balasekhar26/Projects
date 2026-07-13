from fastapi import APIRouter, WebSocket, Header, HTTPException, Body
from typing import Any
from backend.api.v1.common import *
from backend.core.failure_codes import FailureReason

chat_router = APIRouter(tags=["Chat"])

def execute_chat_pipeline(
    raw_message: str,
    session_id: str,
    user_message_id: str,
    mode_override: str | None = None,
) -> dict[str, Any]:
    """Routes execution between Chat, Assistant, and Autonomous modes, and instruments tracing."""
    from backend.core.governance.request_tracer import RequestTracer
    from backend.core.rbil import RBIL, MetricsTracker
    from backend.core.safety import classify_risk
    from backend.core.adaptive_runtime import SemanticResponseCache
    from backend.core.model_router import ask_model

    clean_message = _strip_operator_prefix(raw_message)

    # 1. Determine execution mode
    escalation_level = RBIL.classify_escalation_level(clean_message)
    if mode_override:
        mode = mode_override
    else:
        if escalation_level in (1, 2):
            mode = "CHAT"
        else:
            lower_msg = clean_message.lower()
            planning_keywords = {
                "build a project", "create a plan", "setup and run", "run setup",
                "learn rf", "build a chat", "implement a system", "design a framework"
            }
            if any(kw in lower_msg for kw in planning_keywords):
                mode = "AUTONOMOUS"
            else:
                mode = "ASSISTANT"

    tracer = RequestTracer(clean_message, mode=mode)

    # 2. Route Execution based on mode
    if mode == "CHAT":
        tracer.record_stage(intent="QA_OR_CONVERSATION", router="direct_model")

        # A. Check handle_fast_path
        fast_payload = handle_fast_path(raw_message)
        if fast_payload:
            response_text = fast_payload.get("response") or ""
            tracer.record_stage(router="fast_path", result=response_text)
            state = {
                "user_input": raw_message,
                "memory_query": clean_message,
                "chat_session_id": session_id,
                "current_chat_message_id": user_message_id,
                "selected_agent": "fast_path",
                "risk_level": "low",
                "approval_required": False,
                "approval_id": None,
                "result": response_text,
                "logs": ["fast-path: executed fast command"],
                "tool_request": None,
                "operator_plan": None,
                "related_messages": [],
            }
            tracer.finalize_failure(FailureReason.OK, "fast_path", result=response_text)
            return {"response": response_text, "state": state}

        # B. Check RBIL (Level 0)
        rbil_res = RBIL.process(clean_message, session_id=session_id)
        if rbil_res:
            response_text = rbil_res["result"]
            tracer.record_stage(router="rbil", result=response_text)
            related = memory.search_chat_messages(
                clean_message,
                limit=5,
                session_id=session_id,
                exclude_message_id=user_message_id,
            )
            state = {
                "user_input": raw_message,
                "memory_query": clean_message,
                "chat_session_id": session_id,
                "current_chat_message_id": user_message_id,
                "selected_agent": rbil_res["selected_agent"],
                "risk_level": "low",
                "approval_required": False,
                "approval_id": None,
                "result": response_text,
                "logs": rbil_res["logs"],
                "tool_request": None,
                "operator_plan": None,
                "related_messages": related,
            }
            tracer.finalize_failure(FailureReason.OK, "rbil_handler", result=response_text)
            return {"response": response_text, "state": state}

        # C. Check Semantic Response Cache (if safe)
        risk_res = classify_risk(clean_message)
        is_safe = not risk_res.approval_required and not risk_res.blocked
        cached_res, cached_agent = (
            SemanticResponseCache.get(clean_message)
            if is_safe
            else (None, None)
        )
        if cached_res:
            tracer.record_stage(router="semantic_cache", result=cached_res)
            related = memory.search_chat_messages(
                clean_message,
                limit=5,
                session_id=session_id,
                exclude_message_id=user_message_id,
            )
            state = {
                "user_input": raw_message,
                "memory_query": clean_message,
                "chat_session_id": session_id,
                "current_chat_message_id": user_message_id,
                "selected_agent": cached_agent or "semantic_cache",
                "risk_level": "low",
                "approval_required": False,
                "approval_id": None,
                "result": cached_res,
                "logs": ["cache: semantic cache hit"],
                "tool_request": None,
                "operator_plan": None,
                "related_messages": related,
            }
            tracer.finalize_failure(FailureReason.OK, "semantic_cache_hit", result=cached_res)
            return {"response": cached_res, "state": state}

        # D. Direct Model Query
        role = "fast" if escalation_level == 1 else "general"
        tracer.record_stage(model=role)
        
        prompt_with_context = _build_direct_model_prompt(clean_message, session_id, user_message_id)
        result_text = ask_model(prompt_with_context, role=role)
        
        if is_safe:
            SemanticResponseCache.set(clean_message, result_text, f"direct_model_level_{escalation_level}")

        related = memory.search_chat_messages(
            clean_message,
            limit=5,
            session_id=session_id,
            exclude_message_id=user_message_id,
        )
        state = {
            "user_input": raw_message,
            "memory_query": clean_message,
            "chat_session_id": session_id,
            "current_chat_message_id": user_message_id,
            "selected_agent": f"direct_model_level_{escalation_level}",
            "risk_level": "low",
            "approval_required": False,
            "approval_id": None,
            "result": result_text,
            "logs": [f"rbil: escalated to Level {escalation_level} direct model"],
            "tool_request": None,
            "operator_plan": None,
            "related_messages": related,
        }
        # M38: CHAT-mode direct model path = escalation bypassed the agent graph
        tracer.finalize_failure(
            FailureReason.ESCALATION_BYPASSED,
            f"RBIL Level {escalation_level} -> direct_model (no agent graph)",
            result=result_text,
        )
        return {"response": result_text, "state": state}

    else:
        # Assistant Mode or Autonomous Mode runs the LangGraph cognitive stack
        tracer.record_stage(
            intent="COMPLEX_TASK_OR_PLANNING",
            router="cognitive_graph_pipeline"
        )
        
        from backend.core.adaptive_runtime import MemoryPrefetcher
        MemoryPrefetcher.prefetch(user_message_id, clean_message, session_id)

        state = _run_graph(
            raw_message,
            chat_session_id=session_id,
            current_chat_message_id=user_message_id,
            memory_query=clean_message,
        )

        selected = state.get("selected_agent") or "evaluator"
        tracer.record_stage(tool=selected, result=state.get("result"))

        if not state.get("approval_required") and state.get("result"):
            SemanticResponseCache.set(
                clean_message,
                state.get("result") or "",
                state.get("selected_agent") or "general"
            )

        tracer.finalize(result=state.get("result"))
        return {"response": state.get("result"), "state": state}


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

    # Route execution through unified pipeline
    res_dict = execute_chat_pipeline(
        request.message,
        session_id=session["id"],
        user_message_id=user_message["id"],
    )
    state = res_dict["state"]

    assistant_message = memory.add_chat_message(
        session["id"],
        "assistant",
        str(state.get("result") or ""),
        agent=str(state.get("selected_agent") or ""),
        risk=str(state.get("risk_level") or ""),
        metadata=_chat_state_metadata(state),
    )

    # Run dynamic history compression
    from backend.core.adaptive_runtime import MemoryCompressionEngine
    MemoryCompressionEngine.compress_history(session["id"])

    # Trigger async reflection & episodic storage
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

        # Check cluster capacity / handoff first
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

        session = memory.get_or_create_primary_chat_session()
        clean_message = _strip_operator_prefix(user_message)
        stored_user_message = memory.add_chat_message(session["id"], "user", clean_message)

        # Route execution through unified pipeline
        res_dict = execute_chat_pipeline(
            user_message,
            session_id=session["id"],
            user_message_id=stored_user_message["id"],
        )
        state = res_dict["state"]
        response = res_dict["response"]

        assistant_message = memory.add_chat_message(
            session["id"],
            "assistant",
            str(response or ""),
            agent=str(state.get("selected_agent") or ""),
            risk=str(state.get("risk_level") or ""),
            metadata=_chat_state_metadata(state),
        )

        from backend.core.adaptive_runtime import MemoryCompressionEngine
        MemoryCompressionEngine.compress_history(session["id"])

        for line in state.get("logs", []):
            await websocket.send_json({"type": "progress", "content": line})
        _trigger_voice_response(state)
        await websocket.send_json(
            {
                "type": "assistant",
                "content": response or "",
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



