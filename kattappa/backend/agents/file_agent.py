from __future__ import annotations

from backend.core.model_router import ask_model


def file_node(state):
    if _delete_without_target(state["user_input"]):
        state["result"] = (
            "I need the exact delete target first: file, folder, chat item, or memory item."
        )
        state["logs"].append("file: delete target missing")
        return state

    state["result"] = ask_model(
        f"File Agent request: {state['user_input']}\nExplain what files should be inspected or changed. "
        "Do not write files without approval.",
        role="general",
    )
    state["logs"].append("file: planned")
    return state


def _delete_without_target(text: str) -> bool:
    lower = text.lower().strip()
    if not any(word in lower for word in ("delete", "remove", "erase")):
        return False
    target_markers = (
        "/",
        "\\",
        ".txt",
        ".md",
        ".py",
        ".ts",
        ".tsx",
        ".json",
        ".yaml",
        ".yml",
        " file ",
        " folder ",
        " directory ",
        " memory ",
        " chat ",
        " message ",
    )
    return not any(marker in lower for marker in target_markers)
