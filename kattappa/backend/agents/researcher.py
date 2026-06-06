from __future__ import annotations

from backend.core.model_router import ask_model
from backend.tools.browser_tools import search_web_basic


def researcher_node(state):
    web = search_web_basic(state["user_input"])
    state["result"] = ask_model(
        f"Research the request using this browser text.\nRequest: {state['user_input']}\n\n{web['text'][:8000]}",
        role="general",
    )
    state["logs"].append("researcher: summarized web result")
    return state
