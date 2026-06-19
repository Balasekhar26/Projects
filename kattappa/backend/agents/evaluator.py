from __future__ import annotations

import re
from backend.core.local_answers import built_in_answer, is_model_timeout
from backend.core.memory import remember
from backend.core.model_router import ask_model
from backend.core.response_quality import response_looks_related, topic_phrase
from backend.core.tool_scout import scout_for_task_background


QUICK_REPLIES = {
    "hi": "Hi, Kattappa AI OS is online and ready.",
    "hello": "Hello, Kattappa AI OS is online and ready.",
    "hey": "Hey, Kattappa AI OS is online and ready.",
    "status": "Kattappa AI OS is running locally.",
}

BAD_INTERACTION_PATTERNS = (
    r"(?i)\b(i am|i'm)\s+jarvis\b",
    r"(?i)\b(british|sarcastic)\s+ai\b",
    r"(?i)\bcomplete diagnostic control\b",
    r"(?i)\bfull control of (your|the) (system|computer|machine)\b",
    r"(?i)\b(my lord|master|darling|sexy)\b",
    r"(?i)\b(idiot|stupid|dumb|shut up)\b",
)


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

    guarded = guard_interaction_reply(state["user_input"], final)
    if guarded != final:
        final = guarded
        state["logs"].append("evaluator: interaction guard repaired response tone")

    relevant = guard_relevance_reply(state["user_input"], final)
    if relevant != final:
        final = relevant
        state["logs"].append("evaluator: relevance guard repaired response focus")

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


def guard_interaction_reply(user_input: str, draft: str) -> str:
    if not _needs_interaction_guard(draft):
        return draft
    repaired = _repair_interaction_reply(user_input, draft)
    if repaired and not _needs_interaction_guard(repaired) and not is_model_timeout(repaired):
        return repaired
    built_in = built_in_answer(user_input)
    if built_in:
        return built_in
    return (
        "I should not answer in that tone. I can help, but I will keep it clear, respectful, "
        "and honest about what I can actually do. Please send the exact task and I will handle it safely."
    )


def _needs_interaction_guard(text: str) -> bool:
    return any(re.search(pattern, text or "") for pattern in BAD_INTERACTION_PATTERNS)


def _repair_interaction_reply(user_input: str, draft: str) -> str:
    prompt = (
        "Rewrite this assistant reply for Kattappa AI OS.\n"
        "Rules: English text only, respectful, concise, practical, no sarcasm, no insults, no flirting, "
        "no JARVIS/British persona, no movie-character roleplay, and no false claims of system control. "
        "Preserve any useful task answer if possible.\n\n"
        f"User request:\n{user_input}\n\n"
        f"Bad draft:\n{draft}\n\n"
        "Safe reply:"
    )
    return ask_model(
        prompt,
        role="fast",
        system=(
            "You are a safety-and-tone repair layer for Kattappa AI OS. Return only the corrected English reply."
        ),
    )


def guard_relevance_reply(user_input: str, draft: str) -> str:
    if response_looks_related(user_input, draft):
        return draft
    complaint_reply = _relevance_complaint_reply(user_input)
    if complaint_reply:
        return complaint_reply
    repaired = _repair_relevance_reply(user_input, draft)
    if repaired and response_looks_related(user_input, repaired) and not is_model_timeout(repaired):
        return repaired
    built_in = built_in_answer(user_input)
    if built_in:
        return built_in
    return (
        f"I may have drifted from your latest message: \"{topic_phrase(user_input)}\". "
        "Please resend the exact task or question, and I will answer that message directly without using unrelated older context."
    )


def _relevance_complaint_reply(user_input: str) -> str:
    lower = user_input.lower()
    reply_words = ("reply", "replies", "respond", "response", "answer")
    relation_words = ("related", "relevant", "relate", "message", "question", "latest")
    if any(word in lower for word in reply_words) and any(word in lower for word in relation_words):
        return (
            "You are right. Kattappa should answer your latest message directly, not drift into older chat or unrelated memory. "
            "I added a relevance guard so each draft reply is checked against your current message before it is shown, stored, or spoken."
        )
    return ""


def _repair_relevance_reply(user_input: str, draft: str) -> str:
    prompt = (
        "Rewrite this assistant reply so it directly answers the latest user message. "
        "Ignore unrelated older memory unless it clearly supports the latest message. "
        "Keep the reply in English, practical, concise, and focused. "
        "The first sentence must clearly address the user's exact request.\n\n"
        f"Latest user message:\n{user_input}\n\n"
        f"Unrelated or drifting draft:\n{draft}\n\n"
        "Focused reply:"
    )
    return ask_model(
        prompt,
        role="fast",
        system=(
            "You are Kattappa AI OS response-focus repair. Return only the corrected English reply."
        ),
    )
