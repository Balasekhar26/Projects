from __future__ import annotations

from backend.core.memory import build_memory_context


def memory_node(state):
    state["memory_context"] = build_memory_context(state["user_input"])
    state["logs"].append("memory: recalled context")
    return state
