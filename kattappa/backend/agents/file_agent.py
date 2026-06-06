from __future__ import annotations

from backend.core.model_router import ask_model


def file_node(state):
    state["result"] = ask_model(
        f"File Agent request: {state['user_input']}\nExplain what files should be inspected or changed. "
        "Do not write files without approval.",
        role="general",
    )
    state["logs"].append("file: planned")
    return state
