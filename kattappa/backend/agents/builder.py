from __future__ import annotations

from backend.core.builder_brain import builder_answer


def builder_node(state):
    state["result"] = builder_answer(state["user_input"])
    state["logs"].append("builder: explained local engineering workflow")
    return state
