from __future__ import annotations

from backend.tools.browser_tools import search_web_basic


def browser_node(state):
    result = search_web_basic(state["user_input"])
    state["result"] = f"Browser result:\nTitle: {result['title']}\n\n{result['text']}"
    state["logs"].append("browser: searched/read")
    return state
