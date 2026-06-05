from __future__ import annotations

from typing import Any

from backend.tools.writing.harper_checker import check_with_harper, harper_status


def writing_status() -> dict[str, Any]:
    return {
        "tool": "writing",
        "primary_engine": harper_status(),
        "local_fallback_ready": True,
        "uses_paid_api": False,
    }


def check_grammar(text: str) -> dict[str, Any]:
    return check_with_harper(text)
