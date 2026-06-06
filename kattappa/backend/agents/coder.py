from __future__ import annotations

from backend.core.local_answers import built_in_answer
from backend.core.model_router import ask_model
from backend.tools.code_tools import git_status


EXPLANATION_WORDS = (
    "explain",
    "tell me",
    "what is",
    "what are",
    "simple words",
    "deep explanation",
    "about",
)

CODE_ACTION_WORDS = (
    "build",
    "fix",
    "change",
    "edit",
    "implement",
    "debug",
    "error",
    "test",
    "code",
    "file",
)


def coder_node(state):
    status = git_status()
    user_input = state["user_input"]
    lower_input = user_input.lower()
    explanation_only = any(word in lower_input for word in EXPLANATION_WORDS) and not any(
        word in lower_input for word in CODE_ACTION_WORDS
    )
    if explanation_only:
        local_answer = built_in_answer(user_input)
        if local_answer:
            state["result"] = local_answer
            state["logs"].append("coder: answered from built-in local knowledge")
            return state

    state["result"] = ask_model(
        f"Act as Bala's technical assistant.\nRequest: {user_input}\nPlan: {state.get('plan')}\nGit status: {status}\n"
        "If the user asks for an explanation, explain clearly and deeply in simple words. "
        "If the user asks for code changes, give a safe coding plan and do not claim to edit files unless an approved file tool is used.",
        role="fast" if explanation_only else "coder",
    )
    state["logs"].append("coder: responded")
    return state
