from __future__ import annotations

from typing import Any

from backend.core.model_router import ask_model
from backend.tools.writing.grammar_api import check_grammar


def improve_text(text: str, tone: str = "clear") -> dict[str, Any]:
    checked = check_grammar(text)
    corrected = checked["corrected_text"]
    prompt = (
        "Rewrite this text with the requested tone while preserving meaning. "
        "Do not add new facts.\n\n"
        f"Tone: {tone}\n\nText:\n{corrected}"
    )
    rewritten = ask_model(
        prompt,
        role="fast",
        system="You are a concise local writing assistant. Preserve meaning and privacy.",
    )
    return {
        "engine": "harper-plus-local-llm",
        "grammar": checked,
        "rewritten_text": rewritten,
        "network_required": False,
        "tone": tone,
    }
