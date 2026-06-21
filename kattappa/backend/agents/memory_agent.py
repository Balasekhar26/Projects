from __future__ import annotations

from backend.core.memory import build_memory_context, memory
from backend.core.obsidian_memory import ObsidianMemory


def memory_node(state):
    if state.get("ephemeral_worker"):
        state["related_messages"] = []
        state["memory_context"] = ""
        state["logs"].append("memory: skipped durable recall for ephemeral worker task")
        return state

    remembered = _remember_command_payload(state["user_input"])
    if remembered:
        if state.get("trust_tag") == "UNTRUSTED_ENVIRONMENT":
            approved_id = state.get("approved_approval_id")
            if approved_id and _approved_continuation_matches(str(approved_id), state["user_input"]):
                state["logs"].append("memory: saving approved untrusted memory")
            else:
                import json
                approval_id = memory.create_approval(
                    state["user_input"],
                    "medium",
                    continuation_type="chat",
                    continuation_payload=json.dumps(
                        {
                            "message": state["user_input"],
                            "memory_query": state.get("memory_query") or state["user_input"],
                            "chat_session_id": state.get("chat_session_id"),
                            "chat_message_id": state.get("current_chat_message_id"),
                            "source": "memory",
                        }
                    ),
                )
                state["approval_id"] = approval_id
                state["approval_required"] = True
                state["result"] = "Approval needed. Approve to continue saving memory."
                state["logs"].append(f"memory: untrusted save request blocked pending approval {approval_id}")
                return state

        memory_id = memory.remember(remembered, category="user_memory")
        
        # Write to Obsidian Memory Graph
        try:
            obsidian = ObsidianMemory()
            obsidian.write_daily_note(f"Saved memory: {remembered}", category="user-memory")
            obsidian.write_concept_page(
                title=f"UserMemory-{memory_id[:8]}", 
                content=remembered, 
                tags=["kattappa", "memory", "user_memory"],
                connections=["Kattappa Memory System"]
            )
            state["logs"].append("memory: synced memory to Obsidian vault")
        except Exception as e:
            state["logs"].append(f"memory error: failed to write to Obsidian: {e}")

        state["selected_agent"] = "memory"
        state["plan"] = "Store the explicit user memory, then confirm it in chat."
        state["tool_request"] = {
            "agent_routing": {
                "agent": "memory",
                "reason": "The user gave an explicit remember/save-memory order.",
                "scores": [],
            }
        }
        state["result"] = f"I remembered: {remembered}"
        state["memory_context"] = remembered
        state["related_messages"] = []
        state["logs"].append(f"memory: stored explicit user memory {memory_id}")
        return state

    query = state.get("memory_query") or state["user_input"]
    message_id = state.get("current_chat_message_id")
    pref_result = None
    if message_id:
        from backend.core.adaptive_runtime import MemoryPrefetcher
        pref_result = MemoryPrefetcher.get_result(message_id)

    if pref_result:
        related_messages = pref_result["related_messages"]
        state["related_messages"] = related_messages
        state["memory_context"] = pref_result["memory_context"]
        state["logs"].append("memory: retrieved prefetched context (0ms entry latency)")
    else:
        related_messages = memory.search_chat_messages(
            query,
            limit=5,
            session_id=state.get("chat_session_id"),
            exclude_message_id=state.get("current_chat_message_id"),
        )
        state["related_messages"] = related_messages
        state["memory_context"] = build_memory_context(
            query,
            chat_session_id=state.get("chat_session_id"),
            current_chat_message_id=state.get("current_chat_message_id"),
            related_messages=related_messages,
        )
        state["logs"].append(
            f"memory: {len(related_messages)} related older message(s) found"
            if related_messages
            else "memory: no related older messages found"
        )
    return state


def _remember_command_payload(text: str) -> str:
    clean = text.strip()
    lower = clean.lower()
    if lower.startswith(("what do you remember", "do you remember", "did you remember")):
        return ""
    prefixes = (
        "remember that ",
        "remember this ",
        "remember ",
        "please remember that ",
        "please remember ",
        "save this memory: ",
        "save this memory ",
        "store this memory: ",
        "store this memory ",
        "keep in memory that ",
        "keep in memory ",
    )
    for prefix in prefixes:
        if lower.startswith(prefix):
            return clean[len(prefix):].strip(" .")
    return ""


def _approved_continuation_matches(approval_id: str, message: str) -> bool:
    import json
    approval = memory.get_approval(approval_id)
    if not approval or approval["status"] != "approved":
        return False
    if approval["continuation_type"] not in {"chat", "desktop", "manual"}:
        return False
    try:
        payload = json.loads(approval.get("continuation_payload") or "{}")
    except json.JSONDecodeError:
        payload = {}
    approved_message = str(payload.get("message") or approval["action"])
    return approved_message == message
