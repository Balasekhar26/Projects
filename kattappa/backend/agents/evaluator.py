from __future__ import annotations

import re
from backend.core.local_answers import built_in_answer, is_model_timeout
from backend.core.memory import remember
from backend.core.model_router import ask_model
from backend.core.tool_scout import scout_for_task_background


QUICK_REPLIES = {
    "hi": "Hi, Kattappa AI OS is online and ready.",
    "hello": "Hello, Kattappa AI OS is online and ready.",
    "hey": "Hey, Kattappa AI OS is online and ready.",
    "status": "Kattappa AI OS is running locally.",
}


def detect_placeholders(text: str) -> bool:
    patterns = [
        r"(?i)#\s*todo",
        r"(?i)//\s*todo",
        r"(?i)/\*+\s*todo",
        r"(?i)#\s*\.\.\.\s*(implement|add|write)",
        r"(?i)//\s*\.\.\.\s*(implement|add|write)",
        r"(?i)pass\s*#\s*placeholder",
        r"(?i)#\s*your\s*code\s*here",
        r"(?i)//\s*your\s*code\s*here",
        r"(?i)write\s*your\s*code\s*here",
        r"(?i)implement\s*your\s*logic\s*here",
    ]
    for pattern in patterns:
        if re.search(pattern, text):
            return True
    return False


def refine_placeholder_response(user_input: str, draft: str) -> str:
    prompt = (
        "You are the Kattappa AI OS Self-Reflection agent. Your task is to review the following draft "
        "and rewrite it to remove all code stubs, placeholder comments (like '# TODO' or '// implement here'), "
        "or incomplete logic. You MUST provide the FULL, complete, copy-paste-ready code and explanation "
        "with absolutely no placeholders.\n\n"
        f"Original User Request:\n{user_input}\n\n"
        f"Draft Containing Placeholders:\n{draft}\n\n"
        "Fully Completed Response:"
    )
    return ask_model(prompt, role="coder")


def evaluator_node(state):
    if state.get("result"):
        final = state["result"]
    elif state["user_input"].strip().lower() in QUICK_REPLIES:
        final = QUICK_REPLIES[state["user_input"].strip().lower()]
        state["result"] = final
        return _finalize_evaluator(state, final)
    else:
        from backend.core.sage import SAGE
        sage_decision = SAGE.decide(
            state["user_input"],
            context=f"Plan:\n{state.get('plan') or ''}\n\nRelevant memory:\n{state.get('memory_context') or ''}"
        )
        final = sage_decision["result"]
        state["selected_agent"] = sage_decision["selected_agent"]
        state["logs"].append(f"sage: selected engine {sage_decision['selected_agent']} with score {sage_decision['score']}")
        if is_model_timeout(final):
            final = built_in_answer(state["user_input"]) or final


    # Self-Reflection / Code Verification pass
    if detect_placeholders(final):
        state["logs"].append("evaluator: self-reflection detected placeholder stubs; executing code refinement pass...")
        try:
            refined = refine_placeholder_response(state["user_input"], final)
            if refined and refined.strip():
                final = refined
                state["logs"].append("evaluator: code refinement pass completed successfully")
        except Exception as exc:
            state["logs"].append(f"evaluator: code refinement pass failed: {exc}")

    state["result"] = final
    return _finalize_evaluator(state, final)


def _finalize_evaluator(state, final):
    if state.get("ephemeral_worker"):
        state["logs"].append("evaluator: skipped durable memory for ephemeral worker task")
        state["logs"].append("evaluator: finalized")
        return state

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
