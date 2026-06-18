from __future__ import annotations

from backend.core.memory import build_memory_context, memory


def memory_node(state):
    if state.get("ephemeral_worker"):
        state["related_messages"] = []
        state["memory_context"] = ""
        state["logs"].append("memory: skipped durable recall for ephemeral worker task")
        return state

    remembered = _remember_command_payload(state["user_input"])
    if remembered:
        memory_id = memory.remember(remembered, category="user_memory")
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
