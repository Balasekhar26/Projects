from __future__ import annotations

from backend.core.model_router import ask_model
from backend.tools.screen_tools import read_screen_text


def vision_node(state):
    screen_text = read_screen_text()
    state["result"] = ask_model(
        f"Explain the current screen from OCR text and say what action may help.\nOCR:\n{screen_text}",
        role="vision",
    )
    state["logs"].append("vision: screen analyzed")
    return state
