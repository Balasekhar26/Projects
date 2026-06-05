from __future__ import annotations

from backend.core.local_answers import built_in_answer, is_model_timeout
from backend.core.memory import remember
from backend.core.model_router import ask_model
from backend.core.tool_scout import scout_for_task_background


QUICK_REPLIES = {
    "hi": "Hi Sekhar, I am online and ready.",
    "hello": "Hello Sekhar, I am online and ready.",
    "hey": "Hey Sekhar, I am online and ready.",
    "status": "Sekhar AI OS is running locally.",
}


def evaluator_node(state):
    if state.get("result"):
        final = state["result"]
    elif state["user_input"].strip().lower() in QUICK_REPLIES:
        final = QUICK_REPLIES[state["user_input"].strip().lower()]
        state["result"] = final
    else:
        final = ask_model(
            "Answer the user's request directly. Ignore unrelated memory. Do not greet unless the user greeted.\n\n"
            f"User request:\n{state['user_input']}\n\nPlan:\n{state.get('plan')}\n\n"
            f"Relevant memory, if any:\n{state.get('memory_context')}\n\nFinal answer:",
            role="fast",
        )
        if is_model_timeout(final):
            final = built_in_answer(state["user_input"]) or final
        state["result"] = final
    remember(f"User: {state['user_input']}\nResult: {final}", category="conversation")
    if _should_scout(state["user_input"]):
        scout_for_task_background(state["user_input"], final)
        state["logs"].append("tool_scout: background free-tool scan queued")
    state["logs"].append("evaluator: finalized")
    return state


def _should_scout(user_input: str) -> bool:
    text = user_input.strip().lower()
    if not text:
        return False
    if text in QUICK_REPLIES:
        return False
    noisy = ("hi", "hello", "thanks", "thank you", "ok", "yes", "no")
    if text in noisy:
        return False
    return len(text) >= 12
